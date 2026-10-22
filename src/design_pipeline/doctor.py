"""Diagnóstico del entorno: dependencias disponibles y ausentes."""

from __future__ import annotations

import importlib
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from design_pipeline import __version__
from design_pipeline.config import global_skills_dir, user_config_path

# CLIs de agente que el usuario podría tener. La detección NO implica
# compatibilidad: solo informa presencia. La compatibilidad se declara por
# adaptador en design_pipeline.adapters.
AGENT_CLIS = ("opencode", "claude", "codex", "gemini", "aider")

MIN_PYTHON = (3, 11)


@dataclass
class Check:
    name: str
    ok: bool
    required: bool
    detail: str
    remedy: str = ""


@dataclass
class DoctorReport:
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks if check.required)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "design_pipeline_version": __version__,
            "checks": [
                {
                    "name": check.name,
                    "ok": check.ok,
                    "required": check.required,
                    "detail": check.detail,
                    "remedy": check.remedy,
                }
                for check in self.checks
            ],
        }


def _module_version(module: str) -> str | None:
    try:
        found = importlib.import_module(module)
    except Exception:
        return None
    return str(getattr(found, "__version__", "desconocida"))


def run_doctor(workspace: Path | None = None) -> DoctorReport:
    report = DoctorReport()

    # Python ---------------------------------------------------------------
    py_ok = sys.version_info >= MIN_PYTHON
    report.checks.append(
        Check(
            name="python",
            ok=py_ok,
            required=True,
            detail=f"{sys.version.split()[0]} en {sys.executable}",
            remedy="" if py_ok else f"Instalá Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} o superior.",
        )
    )

    # PyYAML (dependencia de runtime) ---------------------------------------
    yaml_version = _module_version("yaml")
    report.checks.append(
        Check(
            name="pyyaml",
            ok=yaml_version is not None,
            required=True,
            detail=f"PyYAML {yaml_version}" if yaml_version else "no instalado",
            remedy="" if yaml_version else "Instalá el paquete con `pip install PyYAML`.",
        )
    )

    # pytest (solo desarrollo) ----------------------------------------------
    pytest_version = _module_version("pytest")
    report.checks.append(
        Check(
            name="pytest",
            ok=pytest_version is not None,
            required=False,
            detail=f"pytest {pytest_version}" if pytest_version else "no instalado",
            remedy="" if pytest_version else "Opcional: `pip install -e '.[dev]'` para correr la suite.",
        )
    )

    # Node/npm (necesario solo para builds del proyecto de destino) ---------
    for tool in ("node", "npm"):
        found = shutil.which(tool)
        report.checks.append(
            Check(
                name=tool,
                ok=found is not None,
                required=False,
                detail=found or "no encontrado",
                remedy=""
                if found
                else f"Sin {tool}: las validaciones de build/lint se marcarán SKIPPED.",
            )
        )

    # git -------------------------------------------------------------------
    git_path = shutil.which("git")
    report.checks.append(
        Check(
            name="git",
            ok=git_path is not None,
            required=False,
            detail=git_path or "no encontrado",
            remedy="" if git_path else "Opcional: útil para versionar el workspace.",
        )
    )

    # CLIs de agente (solo informativo) -------------------------------------
    detected = [cli for cli in AGENT_CLIS if shutil.which(cli)]
    report.checks.append(
        Check(
            name="agentes-detectados",
            ok=True,
            required=False,
            detail=", ".join(detected) if detected else "ninguna CLI de agente en PATH",
            remedy="La detección no implica compatibilidad; verificá el adaptador correspondiente.",
        )
    )

    # Config y workspace ----------------------------------------------------
    user_cfg = user_config_path()
    report.checks.append(
        Check(
            name="config-usuario",
            ok=True,
            required=False,
            detail=f"{user_cfg} ({'existe' if user_cfg.exists() else 'no existe; se usan los defaults'})",
        )
    )
    skills_dir = global_skills_dir({"skills": {}})
    report.checks.append(
        Check(
            name="skills-globales",
            ok=True,
            required=False,
            detail=f"{skills_dir} ({'existe' if skills_dir.exists() else 'se creará al importar una skill'})",
        )
    )
    if workspace is not None:
        writable = workspace.exists() and workspace.is_dir() and os_access_write(workspace)
        report.checks.append(
            Check(
                name="workspace",
                ok=writable,
                required=False,
                detail=f"{workspace} ({'escribible' if writable else 'inexistente o no escribible'})",
                remedy="" if writable else "Creá el directorio o elegí otro con --workspace.",
            )
        )
    return report


def os_access_write(path: Path) -> bool:
    import os

    return os.access(path, os.W_OK)


def render_text(report: DoctorReport) -> str:
    lines = [f"design-pipeline {__version__} — diagnóstico del entorno", ""]
    for check in report.checks:
        mark = "OK " if check.ok else ("FALTA" if not check.required else "ERROR")
        lines.append(f"[{mark:>5}] {check.name}: {check.detail}")
        if not check.ok and check.remedy:
            lines.append(f"        -> {check.remedy}")
    lines.append("")
    lines.append("Entorno listo." if report.ok else "Hay dependencias requeridas ausentes.")
    return "\n".join(lines)
