"""Convertor JSX/TSX → Astro para componentes estáticos.

Subconjunto conservador y determinista:

- Convierte funciones de componente a ``.astro`` con frontmatter.
- Mapea ``className``→``class``, ``htmlFor``→``for`` y Props→``Astro.props``.
- Reescribe imports de componentes que también se convirtieron a ``.astro``.
- Si detecta constructos no soportados (hooks, handlers en elementos HTML),
  lanza :class:`UnsupportedConversion` y el perfil deja el componente como
  isla React (copia literal + wrapper ``.astro`` con ``client:load``).

No se pretende cubrir todo el espacio JSX: cualquier caso fuera del subconjunto
cae al fallback de isla, que preserva el comportamiento sin reescribirlo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class UnsupportedConversion(Exception):
    """El componente no entra en el subconjunto estático convertible."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class Conversion:
    text: str
    warnings: list[str] = field(default_factory=list)


_IMPORT_STATEMENT_RE = re.compile(
    r"""^\s*import\s+(type\s+)?([^;]+?)\s+from\s+['"]([^'"]+)['"]\s*;?|^\s*import\s+['"]([^'"]+)['"]\s*;?""",
    re.MULTILINE,
)
_INTERFACE_RE = re.compile(r"interface\s+(\w+Props)\s*\{([^}]*)\}", re.DOTALL)
_FUNCTION_RE = re.compile(
    r"(?:export\s+)?function\s+([A-Z]\w*)\s*\(\s*\{([^}]*)\}\s*(?::\s*\w+)?\s*\)"
)
_HOOK_RE = re.compile(r"\buse[A-Z]\w*\s*\(")
_HTML_TAG_RE = re.compile(r"<\s*([a-z][\w-]*)\b([^>]*?)(/?)>", re.DOTALL)
_HANDLER_ATTR_RE = re.compile(r"\bon[A-Z]\w*\s*=")
_COMPONENT_TAG_RE = re.compile(r"<\s*([A-Z]\w*)\b([^>]*?)>", re.DOTALL)
_COMPONENT_HANDLER_ATTR_RE = re.compile(r"\bon[A-Z]\w*\s*=")


def classify(code: str) -> tuple[str, list[str]]:
    """Clasifica el componente: 'island' si hay constructos no convertibles."""
    reasons: list[str] = []
    if _HOOK_RE.search(code):
        reasons.append("usa hooks de React (useState/useEffect/...)")
    for match in _HTML_TAG_RE.finditer(code):
        attrs = match.group(2) or ""
        if _HANDLER_ATTR_RE.search(attrs):
            reasons.append(
                f"handler de evento en elemento HTML `<{match.group(1)}>` "
                "(no soportado en plantillas .astro estáticas)"
            )
    if "dangerouslySetInnerHTML" in code:
        reasons.append("usa dangerouslySetInnerHTML")
    if re.search(r"\bforwardRef\s*\(", code):
        reasons.append("usa forwardRef")
    return ("island", reasons) if reasons else ("static", [])


def _balance_template(text: str, start: int) -> tuple[str, int]:
    """Extrae el template JSX balanceando paréntesis desde ``return (``."""
    depth = 1
    index = start
    quote: str | None = None
    while index < len(text) and depth:
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        index += 1
    if depth != 0:
        raise UnsupportedConversion("no se pudo balancear el paréntesis de return(")
    return text[start : index - 1].strip(), index


def _balance_return_jsx(text: str, start: int) -> tuple[str, int]:
    """Extrae el JSX de un ``return <jsx>;`` sin paréntesis.

    Escáner angular conservador: cuenta ``<``/``>`` fuera de cadenas y termina
    en el ``;`` posterior al cierre del elemento raíz. Si el patrón no encaja
    en el subconjunto (p. ej. un ``<`` textual dentro de contenido), lanza
    :class:`UnsupportedConversion` y el componente cae a isla.
    """
    index = start
    depth = 0
    quote: str | None = None
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'`":
            quote = char
        elif char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
            if depth == 0:
                cursor = index + 1
                while cursor < len(text) and text[cursor] in " \t\r\n":
                    cursor += 1
                if cursor < len(text) and text[cursor] == ";":
                    return text[start : index + 1].strip(), cursor + 1
                if cursor >= len(text):
                    return text[start : index + 1].strip(), cursor
        index += 1
    raise UnsupportedConversion("no se pudo delimitar el JSX de return")


