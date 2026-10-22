from __future__ import annotations

from pathlib import Path

from design_pipeline.analysis.analyzer import (
    CLASSIFICATION_OBSERVED,
    CLASSIFICATION_PROPOSED,
    analyze_batch,
    parse_component,
    parse_css,
)
from design_pipeline.importers.inventory import build_inventory

TEXT_EXT = [".tsx", ".ts", ".jsx", ".js", ".css", ".json", ".svg", ".md", ".txt"]


def _analyze(fixture_export: Path):
    inv = build_inventory(fixture_export, TEXT_EXT, [], 1024 * 1024)
    return analyze_batch(inv, fixture_export)


BUTTON_TSX = '''
import React from "react";
export interface ButtonProps { variant?: "a" | "b"; onClick?: () => void; }
export function Button({ variant = "a", onClick }: ButtonProps) {
  const classes = ["btn", `btn--${variant}`].filter(Boolean).join(" ");
  return <button className={classes} onClick={onClick} type="button">OK</button>;
}
'''


def test_parse_component_props_y_defaults():
    component = parse_component("Button.tsx", BUTTON_TSX)
    assert component is not None
    assert component.name == "Button"
    prop_names = {p["name"]: p for p in component.props}
    assert prop_names["variant"]["optional"] is True
    assert prop_names["variant"]["type"] == '"a" | "b"'
    assert prop_names["variant"]["default"] == '"a"'
    assert "onClick" in prop_names
    assert component.interactive is True  # onClick en props
    assert component.dynamic_classes is True
    assert "btn" in component.class_literals


def test_parse_component_a11y():
    text = '''
export function Broken() {
  return (
    <div onClick={() => undefined}>
      <img src="x.png" />
      <svg viewBox="0 0 1 1"><rect /></svg>
    </div>
  );
}
'''
    component = parse_component("Broken.tsx", text)
    rules = {item["rule"] for item in component.a11y_findings}
    assert rules == {"img-sin-alt", "click-sin-teclado", "svg-sin-aria"}


def test_parse_css_tokens_y_media():
    css = parse_css(
        "x.css",
        """
/* comentario */
:root { --color-a: #fff; --space-1: 4px; }
.btn { color: #123456; padding: var(--space-1); font-family: Inter, sans-serif; font-size: 14px; }
@media (min-width: 768px) { .btn { padding: 8px; } }
""",
    )
    assert css.custom_properties == {"--color-a": "#fff", "--space-1": "4px"}
    assert "#123456" in css.colors
    assert "btn" in css.class_selectors
    assert css.media_queries[0]["condition"] == "(min-width: 768px)"
    assert ".btn" in css.media_queries[0]["selectors"]


def test_parse_css_ignora_falsos_positivos():
    css = parse_css(
        "x.css",
        ".btn--primary:hover { background: #1f57c4; }\n.a { --real: 1px; }\n",
    )
    assert css.custom_properties == {"--real": "1px"}


def test_analyze_fixture(fixture_export: Path):
    result = _analyze(fixture_export)
    names = {component.name for component in result.components}
    assert names == {"Button", "Card", "Stat", "Legacy"}

    # Relación Card -> Button observada.
    card = next(c for c in result.components if c.name == "Card")
    assert "Button" in card.related
    assert any("img-sin-alt" == item["rule"] for item in card.a11y_findings)

    # Stat es interactivo por useState + onClick.
    stat = next(c for c in result.components if c.name == "Stat")
    assert stat.interactive is True
    assert "useState" in stat.hooks

    # Tokens desde tokens.css.
    assert result.tokens["--color-brand-600"] == "#2f6feb"

    # Clasificación de hallazgos.
    observed = result.by_classification(CLASSIFICATION_OBSERVED)
    assert any("Componente `Button`" in f.message for f in observed)
    proposed = result.by_classification(CLASSIFICATION_PROPOSED)
    assert any("Colores literales" in f.message for f in proposed)

    # Limitación por referencia rota de Legacy.
    assert any("old-styles.css" in item for item in result.limitations)

    # Sparkline.svg sin referencias.
    assert "assets/sparkline.svg" in result.unused_assets


def test_analisis_no_afirma_intercambiability(fixture_export: Path):
    result = _analyze(fixture_export)
    for dup in result.duplications:
        assert dup["status"] == "needs_review"
