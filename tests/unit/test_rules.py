from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from design_pipeline.analysis.analyzer import AnalysisResult, ComponentInfo, analyze_batch
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
    is_react_component,
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


# ---------------------------------------------------------------------------
# q-001: recomendación de destino con exportaciones .jsx (issue #5)
# ---------------------------------------------------------------------------


def _jsx_export(tmp_path: Path) -> Path:
    """Exportación 100% `.jsx` (el caso más común de Figma/FigCraft)."""
    src = tmp_path / "export-jsx"
    src.mkdir()
    for name in ("CardEquipment", "CardOperator", "InfoCards", "WrapperActions"):
        (src / f"{name}.jsx").write_text(
            f'import "./{name.lower()}.css";\n\n'
            f'export function {name}({{ title = "Título" }}) {{\n'
            '  return <div className="card">{title}</div>;\n}\n',
            encoding="utf-8",
        )
    return src


def test_q001_recomienda_react_para_lote_solo_jsx(tmp_path: Path):
    export = _jsx_export(tmp_path)
    inventory = build_inventory(export, TEXT_EXT, [], 1024 * 1024)
    analysis = analyze_batch(inventory, export)
    assert len(analysis.components) == 4
    assert all(component.path.endswith(".jsx") for component in analysis.components)

    question = build_discovery_questions(analysis)[0]
    assert question.id == "q-001"
    # El rationale de react-css describe textualmente este lote: recomendar
    # astro-css obligaría a una conversión además de la fidelidad.
    assert question.recommendation == "react-css"


def test_is_react_component_extension_y_contenido():
    # Extensión JSX/TSX basta (ambas son JSX de React).
    assert is_react_component(ComponentInfo(name="Card", path="Card.jsx"))
    assert is_react_component(ComponentInfo(name="Card", path="Card.tsx"))
    # Otras extensiones: se decide por evidencia en el contenido.
    assert is_react_component(
        ComponentInfo(name="Legacy", path="legacy.js", package_imports=["react"])
    )
    assert is_react_component(
        ComponentInfo(name="Legacy", path="legacy.js", hooks=["useState"])
    )
    # Sin señales de React: la extensión decide, no la etiqueta.
    assert not is_react_component(
        ComponentInfo(name="Astro", path="Astro.astro", package_imports=["@scope/pkg"])
    )
    assert not is_react_component(ComponentInfo(name="Astro", path="Astro.astro"))


def test_q001_sigue_recomendando_astro_sin_componentes_react():
    analysis = AnalysisResult(
        created_at="2026-01-01T00:00:00Z",
        inventory_fingerprint="abc",
        components=[ComponentInfo(name="Hero", path="Hero.astro")],
    )
    question = build_discovery_questions(analysis)[0]
    assert question.recommendation == "astro-css"


# ---------------------------------------------------------------------------
# Pregunta de tokens: una sola por decisión y derivación de regla (issue #2)
# ---------------------------------------------------------------------------


def test_pregunta_de_tokens_no_se_duplica(project, analysis):
    questions = seed_discovery(project, analysis)
    categories = [question.category for question in questions]
    # La decisión de tokens se pregunta una sola vez: ni el hallazgo `adhoc` ni
    # la incertidumbre u-00X generan una pregunta cada uno.
    assert categories.count("tokens") == 1
    # Mismo patrón para accesibilidad (idéntica duplicación, misma causa).
    assert categories.count("accesibilidad") == 1

    tokens_question = next(q for q in questions if q.category == "tokens")
    assert tokens_question.id == "q-003"
    assert tokens_question.options[0]["value"] == "conservar"
    # La procedencia conserva la incertidumbre del análisis que cubre.
    assert tokens_question.source.startswith("discovery+")
    assert "u-" in tokens_question.source
    # Las preguntas trazables al análisis que no se duplican siguen presentes.
    assert any(q.source.startswith("análisis:") for q in questions)
    # Idempotente: repetir no agrega ni renumera.
    assert [q.id for q in seed_discovery(project, analysis)] == [q.id for q in questions]


@pytest.mark.parametrize(
    ("answer", "expected_text"),
    [
        ("conservar", "Conservar los colores y medidas literales del export tal cual"),
        ("unificar", "Unificar los colores literales del lote en tokens"),
    ],
)
def test_responder_pregunta_de_tokens_deriva_regla(project, analysis, answer, expected_text):
    seed_discovery(project, analysis)
    answer_question(project, "q-003", answer)
    created = derive_rules_from_answers(project)

    assert len(created) == 1
    rule = created[0]
    assert rule.category == "tokens"
    assert rule.status == RULE_PROPOSED
    assert rule.provenance == {"kind": "derived", "origin": "answer:q-003"}
    assert expected_text in rule.text
    # Opción `unificar` incluida: antes sólo existía la clave muerta
    # `q-tokens-conservar`, que no coincidía con ninguna pregunta.
    assert derive_rules_from_answers(project) == []


def test_responder_cualquier_pregunta_de_descubrimiento_deriva_regla(project, analysis):
    questions = seed_discovery(project, analysis)
    accessibility = next(q for q in questions if q.category == "accesibilidad")
    answer_question(project, accessibility.id, "reportar")

    created = derive_rules_from_answers(project)
    assert len(created) == 1
    assert created[0].category == "accesibilidad"
    assert created[0].provenance["origin"] == f"answer:{accessibility.id}"
