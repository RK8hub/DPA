"""Modelo de estado del proyecto y su persistencia en ``state.yaml``."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from design_pipeline import SCHEMA_VERSION
from design_pipeline.engine import stages as stages_mod
from design_pipeline.errors import DesignPipelineError
from design_pipeline.utils import atomic_write_text, iso_now


@dataclass
class StageState:
    id: str
    label: str
    status: str = stages_mod.PENDING
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    artifacts: list[str] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class RunRecord:
    run_id: str
    stage: str
    started_at: str
    finished_at: str | None = None
    status: str = "in_progress"
    events: int = 0
    log_file: str | None = None
    error: str | None = None


@dataclass
class ProjectState:
    project: str
    created_at: str = field(default_factory=iso_now)
    updated_at: str = field(default_factory=iso_now)
    schema_version: int = SCHEMA_VERSION
    source_path: str | None = None
    stages: dict[str, StageState] = field(default_factory=dict)
    runs: list[RunRecord] = field(default_factory=list)
    decisions_pending: list[str] = field(default_factory=list)
    last_validation: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        for stage_def in stages_mod.STAGES:
            if stage_def.id not in self.stages:
                self.stages[stage_def.id] = StageState(id=stage_def.id, label=stage_def.label)

    # -- consultas ---------------------------------------------------------
    def stage(self, stage_id: str) -> StageState:
        try:
            return self.stages[stage_id]
        except KeyError as exc:  # pragma: no cover - contrato garantizado por __post_init__
            raise DesignPipelineError(f"Etapa desconocida: {stage_id}") from exc

    def is_done(self, stage_id: str) -> bool:
        return self.stage(stage_id).status == stages_mod.DONE

    def current_stage(self) -> str | None:
        """Primera etapa que no está ``done``, en orden."""
        for stage_def in stages_mod.STAGES:
            if self.stages[stage_def.id].status != stages_mod.DONE:
                return stage_def.id
        return None

    def add_run(self, record: RunRecord, keep: int = 20) -> None:
        self.runs.append(record)
        if len(self.runs) > keep:
            del self.runs[: len(self.runs) - keep]

    # -- persistencia ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        order = ["schema_version", "project", "created_at", "updated_at", "source_path"]
        ordered: dict[str, Any] = {key: data.pop(key) for key in order}
        ordered.update(data)
        return ordered

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        if not isinstance(data, dict):
            raise DesignPipelineError("state.yaml debe contener un mapping.")
        version = data.get("schema_version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise DesignPipelineError(
                f"Versión de esquema de estado no soportada: {version} (se esperaba {SCHEMA_VERSION})."
            )
        stages_raw = data.get("stages", {}) or {}
        stages = {
            key: StageState(**value) if isinstance(value, dict) else _bad_stage(key, value)
            for key, value in stages_raw.items()
        }
        runs_raw = data.get("runs", []) or []
        runs = [RunRecord(**value) for value in runs_raw if isinstance(value, dict)]
        state = cls(
            project=str(data.get("project", "unknown")),
            created_at=str(data.get("created_at", iso_now())),
            updated_at=str(data.get("updated_at", iso_now())),
            schema_version=version,
            source_path=data.get("source_path"),
            stages=stages,
            runs=runs,
            decisions_pending=list(data.get("decisions_pending", []) or []),
            last_validation=data.get("last_validation"),
        )
        # Conserva etapas guardadas desconocidas por compatibilidad futura.
        for key, value in stages_raw.items():
            if key not in state.stages:
                state.stages[key] = StageState(id=key, label=str(value))
        return state

    @classmethod
    def load(cls, path: Path) -> "ProjectState":
        if not path.exists():
            raise DesignPipelineError(f"No existe el archivo de estado: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls.from_dict(data or {})

    def save(self, path: Path) -> None:
        self.updated_at = iso_now()
        payload = yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)
        atomic_write_text(path, payload)


def _bad_stage(key: str, value: Any) -> StageState:
    raise DesignPipelineError(f"Entrada de etapa inválida en state.yaml: {key}={value!r}")
