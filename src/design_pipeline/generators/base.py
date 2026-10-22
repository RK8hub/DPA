"""Contrato de los perfiles de generación (etapa F).

Un perfil recibe las especificaciones validadas de la etapa E y escribe el
código de salida en ``output/<perfil>/``, preservando la estructura de
directorios de la fuente para que los imports relativos sigan resolviendo.
El núcleo no conoce detalles de ningún perfil concreto: agregar un destino
nuevo es implementar :class:`Profile` y registrarlo en ``registry.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from design_pipeline.analysis.analyzer import AnalysisResult
from design_pipeline.rules.manager import Rule
from design_pipeline.workspace.project import Project


@dataclass
class GenerationContext:
    project: Project
    source_root: Path
    output_dir: Path
    specs: list[dict[str, Any]]  # especificaciones validadas (dicts)
    analysis: AnalysisResult
    approved_rules: list[Rule]

    def read_source(self, rel_path: str) -> str:
        return (self.source_root / rel_path).read_text(encoding="utf-8", errors="replace")

    def write(self, rel_path: str, content: str) -> None:
        target = self.output_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def copy(self, rel_path: str) -> None:
        source = self.source_root / rel_path
        target = self.output_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


@dataclass
class GeneratedFile:
    path: str
    action: str  # created | copied | transformed
    note: str = ""


@dataclass
class GenerationResult:
    profile: str
    files: list[GeneratedFile] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add(self, path: str, action: str, note: str = "") -> None:
        self.files.append(GeneratedFile(path=path, action=action, note=note))


class Profile(ABC):
    """Interfaz de un perfil de destino."""

    id: str = ""
    label: str = ""
    description: str = ""

    @abstractmethod
    def generate(self, ctx: GenerationContext) -> GenerationResult:
        """Genera el árbol de salida. No debe escribir fuera de ``ctx.output_dir``."""
