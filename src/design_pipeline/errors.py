"""Excepciones del dominio.

Todas las excepciones públicas heredan de :class:`DesignPipelineError` para que
la CLI pueda traducirlas a mensajes legibles y códigos de salida estables.
"""

from __future__ import annotations


class DesignPipelineError(Exception):
    """Error base del proyecto."""


class ConfigError(DesignPipelineError):
    """Configuración inválita o ilegible."""


class ProjectNotFoundError(DesignPipelineError):
    """El proyecto solicitado no existe en el workspace."""


class ProjectExistsError(DesignPipelineError):
    """Ya existe un proyecto con ese nombre."""


class StageOrderError(DesignPipelineError):
    """Se intentó ejecutar una etapa sin cumplir sus requisitos previos."""


class StageExecutionError(DesignPipelineError):
    """Fallo durante la ejecución de una etapa."""


class ImportSafetyError(DesignPipelineError):
    """La importación detectó una condición insegura y se detuvo."""


class SkillError(DesignPipelineError):
    """Problema con el registro o el contenido de una skill."""


class SchemaValidationError(DesignPipelineError):
    """Un documento no cumple el esquema esperado."""
