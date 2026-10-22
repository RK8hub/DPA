from __future__ import annotations

from pathlib import Path

from design_pipeline.importers.inventory import (
    build_inventory,
    extract_references,
    _resolve_relative,
)

TEXT_EXT = [".tsx", ".ts", ".jsx", ".js", ".css", ".json", ".svg", ".md", ".txt"]
EXCLUSIONS = ["node_modules", ".git", "dist"]


def _inventory(source: Path):
    return build_inventory(source, TEXT_EXT, EXCLUSIONS, max_file_size_bytes=1024 * 1024)


def test_inventario_fixture(fixture_export: Path):
    inv = _inventory(fixture_export)
    paths = {entry.path for entry in inv.files}
    assert "components/Button/Button.tsx" in paths
    assert "styles/tokens.css" in paths
    by_cat = inv.stats["by_category"]
    assert by_cat["component"] == 4  # Button, Card, Stat, Legacy
    assert by_cat["style"] == 4      # 3 CSS de componentes + tokens
    assert by_cat["vector"] == 2


def test_inventario_detecta_referencia_rota(fixture_export: Path):
    inv = _inventory(fixture_export)
    broken = {(item["from"], item["ref"]) for item in inv.broken_references}
    assert ("components/Legacy/Legacy.tsx", "./old-styles.css") in broken
    # Card importa Button y assets que sí existen: no debe aparecer como roto.
    assert ("components/Card/Card.tsx", "../Button/Button") not in broken


def test_inventario_detecta_paquetes_y_rutas(fixture_export: Path):
    inv = _inventory(fixture_export)
    externals = {item["ref"] for item in inv.external_references}
    assert "react" in externals
    assert "./Button.css" not in externals
    assert "../../assets/logo.svg" not in externals


def test_inventario_no_modifica_la_fuente(copied_export: Path):
    before = {p: p.read_bytes() for p in copied_export.rglob("*") if p.is_file()}
    _inventory(copied_export)
    after = {p: p.read_bytes() for p in copied_export.rglob("*") if p.is_file()}
    assert before == after


def test_exclusiones_y_duplicados(tmp_path: Path):
    root = tmp_path / "batch"
    (root / "node_modules" / "pkg").mkdir(parents=True)
    (root / "node_modules" / "pkg" / "index.js").write_text("x")
    (root / "a").mkdir()
    (root / "b").mkdir()
    (root / "a" / "same.tsx").write_text("export const A = 1;")
    (root / "b" / "same.tsx").write_text("export const A = 1;")
    inv = _inventory(root)
    paths = {entry.path for entry in inv.files}
    assert not any(path.startswith("node_modules") for path in paths)
    assert len(inv.duplicate_groups) == 1
    assert set(inv.duplicate_groups[0]["paths"]) == {"a/same.tsx", "b/same.tsx"}


def test_archivo_grande_no_se_analiza(tmp_path: Path):
    root = tmp_path / "big"
    root.mkdir()
    (root / "big.css").write_text("/* padding */" + " " * 4096)
    inv = build_inventory(root, TEXT_EXT, [], max_file_size_bytes=1024)
    entry = inv.files[0]
    assert entry.analyzed is False
    assert "supera el máximo" in entry.reason


def test_resolve_relative_rechaza_traversal():
    assert _resolve_relative("components/A.tsx", "./B.css") == "components/B.css"
    assert _resolve_relative("components/A.tsx", "../styles/t.css") == "styles/t.css"
    assert _resolve_relative("A.tsx", "../../fuera.txt") is None


def test_extract_references_varios_patrones():
    text = (
        'import React from "react";\n'
        'import { A } from "./A";\n'
        'const b = require("./b");\n'
        '<img src="./img.png" />\n'
    )
    refs = extract_references(text, "component")
    assert refs == ["react", "./A", "./b", "./img.png"]


def test_extract_references_css_url():
    refs = extract_references('.a { background: url("./bg.png"); }', "style")
    assert refs == ["./bg.png"]
