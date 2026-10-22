from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from design_pipeline.config import load_config
from design_pipeline.errors import SkillError
from design_pipeline.skills.registry import (
    add_skill,
    active_skills_for_stage,
    discover_skills,
    find_skill,
    parse_frontmatter,
    remove_skill,
    seed_internal_skills,
    set_skill_enabled,
    validate_skill_dir,
)
from design_pipeline.workspace.project import create_project

VALID_SKILL = """---
name: demo-skill
description: "Descripción de prueba válida."
version: 0.1.0
mode: instructive
permissions: [read-workspace]
tools: []
stages: [report]
scripts: []
---

# Demo skill

Instrucciones suficientemente largas para pasar la advertencia de longitud
mínima del validador y servir de ejemplo en pruebas.
"""


@pytest.fixture
def project(tmp_path: Path):
    config = load_config()
    ws = tmp_path / "ws"
    ws.mkdir()
    return create_project("demo", ws, config)


def _make_skill(tmp_path: Path, content: str = VALID_SKILL, name: str = "demo") -> Path:
    src = tmp_path / name
    src.mkdir(exist_ok=True)
    (src / "SKILL.md").write_text(content, encoding="utf-8")
    return src


def test_frontmatter_valido():
    meta, body = parse_frontmatter(VALID_SKILL)
    assert meta["name"] == "demo-skill"
    assert meta["stages"] == ["report"]
    assert body.startswith("# Demo skill")


def test_frontmatter_yaml_roto_lanza_error_controlado():
    broken = "---\nname: x\ndescription: con: dos.puntos malos\n---\nCuerpo\n"
    with pytest.raises(SkillError):
        parse_frontmatter(broken)


def test_validate_skill_dir_valida(tmp_path: Path):
    validation = validate_skill_dir(_make_skill(tmp_path))
    assert validation.ok
    assert validation.errors == []
    assert validation.record is not None
    assert validation.record.name == "demo-skill"


def test_validate_skill_dir_falla_sin_description(tmp_path: Path):
    src = _make_skill(
        tmp_path,
        VALID_SKILL.replace('description: "Descripción de prueba válida."\n', ""),
    )
    validation = validate_skill_dir(src)
    assert not validation.ok
    assert any("description" in error for error in validation.errors)


def test_validate_skill_dir_nombre_discrepancia(tmp_path: Path):
    validation = validate_skill_dir(_make_skill(tmp_path), assumed_name="otro-nombre")
    assert not validation.ok
    assert any("no coincide" in error for error in validation.errors)


def test_validate_etapa_desconocida(tmp_path: Path):
    src = _make_skill(tmp_path, VALID_SKILL.replace("stages: [report]", "stages: [no-existe]"))
    validation = validate_skill_dir(src)
    assert not validation.ok
    assert any("etapa desconocida" in error for error in validation.errors)


def test_validate_script_inseguro(tmp_path: Path):
    src = _make_skill(
        tmp_path,
        VALID_SKILL.replace("scripts: []", "scripts: ['../../etc/passwd']"),
    )
    validation = validate_skill_dir(src)
    assert not validation.ok
    assert any("insegura" in error for error in validation.errors)


def test_validate_executive_genera_advertencia(tmp_path: Path):
    src = _make_skill(tmp_path, VALID_SKILL.replace("mode: instructive", "mode: executive"))
    validation = validate_skill_dir(src)
    assert validation.ok
    assert any("executive" in warning for warning in validation.warnings)


def test_seed_internal_skills(project):
    enabled = seed_internal_skills(project)
    assert "analyze-batch" in enabled
    assert "validate-output" in enabled
    assert set(enabled) == set(project.enabled_skills)


def test_add_skill_copia_sin_bit_ejecucion(project, tmp_path: Path):
    src = _make_skill(tmp_path)
    (src / "run.sh").write_text("#!/bin/sh\necho hola\n")
    (src / "run.sh").chmod(0o755)  # el origen SÍ tiene bit de ejecución
    config = project.config

    record = add_skill(src, project, config, target="project")
    assert record.origin == "project"
    dest = Path(record.path)
    assert (dest / "SKILL.md").exists()
    # La copia NO hereda el bit de ejecución.
    mode = (dest / "run.sh").stat().st_mode
    assert not mode & stat.S_IXUSR
    # Procedencia y hashes registrados, sin ejecución.
    meta = (dest / "skill.yaml").read_text(encoding="utf-8")
    assert "imported_at" in meta
    assert "file_sha256" in meta
    assert "run.sh" in meta
    assert "scripts_executed_on_import: false" in meta


def test_add_skill_duplicada_no_sobrescribe(project, tmp_path: Path):
    src = _make_skill(tmp_path)
    config = project.config
    add_skill(src, project, config, target="project")
    with pytest.raises(SkillError, match="No se sobrescribe"):
        add_skill(src, project, config, target="project")


def test_add_skill_executive_rechazada_sin_config(project, tmp_path: Path):
    src = _make_skill(tmp_path, VALID_SKILL.replace("mode: instructive", "mode: executive"))
    config = dict(project.config)
    config["skills.allow_executive"] = False
    with pytest.raises(SkillError, match="executive"):
        add_skill(src, project, config, target="project")


def test_add_skill_rechaza_symlink(project, tmp_path: Path):
    src = _make_skill(tmp_path)
    target = tmp_path / "fuera.txt"
    target.write_text("secreto")
    (src / "enlace.txt").symlink_to(target)
    with pytest.raises(SkillError, match="Symlink"):
        add_skill(src, project, project.config, target="project")


def test_enable_disable_y_activacion_por_etapa(project, tmp_path: Path):
    src = _make_skill(tmp_path)
    add_skill(src, project, project.config, target="project")
    # Deshabilitada por defecto: no aparece activa en ninguna etapa.
    assert active_skills_for_stage(project, "report") == []
    set_skill_enabled(project, "demo-skill", True)
    active = active_skills_for_stage(project, "report")
    assert [record.name for record in active] == ["demo-skill"]
    # No declara la etapa analyze → no activa ahí.
    assert active_skills_for_stage(project, "analyze") == []
    set_skill_enabled(project, "demo-skill", False)
    assert active_skills_for_stage(project, "report") == []


def test_discover_internas_y_find(project):
    records = discover_skills(project, project.config)
    origins = {record.origin for record in records}
    assert "internal" in origins
    found = find_skill(project, project.config, "analyze-batch")
    assert found is not None and found.origin == "internal"


def test_remove_skill_requiere_confirmacion_y_no_toca_internas(project):
    with pytest.raises(SkillError, match="destructivo"):
        remove_skill(project, project.config, "analyze-batch", confirm=False)
    with pytest.raises(SkillError, match="no se pueden eliminar"):
        remove_skill(project, project.config, "analyze-batch", confirm=True)
