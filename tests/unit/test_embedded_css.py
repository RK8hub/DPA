"""Pruebas del detector de CSS embebido al final de componentes (issue #1)."""

from __future__ import annotations

from pathlib import Path

from design_pipeline.importers.embedded_css import (
    find_embedded_stylesheets,
    find_suspicious_css_tail,
    strip_embedded,
)

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fixture-embedded-css"

COMPONENT = '''import React from "react";
import "./card.css";

export function Card({ title = "Card" }) {
  return <article className="card"><h2 className="card__title">{title}</h2></article>;
}

/* card.css */
.card {
  padding: 16px;
  background: #101828;
  color: #f9fafb;
}

.card__title {
  font-size: 18px;
  color: #e4e7ec;
}
'''


def test_detecta_bloque_embebido_al_final():
    found = find_embedded_stylesheets("components/Card/Card.jsx", COMPONENT)
    assert len(found) == 1
    sheet = found[0]
    assert sheet.ref == "card.css"
    assert sheet.resolved == "components/Card/card.css"
    assert sheet.marker_line == 8
    assert ".card {" in sheet.css
    assert "/* card.css */" not in sheet.css


def test_strip_deja_el_jsx_compilable():
    found = find_embedded_stylesheets("Card.jsx", COMPONENT)
    code = strip_embedded(COMPONENT, found)
    # El import queda intacto y el bloque CSS desaparece.
    assert 'import "./card.css";' in code
    assert "/* card.css */" not in code
    assert "background" not in code
    assert code.rstrip().endswith("}")
    assert code.endswith("\n")


def test_strip_sin_embebido_no_cambia_nada():
    text = "export function A() { return null; }\n"
    assert strip_embedded(text, []) == text


def test_no_detecta_css_a_mitad_de_archivo():
    """Un marcador seguido de código JS no es CSS embebido."""
    text = '''/* theme.css */
export function A() {
  return <div className="a">{"x"}</div>;
}
'''
    assert find_embedded_stylesheets("A.jsx", text) == []


def test_no_detecta_comentario_que_solo_nombra_un_archivo():
    text = '''import "./a.css";
export function A() {
  return <div className="a" />;
}
/* ver docs/estilos.css para más detalle */
'''
    assert find_embedded_stylesheets("A.jsx", text) == []


def test_no_detecta_cola_vacia():
    text = 'export function A() { return null; }\n/* a.css */\n'
    assert find_embedded_stylesheets("A.jsx", text) == []


def test_no_detecta_llaves_desbalanceadas():
    text = '''export function A() { return <div className="a" />; }
/* a.css */
.a { color: #fff;
'''
    assert find_embedded_stylesheets("A.jsx", text) == []


def test_import_at_valido_no_invalida_la_deteccion():
    """`@import "./tokens.css";` es CSS válido: no debe romper la detección."""
    text = '''export function A() { return <div className="a" />; }

/* a.css */
@import "./tokens.css";
.a { color: #fff; }
'''
    found = find_embedded_stylesheets("A.jsx", text)
    assert len(found) == 1
    assert '@import "./tokens.css";' in found[0].css


def test_dos_marcadores_consecutivos():
    text = '''export function A() { return <div />; }

/* a.css */
.a { color: #fff; }

/* b.css */
.b { color: #000; }
'''
    found = find_embedded_stylesheets("A.jsx", text)
    assert [sheet.ref for sheet in found] == ["a.css", "b.css"]
    assert ".a {" in found[0].css and ".b {" not in found[0].css
    assert ".b {" in found[1].css


def test_resuelve_en_subdirectorio():
    text = 'export function A() { return null; }\n/* styles/x.css */\n.x { color: #fff; }\n'
    found = find_embedded_stylesheets("components/A/A.jsx", text)
    assert found[0].resolved == "components/A/styles/x.css"


# ---------------------------------------------------------------------------
# Red de seguridad: colas sospechosas (issue #1: nada inválido en silencio)
# ---------------------------------------------------------------------------

def test_sospechoso_detecta_cola_no_separable():
    text = (FIXTURE / "Broken.jsx").read_text(encoding="utf-8")
    suspicious = find_suspicious_css_tail(text)
    assert suspicious is not None
    assert suspicious.ref == "broken.css"
    assert suspicious.marker_line == 8


def test_no_sospecha_de_un_componente_normal():
    assert find_suspicious_css_tail(COMPONENT) is None


def test_no_sospecha_sin_marcador():
    assert find_suspicious_css_tail("export function A() { return null; }") is None


def test_no_sospecha_de_marcador_sin_cola():
    assert find_suspicious_css_tail("export function A() {}\n/* a.css */\n") is None


def test_fixture_embebido_detecta_los_dos_validos():
    for name, ref in (("Panel.jsx", "panel.css"), ("Toolbar.jsx", "toolbar.css")):
        text = (FIXTURE / name).read_text(encoding="utf-8")
        found = find_embedded_stylesheets(name, text)
        assert [sheet.ref for sheet in found] == [ref]
        assert found[0].resolved == ref  # componentes en la raíz de la fuente
