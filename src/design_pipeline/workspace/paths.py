"""Disco de trabajo por proyecto: rutas y creación del esquema de carpetas."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectPaths:
    """Todas las rutas de un proyecto dentro del workspace."""

    root: Path

    # -- configuración y estado -------------------------------------------
    @property
    def project_yaml(self) -> Path:
        return self.root / "project.yaml"

    @property
    def state_yaml(self) -> Path:
        return self.root / "state.yaml"

    # -- artefactos del pipeline ------------------------------------------
    @property
    def inventory_json(self) -> Path:
        return self.root / "inventory.json"

    @property
    def analysis_json(self) -> Path:
        return self.root / "analysis.json"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def rules_dir(self) -> Path:
        return self.root / "rules"

    @property
    def design_rules_yaml(self) -> Path:
        return self.rules_dir / "design-rules.yaml"

    @property
    def questions_yaml(self) -> Path:
        return self.rules_dir / "questions.yaml"

    @property
    def specs_dir(self) -> Path:
        return self.root / "specs"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    def output_profile_dir(self, profile: str) -> Path:
        return self.output_dir / profile

    @property
    def context_dir(self) -> Path:
        return self.root / "context" / "agent-package"

    @property
    def runs_dir(self) -> Path:
        return self.root / "runs"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def summary_md(self) -> Path:
        return self.logs_dir / "summary.md"

    @property
    def project_skills_dir(self) -> Path:
        return self.root / ".skills"

    def ensure_layout(self) -> None:
        for path in (
            self.root,
            self.reports_dir,
            self.rules_dir,
            self.specs_dir,
            self.output_dir,
            self.runs_dir,
            self.logs_dir,
            self.project_skills_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