def _rewrite_imports(
    code: str, module_modes: dict[str, str], component_path: str, warnings: list[str]
) -> list[str]:
    from design_pipeline.generators.react_profile import resolve_rel

    statements: list[str] = []
    for match in _IMPORT_STATEMENT_RE.finditer(code):
        is_type = bool(match.group(1))
        clause_raw = match.group(2)
        specifier = match.group(3) or match.group(4)
        if specifier is None:
            continue
        if clause_raw is None:
            # Import de efecto: `import "./estilos.css";`
            statements.append(f'import "{specifier}";')
            continue
        clause = clause_raw.strip()
        if specifier == "react" or specifier.startswith("react/"):
            continue  # innecesario en Astro
        if specifier.startswith("."):
            resolved = resolve_rel(component_path, specifier)
            mode = module_modes.get(resolved) or module_modes.get(resolved + ".tsx") or ""
            if mode == "astro":
                named = re.search(r"{\s*(\w+)\s*}", clause)
                default_name = named.group(1) if named else clause
                statements.append(f'import {default_name} from "{specifier}.astro";')
                continue
            if mode == "tsx" and _COMPONENT_HANDLER_ATTR_RE.search(code):
                warnings.append(
                    f"El componente importa `{specifier}` como isla React dentro de una "
                    "plantilla estática: sin directiva client:* su comportamiento en el "
                    "cliente no se activa (NEEDS_REVIEW)."
                )
        prefix = "import type " if is_type else "import "
        statements.append(f'{prefix}{clause} from "{specifier}";')
    return statements


def convert(name: str, code: str, component_path: str, module_modes: dict[str, str]) -> Conversion:
    """Convierte un componente estático a ``.astro``.

    ``module_modes`` mapea rutas relativas de módulos del lote a su modo
    ('astro' | 'tsx') para reescribir imports entre componentes.
    """
    warnings: list[str] = []

    function_match = _FUNCTION_RE.search(code)
    if not function_match:
        raise UnsupportedConversion("no se encontró una función de componente reconocible")
    component_name = function_match.group(1)
    params = function_match.group(2).strip()

    return_match = re.search(r"\breturn\s*\(", code[function_match.end() :])
    return_word_start = function_match.end() + return_match.start() if return_match else 0
    if return_match:
        return_start = function_match.end() + return_match.end() - 1  # posición del '('
        template, _end = _balance_template(code, return_start + 1)
    else:
        bare_match = re.search(r"\breturn\s*(<)", code[function_match.end() :])
        if not bare_match:
            raise UnsupportedConversion("no se encontró `return` con JSX")
        return_word_start = function_match.end() + bare_match.start()
        jsx_start = function_match.end() + bare_match.end() - 1
        template, _end = _balance_return_jsx(code, jsx_start)
    body_start = function_match.end()
    body_end = return_word_start
    prelude = code[body_start:body_end].strip()

    # Interfaz de props → interface Props en el frontmatter.
    interface_match = _INTERFACE_RE.search(code)
    props_interface = ""
    if interface_match:
        body = interface_match.group(2)
        body = body.replace("React.ReactNode", "any").replace("React.FC", "Function")
        props_interface = "interface Props {" + body + "}"

    imports = _rewrite_imports(code, module_modes, component_path, warnings)

    # Mapeo de parámetros → Astro.props (conserva defaults).
    destructure = ""
    if params:
        destructure = f"const {{ {params} }} = Astro.props;"

    # Transformaciones de plantilla.
    astro_template = template.replace("className=", "class=").replace("htmlFor=", "for=")
    if "className" in astro_template:
        raise UnsupportedConversion("quedaron className sin convertir en la plantilla")

    frontmatter_lines = list(imports)
    if props_interface:
        frontmatter_lines.append(props_interface)
    if prelude:
        frontmatter_lines.append(prelude)
    if destructure:
        frontmatter_lines.append(destructure)

    text = "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n" + astro_template + "\n"
    if component_name != name:
        warnings.append(
            f"El nombre de la función ({component_name}) difiere del nombre del archivo ({name})."
        )
    return Conversion(text=text, warnings=warnings)


def island_wrapper(component_file: str, name: str) -> str:
    """Genera el wrapper .astro de una isla React (fallback de conversión)."""
    return f"""---
// Isla React: este componente conserva comportamiento de cliente (hooks o
// handlers). Requiere la integración @astrojs/react en el proyecto Astro.
// La integración NO se instala automáticamente: agregala manualmente.
import {name} from "./{component_file}";
---

<{name} client:load {{...Astro.props}} />
"""
