from __future__ import annotations

from pathlib import Path

import pytest

from design_pipeline.generators.astro_converter import (
    UnsupportedConversion,
    classify,
    convert,
    island_wrapper,
)
from design_pipeline.generators.registry import get_profile, list_profiles
from design_pipeline.generators.stage import run_generate
from tests.helpers import prepared_project

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fixture-export"


def _read(rel: str) -> str:
    return (FIXTURE / rel).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Convertidor
# ---------------------------------------------------------------------------

def test_classify_detecta_islas():
    assert classify(_read("components/Button/Button.tsx"))[0] == "island"   # onClick en <button>
    assert classify(_read("components/Stat/Stat.tsx"))[0] == "island"       # useState + div onClick
    assert classify(_read("components/Card/Card.tsx"))[0] == "static"       # onClick pasa a <Button> (componente)
    assert classify(_read("components/Legacy/Legacy.tsx"))[0] == "static"


def test_classify_motivos():
    _mode, reasons = classify(_read("components/Stat/Stat.tsx"))
    assert any("hooks" in reason for reason in reasons)
    assert any("<div>" in reason for reason in reasons)


def test_convert_card_estatico():
    conversion = convert(
        "Card", _read("components/Card/Card.tsx"), "components/Card/Card.tsx",
        {"components/Button/Button": "tsx"},
    )
    text = conversion.text
    assert text.startswith("---\n")
    assert "interface Props {" in text
    assert 'title: string' in text
    assert "const { title, subtitle, actionLabel, onAction, children } = Astro.props;" in text
    assert 'class="card"' in text or 'className' not in text
    assert "className" not in text.split("---", 2)[2]  # plantilla sin className
    assert 'import React' not in text                  # import de react eliminado
    assert 'import "./Card.css";' in text              # css conservado
    assert 'from "../../assets/logo.svg"' in text      # asset conservado
    # Button queda como isla (.tsx): el import se conserva y se advierte.
    assert 'from "../Button/Button"' in text
    assert any("client:*" in warning or "client" in warning for warning in conversion.warnings)


def test_convert_rescribe_import_a_componente_astro():
    code = '''
import React from "react";
import { Badge } from "../Badge/Badge";
import "./A.css";
export interface AProps { label: string; }
export function A({ label }: AProps) {
  return <article className="a"><Badge label={label} /><label htmlFor="x">X</label></article>;
}
'''
    conversion = convert(
        "A", code, "components/A/A.tsx", {"components/Badge/Badge": "astro"}
    )
    assert 'import Badge from "../Badge/Badge.astro";' in conversion.text
    assert '<label for="x">' in conversion.text


def test_convert_rechaza_templates_no_balanceados():
    code = "export function B({ x }: BProps) { return (<div>{f(}</div>); }"
    with pytest.raises(UnsupportedConversion):
        convert("B", code, "components/B/B.tsx", {})


def test_island_wrapper():
    wrapper = island_wrapper("Stat.tsx", "Stat")
    assert 'import Stat from "./Stat.tsx";' in wrapper
    assert "<Stat client:load {...Astro.props} />" in wrapper
    assert "@astrojs/react" in wrapper


# ---------------------------------------------------------------------------
# Perfiles (integración sobre la fixture)
# ---------------------------------------------------------------------------

def test_registro_de_perfiles():
    ids = {profile["id"] for profile in list_profiles()}
    assert ids == {"react-css", "astro-css"}
    with pytest.raises(Exception):
        get_profile("vue-x")


def test_react_css_genera_copia_fidel(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    profile, result, output_dir = run_generate(project, "react-css")

    # Copia literal del componente fuente.
    generated = (output_dir / "components/Button/Button.tsx").read_text()
    assert generated == _read("components/Button/Button.tsx")
    # CSS y assets referenciados copiados.
    assert (output_dir / "components/Button/Button.css").exists()
    assert (output_dir / "assets/logo.svg").exists()
    # El asset no referenciado queda excluido.
    assert not (output_dir / "assets/sparkline.svg").exists()
    # Barrel y READMEs.
    barrel = (output_dir / "index.ts").read_text()
    assert 'export { Button } from "./components/Button/Button";' in barrel
    assert (output_dir / "components/Button/README.md").exists()
    assert (output_dir / "README.md").exists()
    # Legacy: referencia rota heredada → needs_review.
    assert any("old-styles.css" in item or "sin resolver" in item for item in result.needs_review)
    # La fuente original no cambió.
    assert (FIXTURE / "components/Button/Button.tsx").read_text() == generated


def test_astro_css_conviene_estaticos_y_deja_islas(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    _profile, result, output_dir = run_generate(project, "astro-css")

    # Card (estático) convertido a .astro.
    card = (output_dir / "components/Card/Card.astro").read_text()
    assert card.startswith("---")
    assert "Astro.props" in card
    # Button y Stat quedan como islas React con wrapper.
    assert (output_dir / "components/Button/Button.tsx").exists()
    button_wrapper = (output_dir / "components/Button/Button.astro").read_text()
    assert "client:load" in button_wrapper
    assert (output_dir / "components/Stat/Stat.tsx").exists()
    assert "client:load" in (output_dir / "components/Stat/Stat.astro").read_text()
    # CSS copiado para todos.
    assert (output_dir / "components/Stat/Stat.css").exists()
    # Las islas quedan documentadas para revisión.
    assert any("isla React" in item for item in result.needs_review)
