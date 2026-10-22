"""TUI de design-pipeline: asistente interactivo en terminal (solo stdlib).

Reglas del diseño:

- **Sin lógica de negocio**: todo lo que hace esta capa es pedir datos al
  usuario y llamar al mismo motor que la CLI (runner, rules.manager,
  skills.registry, generators.stage, ...).
- Entradas de texto para scripting/automatización: la TUI es opcional.
- Nunca ejecuta código externo: la aprobación de generación y la de
  comandos externos son pedidas explícitamente, y los comandos externos
  solo se habilitan con la misma doble condición que en la CLI.
"""

from design_pipeline.tui.app import run_tui

__all__ = ["run_tui"]
