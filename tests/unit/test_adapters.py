from __future__ import annotations

import sys
from pathlib import Path

import pytest

from design_pipeline.adapters.context import build_context, export_context_pack, render_context_md
from design_pipeline.adapters.registry import (
    detect_adapters,
    get_adapter,
    list_adapters,
    run_adapter,
)
from design_pipeline.config import load_config
from design_pipeline.errors import DesignPipelineError
from tests.helpers import prepared_project

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fixture-export"


def _config(**adapter_spec):
    return {"agent": {"allow_execution": False, "adapters": adapter_spec}}


def test_list_adapters_valida_comando():
    adapters = list_adapters(_config(mi={"command": ["echo", "{prompt_file}", "{project}"]}))
    assert adapters[0].id == "mi"
    assert adapters[0].status == "declared-not-tested"


def test_list_adapters_rechaza_comando_vacio():
    with pytest.raises(DesignPipelineError, match="lista de strings no vacía"):
        list_adapters(_config(mi={"command": []}))


def test_list_adapters_rechaza_placeholder_desconocido():
    with pytest.raises(DesignPipelineError, match="placeholder desconocido"):
        list_adapters(_config(mi={"command": ["echo", "{inventado}"]}))


def test_list_adapters_rechaza_metodo_invalido():
    with pytest.raises(DesignPipelineError, match="prompt_method inválido"):
        list_adapters(_config(mi={"command": ["echo"], "prompt_method": "carrier-pigeon"}))


def test_detect_resuelve_ejecutable():
    adapters = detect_adapters(_config(catito={"command": ["cat", "{prompt_file}"], "detection": "cat"}))
    assert adapters[0].executable_path
    assert adapters[0].status == "detected-not-run"
    adapters = detect_adapters(_config(fantasma={"command": ["no-existe-xyz"], "detection": "no-existe-xyz"}))
    assert adapters[0].executable_path == ""
    assert adapters[0].status == "declared-not-tested"


def test_get_adapter_desconocido():
    with pytest.raises(DesignPipelineError, match="No existe el adaptador"):
        get_adapter(_config(), "otro")


def test_run_adapter_doble_permiso(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    project.config["agent"] = {
        "allow_execution": False,
        "adapters": {"stub": {"command": [sys.executable, "-c", "print('hola')"]}},
    }
    # 1) Config deshabilitada.
    with pytest.raises(DesignPipelineError, match="deshabilitada"):
        run_adapter(project, "stub", "prompt", allow_execution_flag=True)
    # 2) Config habilitada pero sin flag.
    project.config["agent"]["allow_execution"] = True
    with pytest.raises(DesignPipelineError, match="--allow-execution"):
        run_adapter(project, "stub", "prompt", allow_execution_flag=False)


def test_run_adapter_ejecuta_y_captura(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    project.config["agent"] = {
        "allow_execution": True,
        "adapters": {
            "stub": {
                "command": [
                    sys.executable,
                    "-c",
                    "import sys; print('ok-salida'); print('api_key=supersecreta123456', file=sys.stderr)",
                ],
            }
        },
    }
    result = run_adapter(project, "stub", "contexto de prueba", allow_execution_flag=True)
    assert result["status"] == "ok"
    assert result["exit_code"] == 0
    result_file = Path(result["result_file"])
    assert result_file.exists()
    content = result_file.read_text(encoding="utf-8")
    assert "ok-salida" in content
    # El secreto por contenido queda enmascarado en la salida capturada.
    assert "supersecreta123456" not in content
    assert "***REDACTED***" in content
    # El prompt quedó como auditoría.
    assert Path(result["prompt_file"]).read_text(encoding="utf-8") == "contexto de prueba"


def test_run_adapter_metodo_stdin(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    project.config["agent"] = {
        "allow_execution": True,
        "adapters": {
            "stdin-stub": {
                "command": [
                    sys.executable,
                    "-c",
                    "import sys; data = sys.stdin.read(); print('recibido', len(data))",
                ],
                "prompt_method": "stdin",
            }
        },
    }
    result = run_adapter(project, "stdin-stub", "x" * 50, allow_execution_flag=True)
    assert result["status"] == "ok"
    assert "recibido 50" in Path(result["result_file"]).read_text(encoding="utf-8")


def test_run_adapter_sin_ejecutable(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    project.config["agent"] = {
        "allow_execution": True,
        "adapters": {"perdido": {"command": ["no-existe-xyz", "{prompt_file}"], "detection": "no-existe-xyz"}},
    }
    with pytest.raises(DesignPipelineError, match="no está en PATH"):
        run_adapter(project, "perdido", "p", allow_execution_flag=True)


def test_context_pack_exportado(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    paths = export_context_pack(project)
    md = Path(paths["markdown"])
    json_path = Path(paths["json"])
    assert md.exists() and json_path.exists()
    text = md.read_text(encoding="utf-8")
    assert "Estado del pipeline" in text
    assert "Tareas sugeridas de revisión" in text
    assert "No modifiques la exportación original" in text
    # Idempotente: reexportar no falla y conserva la estructura.
    export_context_pack(project)
    assert md.read_text(encoding="utf-8").splitlines()[0].startswith("# Paquete de contexto")


def test_build_context_refleja_estado(tmp_path: Path):
    project = prepared_project(tmp_path, FIXTURE)
    payload = build_context(project)
    assert payload["project"] == "demo"
    assert payload["stages"]["spec"]["status"] == "done"
    assert "Button" in payload["analysis"]["components"]
    rendered = render_context_md(project, payload)
    assert "`Button`" in rendered
