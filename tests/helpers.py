"""Ayudante de pruebas: prepara un proyecto completo hasta la etapa spec."""

from __future__ import annotations

from pathlib import Path

from design_pipeline.analysis.stage import run_analyze
from design_pipeline.config import load_config
from design_pipeline.engine.pipeline import Pipeline
from design_pipeline.importers.stage import run_import
from design_pipeline.rules.manager import (
    answer_question,
    derive_rules_from_answers,
    decide_rule,
    load_rules,
    seed_discovery,
)
from design_pipeline.analysis.stage import load_analysis
from design_pipeline.spec.builder import build_specs
from design_pipeline.workspace.project import Project, create_project


def prepared_project(tmp_path: Path, fixture: Path, name: str = "demo") -> Project:
    """Crea un proyecto y lo lleva hasta spec con reglas aprobadas."""
    config = load_config()
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    project = create_project(name, ws, config)
    pipeline = Pipeline(project)

    handle = pipeline.begin("init")
    pipeline.complete(handle, artifacts=["project.yaml", "state.yaml"])

    handle = pipeline.begin("import")
    run_import(project, fixture)
    pipeline.complete(handle, artifacts=["inventory.json", "reports/IMPORT-REPORT.md"])

    handle = pipeline.begin("analyze")
    run_analyze(project)
    pipeline.complete(
        handle,
        artifacts=["analysis.json", "reports/ANALYSIS.md"],
    )

    handle = pipeline.begin("rules")
    analysis = load_analysis(project)
    seed_discovery(project, analysis)
    answer_question(project, "q-002", "css-puro")
    derive_rules_from_answers(project)
    for rule in load_rules(project):
        decide_rule(project, rule.id, approve=True)
    pipeline.complete(
        handle,
        artifacts=["rules/design-rules.yaml", "rules/questions.yaml"],
    )

    handle = pipeline.begin("spec")
    build_specs(project)
    pipeline.complete(handle, artifacts=["specs/index.json"])
    return project
