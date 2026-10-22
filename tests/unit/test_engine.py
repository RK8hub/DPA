from __future__ import annotations

from pathlib import Path

import pytest

from design_pipeline.engine import stages as stages_mod
from design_pipeline.engine.pipeline import Pipeline
from design_pipeline.engine.state import ProjectState
from design_pipeline.errors import DesignPipelineError, StageOrderError
from design_pipeline.utils import project_slug  # noqa: F401  (sanity import)
from design_pipeline.workspace.project import create_project, load_project
from design_pipeline.config import load_config


def _new_project(tmp_path: Path, name: str = "demo"):
    config = load_config()
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    return create_project(name, ws, config)


def test_state_se_crea_con_las_ocho_etapas(tmp_path: Path):
    project = _new_project(tmp_path)
    state = ProjectState(project=project.name)
    assert set(state.stages) == set(stages_mod.STAGE_IDS)
    assert state.current_stage() == "init"


def test_state_roundtrip(tmp_path: Path):
    project = _new_project(tmp_path)
    state = ProjectState(project=project.name)
    state.stage("init").status = stages_mod.DONE
    state.decisions_pending = ["r-001"]
    path = tmp_path / "state.yaml"
    state.save(path)
    loaded = ProjectState.load(path)
    assert loaded.is_done("init")
    assert loaded.decisions_pending == ["r-001"]


def test_state_rechaza_esquema_desconocido(tmp_path: Path):
    path = tmp_path / "state.yaml"
    path.write_text("schema_version: 999\nproject: demo\n")
    with pytest.raises(DesignPipelineError):
        ProjectState.load(path)


def test_pipeline_exige_prerequisitos(tmp_path: Path):
    project = _new_project(tmp_path)
    pipeline = Pipeline(project)
    with pytest.raises(StageOrderError):
        pipeline.begin("analyze")
    assert pipeline.missing_requirements("analyze") == ["import"]


def test_pipeline_ciclo_basico_y_reanudacion(tmp_path: Path):
    project = _new_project(tmp_path)
    pipeline = Pipeline(project)
    handle = pipeline.begin("init")
    pipeline.complete(handle, artifacts=["project.yaml", "state.yaml"])
    assert pipeline.state.is_done("init")
    assert project.paths.state_yaml.exists()
    # Recarga desde disco: el estado persiste.
    reloaded = load_project(project.name, Path(project.paths.root.parent))
    assert reloaded.load_state().is_done("init")


def test_pipeline_marcobstaculo_stale_al_cambiar_entradas(tmp_path: Path):
    project = _new_project(tmp_path)
    pipeline = Pipeline(project)
    handle = pipeline.begin("init")
    pipeline.complete(handle, artifacts=["project.yaml", "state.yaml"])

    # Simula la etapa de importación con una fuente real.
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.tsx").write_text("export const A = 1;")
    project.set_source(source)
    project.save_data()
    handle_b = pipeline.begin("import")
    pipeline.complete(handle_b, artifacts=["inventory.json"])

    # Cambia la fuente: la etapa import debe quedar obsoleta.
    (source / "b.tsx").write_text("export const B = 2;")
    stale = pipeline.refresh_staleness()
    assert ("import", "cambiaron las entradas 'source-tree'") in stale
    assert pipeline.state.stage("import").status == stages_mod.STALE
    pending = pipeline.resumable()
    assert "import" in pending
