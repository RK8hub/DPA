"""Alta, carga y enumeración de proyectos en el workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from design_pipeline.config import load_config, workspace_root
from design_pipeline.engine.state import ProjectState
from design_pipeline.errors import (
    DesignPipelineError,
    ProjectExistsError,
    ProjectNotFoundError,
)
from design_pipeline.utils import atomic_write_text, dotted_get, iso_now, project_slug
from design_pipeline.workspace.paths import ProjectPaths


@dataclass
class Project:
    """Proyecto abierto: rutas, configuración fusionada y datos persistidos."""

    name: str
    paths: ProjectPaths
    config: dict[str, Any]
    data: dict[str, Any] = field(default_factory=dict)
    state: ProjectState | None = None

    # -- estado ------------------------------------------------------------
    @property
    def state_path(self) -> Path:
        return self.paths.state_yaml

    def load_state(self) -> ProjectState:
        if self.state is None:
            self.state = ProjectState.load(self.paths.state_yaml)
        return self.state

    def save_state(self) -> None:
        if self.state is None:
            raise DesignPipelineError("No hay estado cargado para guardar.")
        self.state.save(self.paths.state_yaml)

    # -- configuración de proyecto (project.yaml) --------------------------
    def save_data(self) -> None:
        self.data["updated_at"] = iso_now()
        payload = yaml.safe_dump(self.data, sort_keys=False, allow_unicode=True)
        atomic_write_text(self.paths.project_yaml, payload)

    @property
    def enabled_skills(self) -> list[str]:
        return list((self.data.get("skills") or {}).get("enabled", []) or [])

    def set_enabled_skills(self, names: list[str]) -> None:
        skills = dict(self.data.get("skills") or {})
        skills["enabled"] = sorted(set(names))
        self.data["skills"] = skills

    @property
    def source_path(self) -> Path | None:
        raw = (self.data.get("source") or {}).get("path")
        return Path(raw) if raw else None

    def set_source(self, path: Path) -> None:
        source = dict(self.data.get("source") or {})
        source["path"] = str(path)
        self.data["source"] = source


def create_project(name: str, root_ws: Path, config: dict[str, Any]) -> Project:
    if not project_slug(name):
        raise DesignPipelineError(
            f"Nombre de proyecto inválido: {name!r}. Usá minúsculas, dígitos y guiones (2-64 caracteres)."
        )
    paths = ProjectPaths(root=root_ws / name)
    if paths.root.exists():
        raise ProjectExistsError(f"Ya existe un proyecto en {paths.root}.")
    paths.ensure_layout()
    data: dict[str, Any] = {
        "schema_version": 1,
        "name": name,
        "created_at": iso_now(),
        "updated_at": iso_now(),
        "source": {},
        "skills": {"enabled": []},
        "generation": {"profile": str(dotted_get(config, "generation.default_profile", "react-css"))},
    }
    project = Project(name=name, paths=paths, config=config, data=data)
    project.save_data()
    return project


def project_exists(name: str, root_ws: Path) -> bool:
    return (root_ws / name / "project.yaml").exists()


def load_project(name: str, root_ws: Path, config: dict[str, Any] | None = None) -> Project:
    paths = ProjectPaths(root=root_ws / name)
    if not paths.project_yaml.exists():
        raise ProjectNotFoundError(
            f"No existe el proyecto {name!r} en {root_ws}. Ejecutá `design-pipeline init {name}`."
        )
    data = yaml.safe_load(paths.project_yaml.read_text(encoding="utf-8")) or {}
    merged = config if config is not None else load_config(project_dir=paths.root)
    project = Project(name=name, paths=paths, config=merged, data=data)
    if paths.state_yaml.exists():
        project.state = ProjectState.load(paths.state_yaml)
    return project


def list_projects(root_ws: Path) -> list[str]:
    if not root_ws.is_dir():
        return []
    return sorted(
        entry.name
        for entry in root_ws.iterdir()
        if entry.is_dir() and (entry / "project.yaml").exists()
    )


def resolve_project_root(config: dict[str, Any], cli_workspace: str | None = None) -> Path:
    return workspace_root(config, cli_workspace)
