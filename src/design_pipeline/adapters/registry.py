"""Registro de adaptadores: detección informativa y ejecución acotada.

Los adaptadores se declaran en la configuración (``agent.adapters``). Este
módulo nunca ejecuta nada salvo que se cumplan **los dos** permisos:

1. ``agent.allow_execution: true`` en la configuración efectiva;
2. el flag ``--allow-execution`` en la línea de comandos.

Además valida la plantilla del comando (solo argumentos literales + los
placeholders conocidos) y captura la salida con redacción de secretos.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from design_pipeline.adapters.base import AgentAdapter
from design_pipeline.errors import DesignPipelineError
from design_pipeline.utils import dotted_get, iso_now, redact, redact_text, sha256_text

KNOWN_PLACEHOLDERS = ("{prompt_file}", "{project}", "{workspace}")
KNOWN_METHODS = ("prompt-file", "stdin")


def list_adapters(config: dict[str, Any]) -> list[AgentAdapter]:
    """Construye los adaptadores declarados en ``agent.adapters``."""
    adapters: list[AgentAdapter] = []
    raw = dotted_get(config, "agent.adapters") or {}
    if not isinstance(raw, dict):
        raise DesignPipelineError("agent.adapters debe ser un mapping {id: {...}}.")
    for adapter_id, spec in raw.items():
        if not isinstance(spec, dict):
            raise DesignPipelineError(f"agent.adapters.{adapter_id} debe ser un mapping.")
        command = spec.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(item, str) for item in command
        ):
            raise DesignPipelineError(
                f"agent.adapters.{adapter_id}.command debe ser una lista de strings no vacía."
            )
        for item in command:
            for placeholder in _placeholders_in(item):
                if placeholder not in KNOWN_PLACEHOLDERS:
                    raise DesignPipelineError(
                        f"agent.adapters.{adapter_id}: placeholder desconocido {placeholder!r}. "
                        f"Permitidos: {', '.join(KNOWN_PLACEHOLDERS)}"
                    )
        prompt_method = str(spec.get("prompt_method", "prompt-file"))
        if prompt_method not in KNOWN_METHODS:
            raise DesignPipelineError(
                f"agent.adapters.{adapter_id}.prompt_method inválido: {prompt_method!r} "
                f"(opciones: {', '.join(KNOWN_METHODS)})"
            )
        adapters.append(
            AgentAdapter(
                id=str(adapter_id),
                label=str(spec.get("label", adapter_id)),
                command=list(command),
                detection=str(spec.get("detection", command[0])),
                prompt_method=prompt_method,
                skills_support=str(spec.get("skills_support", "instructions-in-prompt")),
                interactive=str(spec.get("interactive", "unknown")),
                capabilities=[str(item) for item in spec.get("capabilities", [])],
                limitations=[str(item) for item in spec.get("limitations", [])],
                source="config",
                status="declared-not-tested",
            )
        )
    return adapters


def _placeholders_in(text: str) -> list[str]:
    found: list[str] = []
    index = 0
    while True:
        start = text.find("{", index)
        if start == -1:
            break
        end = text.find("}", start)
        if end == -1:
            break
        found.append(text[start : end + 1])
        index = end + 1
    return found


def detect_adapters(config: dict[str, Any]) -> list[AgentAdapter]:
    """Adaptadores declarados + resolución del ejecutable en PATH (informativo)."""
    adapters = list_adapters(config)
    for adapter in adapters:
        executable = shutil.which(adapter.detection)
        if executable:
            adapter.executable_path = executable
            adapter.status = "detected-not-run"
    return adapters


def get_adapter(config: dict[str, Any], adapter_id: str) -> AgentAdapter:
    for adapter in list_adapters(config):
        if adapter.id == adapter_id:
            return adapter
    available = ", ".join(adapter.id for adapter in list_adapters(config)) or "(ninguno)"
    raise DesignPipelineError(
        f"No existe el adaptador '{adapter_id}'. Declarados: {available}. "
        "Se configuran en agent.adapters (ver docs/AGENT-ADAPTERS.md)."
    )


def build_command(
    adapter: AgentAdapter, prompt_file: Path, project_name: str, workspace: str
) -> list[str]:
    values = {
        "{prompt_file}": str(prompt_file),
        "{project}": project_name,
        "{workspace}": workspace,
    }
    return [item.replace("{prompt_file}", values["{prompt_file}"])
            .replace("{project}", values["{project}"])
            .replace("{workspace}", values["{workspace}"])
            for item in adapter.command]


def run_adapter(
    project: Any,
    adapter_id: str,
    prompt_text: str,
    *,
    allow_execution_flag: bool,
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Ejecuta un adaptador declarado tras el doble permiso.

    Devuelve un resultado con ``exit_code``, rutas de salida y resumen de la
    ejecución. Toda la salida pasa por la redacción de secretos antes de
    guardarse o registrarse en el log.
    """
    config = project.config
    if not bool(dotted_get(config, "agent.allow_execution")):
        raise DesignPipelineError(
            "La ejecución de agentes está deshabilitada: activá "
            "`agent.allow_execution: true` en la configuración."
        )
    if not allow_execution_flag:
        raise DesignPipelineError(
            "Falta el permiso explícito: repetí el comando con --allow-execution."
        )
    adapter = get_adapter(config, adapter_id)
    if not adapter.executable_path and not shutil.which(adapter.command[0]):
        raise DesignPipelineError(
            f"El ejecutable de '{adapter_id}' ({adapter.detection!r}) no está en PATH."
        )

    runs_dir = project.paths.runs_dir / "agent-runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    stamp = iso_now().replace(":", "").replace("-", "")
    prompt_file = runs_dir / f"{stamp}-{adapter.id}.prompt.md"
    prompt_file.write_text(prompt_text, encoding="utf-8")

    command = build_command(
        adapter,
        prompt_file,
        project.name,
        str(project.paths.root.parent),
    )
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "LANG": "C.UTF-8",
    }
    started = time.monotonic()
    # prompt-file: el comando recibe la ruta sustituida. stdin: además se
    # envía el texto por la entrada estándar (el archivo queda como auditoría).
    stdin_payload: str | None = prompt_text if adapter.prompt_method == "stdin" else None
    try:
        proc = subprocess.run(  # noqa: S603 - ejecución aprobada explícitamente por el usuario
            command,
            capture_output=True,
            text=True,
            input=stdin_payload,
            env=env,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise DesignPipelineError(f"Ejecutable no encontrado: {exc}") from exc
    except subprocess.TimeoutExpired:
        return {
            "adapter": adapter.id,
            "status": "timeout",
            "exit_code": None,
            "prompt_file": str(prompt_file),
        }
    duration = round(time.monotonic() - started, 3)

    stdout = redact({"output": proc.stdout})["output"]
    stderr = redact({"output": proc.stderr})["output"]
    result_file = runs_dir / f"{stamp}-{adapter.id}.result.md"
    result_file.write_text(
        f"# Resultado del agente `{adapter.id}`\n\n"
        f"- Fecha: {iso_now()}\n"
        f"- Comando: `{redact_text(' '.join(command))}`\n"
        f"- Código de salida: {proc.returncode}\n"
        f"- Duración: {duration}s\n"
        f"- Prompt (sha256): `{sha256_text(prompt_text)[:16]}…`\n\n"
        f"## stdout (redactado)\n\n```\n{stdout[:20000]}\n```\n\n"
        f"## stderr (redactado)\n\n```\n{stderr[:5000]}\n```\n",
        encoding="utf-8",
    )
    return {
        "adapter": adapter.id,
        "status": "ok" if proc.returncode == 0 else "error",
        "exit_code": proc.returncode,
        "duration_seconds": duration,
        "prompt_file": str(prompt_file),
        "result_file": str(result_file),
        "command": command,
    }
