"""Etapa F: orquestación de la generación por perfil."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from design_pipeline.analysis.stage import load_analysis
from design_pipeline.errors import DesignPipelineError
from design_pipeline.generators.base import GenerationContext, GenerationResult, Profile
from design_pipeline.generators.registry import get_profile
from design_pipeline.rules.manager import approved_rules, pending_rules
from design_pipeline.utils import iso_now
from design_pipeline.workspace.project import Project


def load_specs(project: Project) -> list[dict[str, Any]]:
    specs_dir = project.paths.specs_dir / "components"
    if not specs_dir.is_dir():
        raise DesignPipelineError("No hay especificaciones: ejecutá primero la etapa spec.")
    specs = []
    for path in sorted(specs_dir.glob("*.json")):
        specs.append(json.loads(path.read_text(encoding="utf-8")))
    if not specs:
        raise DesignPipelineError("El índice de especificaciones está vacío.")
    return specs


def run_generate(
    project: Project, profile_id: str | None = None
) -> tuple[Profile, GenerationResult, Path]:
    source_root = project.source_path
    if source_root is None or not source_root.is_dir():
        raise DesignPipelineError("La fuente importada no está disponible.")

    chosen = profile_id or str(project.data.get("generation", {}).get("profile", "react-css"))
    profile = get_profile(chosen)
    specs = load_specs(project)
    analysis = load_analysis(project)
    rules = approved_rules(project)

    output_dir = project.paths.output_profile_dir(profile.id)
    ctx = GenerationContext(
        project=project,
        source_root=source_root,
        output_dir=output_dir,
        specs=specs,
        analysis=analysis,
        approved_rules=rules,
    )
    result = profile.generate(ctx)
    _write_generation_notes(project, profile, result, rules, pending_rules(project))
    return profile, result, output_dir


def _write_generation_notes(
    project: Project,
    profile: Profile,
    result: GenerationResult,
    approved: list,
    pending: list,
) -> None:
    files = "\n".join(
        f"- `{file.path}` ({file.action})"
        + (f" — {file.note}" if file.note else "")
        for file in result.files
    ) or "- (ninguno)"
    review = "\n".join(f"- {item}" for item in result.needs_review) or "- Ninguno."
    notes = "\n".join(f"- {note}" for note in result.notes) or "- Ninguna."
    approved_lines = (
        "\n".join(f"- **{rule.id}**: {rule.text}" for rule in approved) or "- Ninguna."
    )
    pending_lines = (
        "\n".join(f"- **{rule.id}** ({rule.status}): {rule.text}" for rule in pending)
        or "- Ninguna."
    )
    text = f"""# Notas de generación

- **Fecha:** {iso_now()}
- **Perfil:** `{profile.id}` — {profile.label}
- **Reglas aprobadas aplicadas:** {len(approved)}
- **Reglas todavía propuestas (no aplicadas):** {len(pending)}

## Archivos generados

{files}

## Decisiones y transformaciones

{notes}

## Revisión humana pendiente

{review}

## Reglas aprobadas

{approved_lines}

## Reglas pendientes de aprobación

{pending_lines}

## Limitaciones conocidas

- La conversión a Tailwind **no** está implementada de forma determinista: el
  perfil aplica CSS puro. La conversión a utilidades queda como trabajo
  asistido por agente o humano (ver docs/ARCHITECTURE.md).
- Ninguna dependencia de destino fue instalada. Los requisitos de cada perfil
  se listan en el README de la carpeta de salida.
- La exportación original no fue modificada.
"""
    (project.paths.reports_dir / "generation-notes.md").write_text(text, encoding="utf-8")
