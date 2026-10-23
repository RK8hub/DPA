"""CSS embebido al final de componentes JSX/TSX (issue #1).

Algunas herramientas de diseño (p. ej. Figma/FigCraft) exportan el CSS
**pegado al final del propio componente**, tras un marcador
``/* nombre.css */``, en vez de un archivo ``.css`` aparte. Sin detección, el
pipeline cometía dos errores en cadena:

1. El ``import "./x.css"`` del componente se reportaba como **referencia rota**
   y el lote se analizaba con **0 hojas de estilo** (sin tokens ni preguntas).
2. ``generate`` copiaba el bloque CSS crudo al final del ``.jsx``/``.tsx``:
   **sintaxis inválida** que ningún bundler compila.

Este módulo detecta el patrón de forma determinista y conservadora:

- El marcador debe ser un comentario de bloque **en su propia línea** que
  nombre un archivo ``.css`` (``/* card-equipment.css */``).
- Todo lo que sigue desde el marcador hasta el final del archivo debe ser
  CSS: llaves balanceadas, al menos una regla y ningún indicador de código
  JS/JSX (``=>``, ``</div>``, ``import``/``export``/``function``/...).

Si el patrón no se puede confirmar, **no se extrae nada**: la función
:func:`find_suspicious_css_tail` permite reportar el caso como pendiente de
revisión humana en lugar de copiar sintaxis inválida en silencio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Comentario de bloque que nombrea un archivo .css, en su propia línea.
_EMBEDDED_MARKER_RE = re.compile(
    r"/\*\s*((?:\.{0,2}/)?[\w.-]+(?:/[\w.-]+)*\.css)\s*\*/"
)

# Indicadores de que lo que sigue al marcador NO es CSS puro (JS/JSX).
# `@import "./x.css";` es CSS válido: el lookbehind descarta la palabra tras @.
_NOT_CSS_RE = re.compile(
    r"</\w|=>|(?<!@)\b(?:import|export|function|return|const|let|await|async)\b"
)

# Bloque con aspecto de declaración CSS (`propiedad: valor;` entre llaves).
_DECLARATION_BLOCK_RE = re.compile(r"\{[^{}]*[-\w]+\s*:\s*[^;{}]+;")


@dataclass
class EmbeddedStylesheet:
    """Un bloque CSS confirmado, embebido al final de un componente."""

    component: str  # ruta del componente (relativa a la raíz de la fuente)
    ref: str  # como está en el marcador: "card-equipment.css"
    resolved: str  # ruta resuelta contra la carpeta del componente
    marker_line: int
    css: str  # texto CSS crudo (sin el marcador)
    start: int  # offset del inicio del marcador en el texto
    end: int  # offset final del bloque


@dataclass
class SuspiciousCssTail:
    """Marcador de CSS cuyo bloque no se pudo confirmar ni separar."""

    ref: str
    marker_line: int


def resolve_relative(from_rel: str, ref: str) -> str:
    """Resuelve ``ref`` (relativo) contra la carpeta de ``from_rel``."""
    base = Path(from_rel).parent
    parts = list(base.parts)
    for part in Path(ref).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _standalone_markers(text: str) -> list[re.Match[str]]:
    """Marcadores que ocupan una línea propia (no en medio de una expresión)."""
    markers = []
    for match in _EMBEDDED_MARKER_RE.finditer(text):
        before = text[: match.start()].rsplit("\n", 1)[-1]
        if before.strip():
            continue
        markers.append(match)
    return markers


def _looks_like_css(tail: str) -> bool:
    """¿Lo que sigue al marcador es solo CSS (reglas con llaves balanceadas)?"""
    clean = re.sub(r"/\*.*?\*/", " ", tail, flags=re.DOTALL).strip()
    if not clean or _NOT_CSS_RE.search(clean):
        return False
    if clean.count("{") == 0 or clean.count("{") != clean.count("}"):
        return False
    depth = 0
    for char in clean:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def find_embedded_stylesheets(component_path: str, text: str) -> list[EmbeddedStylesheet]:
    """Detecta bloques CSS embebidos tras un marcador ``/* *.css */``.

    Sólo se confirma cuando **todo** lo que sigue al marcador (hasta el
    siguiente marcador o el fin del archivo) es CSS: así un comentario que
    sólo nombrea un archivo, o CSS a mitad de archivo seguido de código, no
    se confunden con hojas embebidas.
    """
    found: list[EmbeddedStylesheet] = []
    markers = _standalone_markers(text)
    for index, marker in enumerate(markers):
        tail_end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        tail = text[marker.end() : tail_end]
        if not _looks_like_css(tail):
            continue
        ref = marker.group(1)
        found.append(
            EmbeddedStylesheet(
                component=component_path,
                ref=ref,
                resolved=resolve_relative(component_path, ref),
                marker_line=_line_of(text, marker.start()),
                css=tail.strip() + "\n",
                start=marker.start(),
                end=tail_end,
            )
        )
    return found


def strip_embedded(text: str, embedded: list[EmbeddedStylesheet]) -> str:
    """Devuelve el código del componente sin los bloques CSS embebidos.

    Los bloques embebidos confirmados van, por definición, al final del
    archivo: recortar desde el primero deja el código JSX/TSX compilable y el
    ``import`` del CSS intacto.
    """
    if not embedded:
        return text
    first = min(item.start for item in embedded)
    return text[:first].rstrip() + "\n"


def find_suspicious_css_tail(text: str) -> SuspiciousCssTail | None:
    """Último marcador ``/* *.css */`` cuyo bloque **no** se pudo separar.

    Red de seguridad del issue #1: si el texto tras el marcador tiene
    declaraciones con aspecto de CSS pero no pasa la validación (llaves des-
    balanceadas, código JS mezclado), el archivo **no** se transforma: se
    reporta como NEEDS_REVIEW para revisión humana en lugar de copiar
    sintaxis inválida en silencio.
    """
    markers = _standalone_markers(text)
    if not markers:
        return None
    marker = markers[-1]
    tail = text[marker.end() :]
    if not _looks_like_css(tail) and _DECLARATION_BLOCK_RE.search(
        re.sub(r"/\*.*?\*/", " ", tail, flags=re.DOTALL)
    ):
        return SuspiciousCssTail(ref=marker.group(1), marker_line=_line_of(text, marker.start()))
    return None
