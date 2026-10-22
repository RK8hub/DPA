"""Carga y fusión de configuración: defaults del paquete < usuario < proyecto < flags."""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from design_pipeline.errors import ConfigError
from design_pipeline.utils import deep_merge, dotted_get

USER_CONFIG_ENV = "DESIGN_PIPELINE_CONFIG"
WORKSPACE_ENV = "DESIGN_PIPELINE_WORKSPACE"


def packaged_defaults() -> dict[str, Any]:
    """Lee ``data/config/defaults.yaml`` desde los recursos del paquete."""
    ref = resources.files("design_pipeline").joinpath("data/config/defaults.yaml")
    try:
        data = yaml.safe_load(ref.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - solo falla si el paquete está corrupto
        raise ConfigError(f"No se pudo leer la configuración empaquetada: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError("La configuración empaquetada no es un mapping YAML.")
    return data


def user_config_path() -> Path:
    """Ruta del config de usuario. Respeta DESIGN_PIPELINE_CONFIG y XDG_CONFIG_HOME."""
    override = os.environ.get(USER_CONFIG_ENV)
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "design-pipeline" / "config.yaml"


def global_skills_dir(config: dict[str, Any]) -> Path:
    configured = dotted_get(config, "skills.global_dir")
    if configured:
        return Path(str(configured)).expanduser()
    return user_config_path().parent / "skills"


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ConfigError(f"{label} ilegible ({path}): {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError(f"{label} debe ser un mapping YAML: {path}")
    return data


def load_config(
    project_dir: Path | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Combina todas las fuentes de configuración en un único dict.

    ``overrides`` viene de flags CLI y tiene la máxima prioridad.
    """
    config = packaged_defaults()
    config = deep_merge(config, _load_yaml_mapping(user_config_path(), "Config de usuario"))
    if project_dir is not None:
        config = deep_merge(
            config, _load_yaml_mapping(project_dir / "project.yaml", "Config de proyecto")
        )
    env_workspace = os.environ.get(WORKSPACE_ENV)
    if env_workspace:
        config = deep_merge(config, {"workspace_root": env_workspace})
    if overrides:
        config = deep_merge(config, overrides)
    return config


def workspace_root(config: dict[str, Any], cli_workspace: str | None = None) -> Path:
    raw = cli_workspace or str(config.get("workspace_root", "./workspace"))
    return Path(raw).expanduser().resolve()
