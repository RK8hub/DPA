from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from design_pipeline.analysis.analyzer import analyze_batch
from design_pipeline.config import load_config
from design_pipeline.errors import DesignPipelineError
from design_pipeline.importers.inventory import build_inventory
from design_pipeline.rules.manager import (
    RULE_APPROVED,
    RULE_PROPOSED,
    STATUS_ANSWERED,
    STATUS_OPEN,
    answer_question,
    build_discovery_questions,
    decide_rule,
    derive_rules_from_answers,
    approved_rules,
    import_rules_file,
    load_questions,
    load_rules,
    pending_rules,
    seed_discovery,
)
from design_pipeline.workspace.project import create_project

TEXT_EXT = [".tsx", ".ts", ".jsx", ".js", ".css", ".json", ".svg", ".md", ".txt"]


@pytest.fixture
def project(tmp_path: Path):
    config = load_config()
    ws = tmp_path / "ws"
    ws.mkdir()
    return create_project("demo", ws, config)


@pytest.fixture
def analysis(fixture_export: Path):
    inv = build_inventory(fixture_export, TEXT_EXT, [], 1024 * 1024)
    return analyze_batch(inv, fixture_export)


def test_discovery_questions_priorizadas(analysis):
    questions = build_discovery_questions(analysis)
    assert questions[0].id == "q-001"
    assert {option["value"] for option in questions[0].options} == {"react-css", "astro-css"}
    assert questions[0].recommendation == "react-css"  # mayoría TSX
    categories = {question.category for question in questions}
    assert "estilos" in categories
    assert "accesibilidad" in categories  # fixture tiene hallazgos a11y
    assert "interactividad" in categories  # Stat usa useState
    assert "tokens" in categories  # hay colores literales propuestos
    # Toda pregunta derivada del análisis conserva la procedencia.
    derived = [q for q in questions if q.source.startswith("análisis:")]
    assert derived
    # Toda opción tiene value slug.
    for question in questions:
        for option in question.options:
            assert option["value"] == option["value"].lower()


def test_seed_discovery_idempotente(project, analysis):
    first = seed_discovery(project, analysis)
    second = seed_discovery(project, analysis)
    assert [q.id for q in first] == [q.id for q in second]
    assert len(load_questions(project)) == len(first)


def test_answer_valida_opciones_y_deriva_reglas(project, analysis):
    seed_discovery(project, analysis)
    with pytest.raises(DesignPipelineError):
        answer_question(project, "q-002", "valor-inexistente")
    answer_question(project, "q-001", "react-css")
    answer_question(project, "q-002", "css-puro")
    created = derive_rules_from_answers(project)
    assert created
    # Las reglas derivadas quedan propuestas, nunca aprobadas automáticamente.
    assert all(rule.status == RULE_PROPOSED for rule in created)
    assert {rule.id for rule in pending_rules(project)}
    # La respuesta de perfil se refleja en project.yaml.
    assert project.data["generation"]["profile"] == "react-css"
    # Derivar dos veces no duplica reglas.
    assert derive_rules_from_answers(project) == []


def test_approve_regla_y_pending_sync(project, analysis):
    seed_discovery(project, analysis)
    answer_question(project, "q-002", "css-puro")
    derive_rules_from_answers(project)
    state = project.load_state()
    assert state.decisions_pending  # preguntas abiertas + reglas propuestas
    target = pending_rules(project)[0]
    decided = decide_rule(project, target.id, approve=True)
    assert target.id in {rule.id for rule in approved_rules(project)}
    assert decided.status == RULE_APPROVED
    assert decided.decided_at is not None
    # DECISIONS.md y DESIGN-RULES.md regenerados.
    decisions = (project.paths.reports_dir / "DECISIONS.md").read_text()
    assert target.id in decisions
    rules_md = (project.paths.reports_dir / "DESIGN-RULES.md").read_text()
    assert target.id in rules_md


def test_import_rules_file_yaml(project, tmp_path: Path):
    rules_file = tmp_path / "reglas.yaml"
    rules_file.write_text(
        yaml.safe_dump(
            {
                "rules": [
                    {"text": "Conservar el espaciado original de 8px base.", "category": "espaciado"},
                    {"text": "Usar la tipografía Inter en todos los componentes.", "category": "tipografia"},
                ]
            }
        )
    )
    imported = import_rules_file(project, rules_file)
    assert len(imported) == 2
    assert all(rule.status == RULE_PROPOSED for rule in imported)
    assert imported[0].provenance["kind"] == "user"
    assert rules_file.name in imported[0].provenance["origin"]
    # Repetir la importación no duplica (dedupe por texto).
    assert import_rules_file(project, rules_file) == []
    # Aprobación explícita.
    decide_rule(project, imported[0].id, approve=True)
    assert len(approved_rules(project)) == 1


def test_import_rules_file_markdown_con_approve(project, tmp_path: Path):
    rules_file = tmp_path / "reglas.md"
    rules_file.write_text("# Reglas\n\n- No inventar colores nuevos.\n- Respetar los breakpoints.\n")
    imported = import_rules_file(project, rules_file, approve=True)
    assert len(imported) == 2
    assert all(rule.status == RULE_APPROVED for rule in imported)


def test_import_rules_file_inexistente(project, tmp_path: Path):
    with pytest.raises(DesignPipelineError):
        import_rules_file(project, tmp_path / "no-existe.yaml")
