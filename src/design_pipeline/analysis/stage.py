"""Etapa C: orquestación del análisis y persistencia de artefactos."""

from __future__ import annotations

import json

from design_pipeline.analysis.analyzer import AnalysisResult, ComponentInfo, CssInfo, Finding, Uncertainty, analyze_batch
from design_pipeline.analysis.reports import (
    render_analysis,
    render_component_map,
    render_uncertainties,
)
from design_pipeline.errors import DesignPipelineError
from design_pipeline.importers.stage import load_inventory
from design_pipeline.utils import write_json
from design_pipeline.workspace.project import Project


def run_analyze(project: Project) -> AnalysisResult:
    inventory = load_inventory(project)
    if inventory is None:
        raise DesignPipelineError("No hay inventario: ejecutá primero la etapa import.")
    source = project.source_path
    if source is None or not source.is_dir():
        raise DesignPipelineError("La fuente importada ya no está disponible.")

    result = analyze_batch(inventory, source)

    write_json(project.paths.analysis_json, result.to_dict())
    (project.paths.reports_dir / "ANALYSIS.md").write_text(
        render_analysis(result), encoding="utf-8"
    )
    (project.paths.reports_dir / "COMPONENT-MAP.md").write_text(
        render_component_map(result), encoding="utf-8"
    )
    (project.paths.reports_dir / "uncertainties.md").write_text(
        render_uncertainties(result), encoding="utf-8"
    )
    return result


def load_analysis(project: Project) -> AnalysisResult:
    """Rehidrata el análisis desde ``analysis.json`` (para etapas posteriores)."""
    path = project.paths.analysis_json
    if not path.exists():
        raise DesignPipelineError("No hay análisis: ejecutá primero la etapa analyze.")
    data = json.loads(path.read_text(encoding="utf-8"))
    return AnalysisResult(
        created_at=data["created_at"],
        inventory_fingerprint=data["inventory_fingerprint"],
        components=[ComponentInfo(**item) for item in data.get("components", [])],
        stylesheets=[CssInfo(**item) for item in data.get("stylesheets", [])],
        tokens=data.get("tokens", {}),
        findings=[Finding(**item) for item in data.get("findings", [])],
        uncertainties=[Uncertainty(**item) for item in data.get("uncertainties", [])],
        duplications=data.get("duplications", []),
        unused_assets=data.get("unused_assets", []),
        limitations=data.get("limitations", []),
    )
