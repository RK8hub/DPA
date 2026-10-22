"""Interfaz común de adaptadores de agentes de terminal (sección 6 del spec).

Un adaptador declara, sin ejecutar nada:

- comando ejecutable y método de detección;
- cómo se pasa el prompt/contexto (archivo temporal, stdin, ...);
- soporte declarado de skills/instrucciones;
- modos interactivo/no interactivo;
- capacidades y limitaciones;
- cómo se captura el resultado (siempre con redacción de secretos).

La ejecución real está tras un doble permiso (configuración
``agent.allow_execution`` + flag ``--allow-execution``) y queda registrada en
el log. El núcleo funciona sin agente: ``design-pipeline context`` exporta un
paquete de contexto cargable manualmente.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentAdapter:
    id: str
    label: str
    command: list[str]  # plantilla con {prompt_file} y {project}
    detection: str  # ejecutable a buscar en PATH ("" = solo config)
    prompt_method: str  # "prompt-file" | "stdin"
    skills_support: str  # "instructions-in-prompt" | "none"
    interactive: str  # "yes" | "no" | "unknown"
    capabilities: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    result_capture: str = "stdout+stderr (redactado) a runs/agent-runs/"
    source: str = "config"  # config | builtin
    status: str = "declared-not-tested"  # declared-not-tested | detected-not-run | tested-with-stub
    executable_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
