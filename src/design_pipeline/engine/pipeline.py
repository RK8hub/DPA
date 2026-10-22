"""Orquestador de etapas: prerequisitos, ejecución, reanudación y obsolescencia.

El motor no contiene lógica de negocio de cada etapa; solo administra el ciclo
de vida (pendiente → en curso → done/failed/stale), los artefactos, los
fingerprints de entradas y el registro estructurado de cada ejecución.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from design_pipeline.engine import stages as stages_mod
from design_pipeline.engine.log import RunLogger
from design_pipeline.engine.state import ProjectState, RunRecord
from design_pipeline.errors import StageOrderError
from design_pipeline.utils import dotted_get, iso_now, new_run_id, sha256_file, tree_fingerprint
from design_pipeline.workspace.project import Project

# Etapas cuyas entradas se registran y comparan para detectar obsolescencia.
# Los valores son rutas relativas al proyecto; un path de directorio se hashea
# como árbol completo. Los archivos opcionales usan el prefixo "optional:".
_FINGERPRINT_SOURCES: dict[str, tuple[str, ...]] = {
    "import": ("@source-tree",),
    "analyze": ("inventory.json",),
    "rules": ("inventory.json", "analysis.json"),
    "spec": ("analysis.json", "optional:rules/design-rules.yaml", "optional:rules/questions.yaml"),
    "generate": (
        "specs",
        "optional:rules/design-rules.yaml",
        "optional:rules/questions.yaml",
    ),
    "validate": ("output",),
    "report": ("reports/validation-report.json",),
}


@dataclass
class RunHandle:
    """Identificador de una ejecución en curso."""

    run_id: str
    stage_id: str
    started_at: str
    logger: RunLogger
    inputs: dict[str, str] = field(default_factory=dict)


class Pipeline:
    def __init__(self, project: Project) -> None:
        self.project = project
        if project.paths.state_yaml.exists():
            self.state: ProjectState = project.load_state()
        else:
            # Etapa A recién creada: inicializa el estado en disco.
            self.state = ProjectState(project=project.name)
            project.state = self.state
            project.save_state()

    # -- consultas ---------------------------------------------------------
    def missing_requirements(self, stage_id: str) -> list[str]:
        """Etapa cuyo estado impide ejecutar ``stage_id``."""
        stage_def = stages_mod.STAGE_BY_ID[stage_id]
        missing: list[str] = []
        for required in stage_def.requires:
            if not self.state.is_done(required):
                missing.append(required)
        return missing

    # -- ciclo de vida -----------------------------------------------------
    def begin(self, stage_id: str) -> RunHandle:
        missing = self.missing_requirements(stage_id)
        if missing:
            raise StageOrderError(
                f"La etapa '{stage_id}' requiere que estén completas: {', '.join(missing)}."
            )
        run_id = new_run_id()
        started_at = iso_now()
        logger = RunLogger(self.project.paths.runs_dir, run_id, stage_id)
        inputs = self.compute_inputs(stage_id)
        handle = RunHandle(
            run_id=run_id, stage_id=stage_id, started_at=started_at, logger=logger, inputs=inputs
        )
        stage_state = self.state.stage(stage_id)
        stage_state.status = stages_mod.IN_PROGRESS
        stage_state.started_at = started_at
        stage_state.finished_at = None
        stage_state.duration_seconds = None
        stage_state.inputs = dict(inputs)
        logger.event("stage_start", stage=stage_id, inputs=inputs)
        # Registro de skills activas para esta etapa (solo trazabilidad:
        # las instrucciones se entregan al usuario/agente, nunca se ejecutan).
        try:
            from design_pipeline.skills.registry import active_skills_for_stage

            active = active_skills_for_stage(self.project, stage_id)
            if active:
                logger.event(
                    "skills_activated",
                    skills=[
                        {
                            "name": record.name,
                            "version": record.version,
                            "mode": record.mode,
                            "origin": record.origin,
                            "why": f"habilitada en el proyecto y declara la etapa '{stage_id}'",
                        }
                        for record in active
                    ],
                )
                stage_state.notes.append(
                    "skills activas: "
                    + ", ".join(f"{r.name} ({r.origin})" for r in active)
                )
        except Exception:  # pragma: no cover - el registro no debe romper el pipeline
            pass
        self.state.add_run(
            RunRecord(
                run_id=run_id,
                stage=stage_id,
                started_at=started_at,
                log_file=str(logger.path.relative_to(self.project.paths.root)),
            ),
            keep=int(dotted_get(self.project.config, "reporting.keep_runs", 20)),
        )
        self.project.save_state()
        return handle

    def complete(
        self,
        handle: RunHandle,
        artifacts: list[str],
        notes: list[str] | None = None,
        summary_lines: list[str] | None = None,
    ) -> None:
        finished_at = iso_now()
        stage_state = self.state.stage(handle.stage_id)
        stage_state.status = stages_mod.DONE
        stage_state.finished_at = finished_at
        stage_state.duration_seconds = _duration(handle.started_at, finished_at)
        stage_state.artifacts = list(artifacts)
        stage_state.notes = list(notes or [])
        # Recalcula las entradas al finalizar: algunas (p. ej. la ruta de la
        # fuente en la etapa import) solo se conocen cuando la etapa corre.
        stage_state.inputs = self.compute_inputs(handle.stage_id)
        # Etapas aguas abajo dejan de estar obsoletas cuando esta se completa.
        for downstream in stages_mod.downstream(handle.stage_id):
            ds_state = self.state.stage(downstream)
            if ds_state.status == stages_mod.STALE:
                ds_state.status = stages_mod.PENDING
        handle.logger.event(
            "stage_done", stage=handle.stage_id, artifacts=artifacts, notes=notes or []
        )
        self._finish_run(handle, status="done")
        if summary_lines:
            handle.logger.append_summary(self.project.paths.summary_md, summary_lines)
        self.project.save_state()

    def fail(self, handle: RunHandle, error: str) -> None:
        stage_state = self.state.stage(handle.stage_id)
        stage_state.status = stages_mod.FAILED
        stage_state.finished_at = iso_now()
        stage_state.duration_seconds = _duration(handle.started_at, stage_state.finished_at)
        handle.logger.event("stage_failed", stage=handle.stage_id, error=error)
        for record in reversed(self.state.runs):
            if record.run_id == handle.run_id:
                record.status = "failed"
                record.error = error
                record.finished_at = stage_state.finished_at
                record.events = handle.logger.events
                break
        self.project.save_state()

    def _finish_run(self, handle: RunHandle, status: str) -> None:
        for record in reversed(self.state.runs):
            if record.run_id == handle.run_id:
                record.status = status
                record.finished_at = iso_now()
                record.events = handle.logger.events
                break

    # -- fingerprints y obsolescencia ---------------------------------------
    def compute_inputs(self, stage_id: str) -> dict[str, str]:
        """Huella actual de las entradas de una etapa."""
        sources = _FINGERPRINT_SOURCES.get(stage_id, ())
        inputs: dict[str, str] = {}
        root = self.project.paths.root
        for source in sources:
            optional = source.startswith("optional:")
            rel = source[len("optional:") :] if optional else source
            if rel == "@source-tree":
                src = self.project.source_path
                if src is None or not Path(src).is_dir():
                    inputs["source-tree"] = "<no-source>"
                else:
                    exclusions = self.project.config.get("exclusions", []) or []
                    inputs["source-tree"] = tree_fingerprint(Path(src), exclusions)
                continue
            target = root / rel
            if not target.exists():
                inputs[rel] = "" if optional else f"<missing:{rel}>"
            elif target.is_dir():
                exclusions = self.project.config.get("exclusions", []) or []
                inputs[rel] = tree_fingerprint(target, exclusions)
            else:
                inputs[rel] = sha256_file(target)
        return inputs

    def refresh_staleness(self) -> list[tuple[str, str]]:
        """Marca etapas ``done`` cuyas entradas cambiaron como ``stale``.

        Devuelve la lista de (etapa, motivo). Persiste el estado.
        """
        stale: list[tuple[str, str]] = []
        upstream_stale: set[str] = set()
        for stage_def in stages_mod.STAGES:
            stage_state = self.state.stage(stage_def.id)
            if stage_state.status != stages_mod.DONE:
                continue
            reason: str | None = None
            for upstream in stage_def.requires:
                if upstream in upstream_stale or not self.state.is_done(upstream):
                    reason = f"etapa previa '{upstream}' obsoleta o incompleta"
                    break
            if reason is None:
                current = self.compute_inputs(stage_def.id)
                for key, value in current.items():
                    recorded = stage_state.inputs.get(key)
                    if recorded is None:
                        reason = f"falta la entrada registrada '{key}'"
                        break
                    if value.startswith("<missing:") and recorded != value:
                        reason = f"desapareció el artefacto '{key}'"
                        break
                    if value != recorded:
                        reason = f"cambiaron las entradas '{key}'"
                        break
            if reason is not None:
                stage_state.status = stages_mod.STALE
                stage_state.notes.append(f"Obsoleta: {reason} ({iso_now()})")
                stale.append((stage_def.id, reason))
                upstream_stale.add(stage_def.id)
        if stale:
            self.project.save_state()
        return stale

    # -- reanudación --------------------------------------------------------
    def resumable(self) -> list[str]:
        """Etapas que conviene (re)ejecutar, en orden."""
        self.refresh_staleness()
        pending: list[str] = []
        for stage_def in stages_mod.STAGES:
            status = self.state.stage(stage_def.id).status
            if status in (stages_mod.PENDING, stages_mod.STALE, stages_mod.FAILED):
                pending.append(stage_def.id)
        return pending

    def last_run(self) -> RunRecord | None:
        return self.state.runs[-1] if self.state.runs else None


def _duration(started_at: str, finished_at: str) -> float:
    from datetime import datetime

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    start = datetime.strptime(started_at, fmt)
    end = datetime.strptime(finished_at, fmt)
    return max(0.0, (end - start).total_seconds())


def stage_artifacts(project: Project, stage_id: str) -> list[str]:
    state = project.load_state()
    return list(state.stage(stage_id).artifacts)


def collect_inputs(config: dict[str, Any], project: Project) -> dict[str, Any]:
    """Helper para reportes: config efectiva y fingerprint de la fuente."""
    src = project.source_path
    exclusions = config.get("exclusions", []) or []
    return {
        "source": str(src) if src else None,
        "source_fingerprint": tree_fingerprint(src, exclusions) if src else None,
    }
