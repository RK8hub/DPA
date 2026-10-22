"""Ejecución genérica de etapas por id, reutilizada por `resume` y la TUI.

Cada etapa se ejecuta con el mismo ciclo begin/completar/fallar que la CLI;
la única diferencia es que aquí no hay argparse: las opciones llegan como
diccionario. Si una etapa necesita un dato que no existe (p. ej. la ruta de la
exportación para reimportar), falla con un mensaje accionable y detiene la
reanudación en ese punto (lo ya ejecutado queda registrado).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from design_pipeline.engine.pipeline import Pipeline
from design_pipeline.errors import DesignPipelineError
from design_pipeline.workspace.project import Project


@dataclass
class StageOutcome:
    stage: str
    artifacts: list[str]
    notes: list[str] = field(default_factory=list)
    summary: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


Runner = Callable[[Project, Pipeline, dict[str, Any]], StageOutcome]


# ---------------------------------------------------------------------------
# Runners por etapa
# ---------------------------------------------------------------------------

def _run_init(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.doctor import run_doctor

    workspace = project.paths.root.parent
    report = run_doctor(workspace=workspace)
    missing = [check for check in report.checks if not check.ok]
    return StageOutcome(
        stage="init",
        artifacts=["project.yaml", "state.yaml"],
        notes=[f"diagnóstico reejecutado: {len(missing)} ausencias"],
        summary=[f"- Proyecto **{project.name}** verificado (ausencias: "
                 f"{', '.join(c.name for c in missing) or 'ninguna'})."],
        payload={"missing": [check.name for check in missing]},
    )


def _run_import(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.importers.stage import run_import

    source_raw = options.get("source") or project.source_path
    if not source_raw:
        raise DesignPipelineError(
            "Etapa import: no hay ruta de exportación registrada. "
            "Ejecutá `design-pipeline import <carpeta> --project ...` o pasá --source."
        )
    source = Path(str(source_raw)).expanduser().resolve()
    if not source.is_dir():
        raise DesignPipelineError(f"Etapa import: la ruta no existe o no es directorio: {source}")
    summary = run_import(project, source)
    return StageOutcome(
        stage="import",
        artifacts=["inventory.json", "reports/IMPORT-REPORT.md"],
        notes=[
            f"archivos: {summary['files']}",
            f"referencias rotas: {summary['broken_references']}",
        ],
        summary=[f"- Importación de `{source}`: {summary['files']} archivos."],
        payload={"source": str(source), **summary},
    )


def _run_analyze(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.analysis.stage import run_analyze

    result = run_analyze(project)
    return StageOutcome(
        stage="analyze",
        artifacts=[
            "analysis.json",
            "reports/ANALYSIS.md",
            "reports/COMPONENT-MAP.md",
            "reports/uncertainties.md",
        ],
        notes=[f"componentes: {len(result.components)}", f"hallazgos: {len(result.findings)}"],
        summary=[f"- Análisis: {len(result.components)} componentes, "
                 f"{len(result.uncertainties)} incertidumbres."],
        payload={"components": [component.name for component in result.components]},
    )


def _run_rules(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.analysis.stage import load_analysis
    from design_pipeline.rules.manager import seed_discovery

    analysis = load_analysis(project)
    questions = seed_discovery(project, analysis)
    return StageOutcome(
        stage="rules",
        artifacts=[
            "rules/design-rules.yaml",
            "rules/questions.yaml",
            "reports/DESIGN-RULES.md",
            "reports/DECISIONS.md",
        ],
        notes=[f"preguntas: {len(questions)}"],
        summary=[f"- Reglas: {len(questions)} preguntas de descubrimiento registradas."],
        payload={"questions": len(questions)},
    )


def _run_spec(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.spec.builder import build_specs

    payload = build_specs(project)
    return StageOutcome(
        stage="spec",
        artifacts=["specs/index.json"] + [
            f"specs/components/{item['name']}.json" for item in payload["components"]
        ],
        notes=[f"componentes especificados: {len(payload['components'])}"],
        summary=[f"- Especificación: {len(payload['components'])} componentes."],
        payload=payload,
    )


def _run_generate(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.generators.stage import run_generate

    profile, result, output_dir = run_generate(project, options.get("profile"))
    return StageOutcome(
        stage="generate",
        artifacts=["reports/generation-notes.md", "output/" + profile.id],
        notes=[
            f"perfil: {profile.id}",
            f"archivos: {len(result.files)}",
            f"needs_review: {len(result.needs_review)}",
        ],
        summary=[f"- Generación ({profile.id}): {len(result.files)} archivos, "
                 f"{len(result.needs_review)} ítems de revisión."],
        payload={"profile": profile.id, "output": str(output_dir),
                 "files": len(result.files), "needs_review": result.needs_review},
    )


def _run_validate(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.validators.runner import run_validate, write_validation_report

    profile_id = options.get("profile") or str(
        project.data.get("generation", {}).get("profile", "react-css")
    )
    report = run_validate(
        project, profile_id, approve_external=bool(options.get("approve_external"))
    )
    write_validation_report(project, report)
    return StageOutcome(
        stage="validate",
        artifacts=["reports/validation-report.json", "reports/VALIDATION.md"],
        notes=[f"veredicto: {report.verdict}"],
        summary=[f"- Validación ({profile_id}): veredicto `{report.verdict}`."],
        payload=report.to_dict(),
    )


def _run_report(project: Project, pipeline: Pipeline, options: dict[str, Any]) -> StageOutcome:
    from design_pipeline.reporting.summary import run_report

    summary = run_report(project, options.get("profile"))
    return StageOutcome(
        stage="report",
        artifacts=["reports/DELIVERY.md", "reports/REVIEW-CHECKLIST.md"],
        notes=[f"veredicto: {summary['verdict']}", f"salida: {summary['output']}"],
        summary=[f"- Entrega generada en `{summary['output']}`."],
        payload=summary,
    )


RUNNERS: dict[str, Runner] = {
    "init": _run_init,
    "import": _run_import,
    "analyze": _run_analyze,
    "rules": _run_rules,
    "spec": _run_spec,
    "generate": _run_generate,
    "validate": _run_validate,
    "report": _run_report,
}


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def run_stage(
    project: Project,
    pipeline: Pipeline,
    stage_id: str,
    options: dict[str, Any] | None = None,
) -> StageOutcome:
    """Ejecuta una etapa completa con el ciclo begin/complete/fail."""
    runner = RUNNERS.get(stage_id)
    if runner is None:  # pragma: no cover - STAGE_IDS y RUNNERS se mantienen juntos
        raise DesignPipelineError(f"No existe runner para la etapa {stage_id}.")
    options = options or {}
    handle = pipeline.begin(stage_id)
    try:
        outcome = runner(project, pipeline, options)
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    pipeline.complete(
        handle,
        artifacts=outcome.artifacts,
        notes=outcome.notes,
        summary_lines=outcome.summary,
    )
    return outcome


def resume_pipeline(
    project: Project,
    pipeline: Pipeline,
    options: dict[str, Any] | None = None,
    until: str | None = None,
) -> list[StageOutcome]:
    """Reejecuta etapas pendientes/obsoletas fallidas en orden.

    - ``until``: id de etapa límite (inclusive); sin él, corre todo lo pendiente.
    - Recalcula la reanudabilidad tras cada etapa para respetar staleness.
    - Se detiene ante la primera etapa que falla (el error ya quedó registrado
      en el estado y en el log).
    """
    from design_pipeline.engine import stages as stages_mod

    if until is not None and until not in stages_mod.STAGE_IDS:
        raise DesignPipelineError(
            f"Límite de reanudación desconocido: {until!r}. "
            f"Opciones: {', '.join(stages_mod.STAGE_IDS)}"
        )
    executed: list[StageOutcome] = []
    while True:
        pending = pipeline.resumable()
        if not pending:
            break
        if until is not None:
            order = stages_mod.STAGE_IDS
            limit = order.index(until)
            runnable = [stage for stage in pending if order.index(stage) <= limit]
            if not runnable:
                break
            target = runnable[0]
        else:
            target = pending[0]
        outcome = run_stage(project, pipeline, target, options)
        executed.append(outcome)
        if until is not None and target == until:
            break
    return executed
