from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from design_pipeline.analysis.analyzer import (
    AnalysisResult,
    ComponentInfo,
    Uncertainty,
    analyze_batch,
)
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


# ---------------------------------------------------------------------------
# seed_discovery incremental: el análisis cambió → se agregan preguntas (#3)
# ---------------------------------------------------------------------------


def _card_export(directory: Path, stylesheet: bool) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    css_import = 'import "./Card.css";\n\n' if stylesheet else ""
    (directory / "Card.jsx").write_text(
        css_import
        + 'export function Card({ title = "Título" }) {\n'
        '  return <div className="card">{title}</div>;\n}\n',
        encoding="utf-8",
    )
    if stylesheet:
        (directory / "Card.css").write_text(
            ":root { --card-bg: #ffffff; }\n"
            ".card { background: #f7f8fa; color: #6b7686; border: 1px solid #e3e8f0; }\n",
            encoding="utf-8",
        )
    return directory


def test_seed_discovery_agrega_preguntas_cuando_el_analisis_cambia(project, tmp_path: Path):
    # 1ª importación: sin hojas de estilo → sólo q-001 y q-002.
    bare = _card_export(tmp_path / "export-bare", stylesheet=False)
    old = analyze_batch(build_inventory(bare, TEXT_EXT, [], 1024 * 1024), bare)
    questions = seed_discovery(project, old)
    assert {q.id for q in questions} == {"q-001", "q-002"}
    answer_question(project, "q-001", "react-css")

    # 2ª importación corregida: ahora hay `.css` con colores literales → el
    # análisis nuevo trae el hallazgo `tokens` y su incertidumbre.
    full = _card_export(tmp_path / "export-full", stylesheet=True)
    new = analyze_batch(build_inventory(full, TEXT_EXT, [], 1024 * 1024), full)
    assert any(u.category == "tokens" for u in new.uncertainties)

    questions = seed_discovery(project, new)
    assert [q.category for q in questions].count("tokens") == 1
    assert len(questions) == 3
    # Las preguntas previas conservan id, texto y — sobre todo — la respuesta.
    assert len({q.id for q in questions}) == len(questions)
    assert next(q for q in questions if q.id == "q-001").answer == "react-css"
    # La nueva decisión queda registrada en DECISIONS.md.
    decisions = (project.paths.reports_dir / "DECISIONS.md").read_text(encoding="utf-8")
    assert "tokens" in decisions
    # Volver a correrlo sin cambios no agrega nada.
    assert len(seed_discovery(project, new)) == 3


def test_seed_discovery_conserva_respuestas_con_incertidumbres_renumeradas(project):
    """Las u-00X se renumeran al cambiar el análisis: la identidad es la decisión."""
    variantes = Uncertainty(
        id="u-001",
        question="¿Qué valores pueden tomar las clases dinámicas de `Card`?",
        source="Card.jsx",
        category="variantes",
        options=["Conservar sólo las variantes observadas en el CSS"],
        recommendation="Conservar las variantes observadas.",
    )
    old = AnalysisResult(
        created_at="2026-01-01T00:00:00Z",
        inventory_fingerprint="a",
        components=[ComponentInfo(name="Card", path="Card.jsx", dynamic_classes=True)],
        uncertainties=[variantes],
    )
    questions = seed_discovery(project, old)
    variantes_question = next(q for q in questions if q.category == "análisis:variantes")
    answer_question(project, variantes_question.id, "conservar-solo-las-variantes-observadas-en-el-css")

    # Análisis nuevo: aparece una incertidumbre de tokens antes → la de
    # variantes pasa a ser u-002 y su id de pregunta competiría con u-001.
    new = AnalysisResult(
        created_at="2026-01-02T00:00:00Z",
        inventory_fingerprint="b",
        components=[ComponentInfo(name="Card", path="Card.jsx", dynamic_classes=True)],
        uncertainties=[
            Uncertainty(
                id="u-001",
                question="¿Unificar los colores literales en tokens o conservarlos tal cual (fidelidad estricta)?",
                source="hojas de estilo del lote",
                category="tokens",
                options=["Conservar literales (fidelidad estricta)"],
                recommendation="Conservar literales por defecto.",
            ),
            Uncertainty(**{**variantes.to_dict(), "id": "u-002"}),
        ],
    )
    questions = seed_discovery(project, new)
    ids = [q.id for q in questions]
    assert len(ids) == len(set(ids))  # sin colisión de ids al renumerar
    assert len(questions) == 4  # q-001, q-002 + tokens nueva + variantes conservada
    # La respuesta previa sigue atada a la misma decisión, con el id original.
    kept = next(q for q in questions if q.category == "análisis:variantes")
    assert kept.answer == "conservar-solo-las-variantes-observadas-en-el-css"
    assert kept.id == variantes_question.id
    # La decisión nueva (tokens) entra como pregunta abierta.
    fresh = next(q for q in questions if q.category == "análisis:tokens")
    assert fresh.status == STATUS_OPEN
