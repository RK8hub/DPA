"""Etapa C: análisis determinista del lote importado.

El análisis es estático y determinista: no ejecuta código de la exportación ni
requiere un LLM. Separa explícitamente hallazgos Observados (respaldados por
los archivos), Inferidos (interpretación razonable con justificación),
Propuestos (cambios sugeridos) y Pendientes (preguntas para un humano).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from design_pipeline.importers.embedded_css import (
    find_embedded_stylesheets,
    find_suspicious_css_tail,
)
from design_pipeline.importers.inventory import FileEntry, Inventory

CLASSIFICATION_OBSERVED = "observed"
CLASSIFICATION_INFERRED = "inferred"
CLASSIFICATION_PROPOSED = "proposed"
CLASSIFICATION_PENDING = "pending"

CLASSIFICATION_LABELS = {
    CLASSIFICATION_OBSERVED: "Observado",
    CLASSIFICATION_INFERRED: "Inferido",
    CLASSIFICATION_PROPOSED: "Propuesto",
    CLASSIFICATION_PENDING: "Pendiente",
}


@dataclass
class Finding:
    kind: str
    classification: str
    message: str
    source: str
    justification: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Uncertainty:
    id: str
    question: str
    source: str
    category: str = "general"
    options: list[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ComponentInfo:
    name: str
    path: str
    export_default: bool = False
    props: list[dict[str, Any]] = field(default_factory=list)
    type_aliases: dict[str, str] = field(default_factory=dict)
    hooks: list[str] = field(default_factory=list)
    interactive: bool = False
    class_literals: list[str] = field(default_factory=list)
    dynamic_classes: bool = False
    local_imports: list[str] = field(default_factory=list)
    package_imports: list[str] = field(default_factory=list)
    style_imports: list[str] = field(default_factory=list)
    asset_imports: list[str] = field(default_factory=list)
    a11y_findings: list[dict[str, Any]] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CssInfo:
    path: str
    custom_properties: dict[str, str] = field(default_factory=dict)
    class_selectors: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    media_queries: list[dict[str, Any]] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    font_families: list[str] = field(default_factory=list)
    font_sizes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    created_at: str
    inventory_fingerprint: str
    components: list[ComponentInfo] = field(default_factory=list)
    stylesheets: list[CssInfo] = field(default_factory=list)
    tokens: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    uncertainties: list[Uncertainty] = field(default_factory=list)
    duplications: list[dict[str, Any]] = field(default_factory=list)
    unused_assets: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "inventory_fingerprint": self.inventory_fingerprint,
            "components": [component.to_dict() for component in self.components],
            "stylesheets": [css.to_dict() for css in self.stylesheets],
            "tokens": self.tokens,
            "findings": [finding.to_dict() for finding in self.findings],
            "uncertainties": [uncertainty.to_dict() for uncertainty in self.uncertainties],
            "duplications": self.duplications,
            "unused_assets": self.unused_assets,
            "limitations": self.limitations,
        }

    def by_classification(self, classification: str) -> list[Finding]:
        return [f for f in self.findings if f.classification == classification]


# ---------------------------------------------------------------------------
# Parsing de componentes (JSX/TSX)
# ---------------------------------------------------------------------------

_FUNC_RE = re.compile(
    r"export\s+(?:default\s+)?(?:function\s+([A-Z]\w*)|const\s+([A-Z]\w*)\s*=)"
)
_INTERFACE_RE = re.compile(r"interface\s+(\w+Props)\s*\{([^}]*)\}", re.DOTALL)
_PROP_FIELD_RE = re.compile(r"(\w+)(\??)\s*:\s*([^;]+);?")
_HOOK_RE = re.compile(r"\b(use[A-Z]\w*)\s*\(")
_CLASSNAME_LITERAL_RE = re.compile(r"""className=\{?["'`]([^"'`$]*)["'`]""")
_IMPORT_LINE_RE = re.compile(r"""(?:import|export)\s+[^'";]*?from\s+['"]([^'"]+)['"]|import\s+['"]([^'"]+)['"]""")
_ATTR_RE = re.compile(r"""\b([a-zA-Z]+)=(["'{])""")
_ONPROP_RE = re.compile(r"\bon[A-Z]\w*")

# Elementos interactivos por defecto en HTML.
_INTERACTIVE_TAGS = {"button", "a", "input", "select", "textarea", "summary", "label"}

_A11Y_IMG_NO_ALT = re.compile(r"<img\b(?![^>]*\balt=)[^>]*>", re.DOTALL)
_A11Y_CLICKABLE = re.compile(
    r"<(div|span|article|section|li|p)\b[^>]*\bonClick\b[^>]*>", re.DOTALL
)
_A11Y_SVG = re.compile(r"<svg\b[^>]*>", re.DOTALL)
_A11Y_INPUT_NO_LABEL = re.compile(r"<input\b(?![^>]*(?:aria-label|id=))[^>]*>", re.DOTALL)

# className con expresión (no literal): className={classes}, className={`x ${y}`}
_DYNAMIC_CLASSNAME_RE = re.compile(r"className=\{(?!['\"`])([^}]*)\}")
_TEMPLATE_INLINE_RE = re.compile(r"""["'`]([^"'`]+)["'`]""")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def parse_component(path: str, text: str) -> ComponentInfo | None:
    """Extrae información de un archivo JSX/TSX. None si no parece componente."""
    match = _FUNC_RE.search(text)
    if not match:
        return None
    name = match.group(1) or match.group(2)
    info = ComponentInfo(name=name, path=path, export_default="default" in text[match.start() :])

    # Comentarios: se eliminan solo para el parseo de props/params (los
    # hallazgos de accesibilidad conservan el texto original con sus números
    # de línea).
    text_nocomments = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    text_nocomments = re.sub(r"//[^\n]*", " ", text_nocomments)

    # Alias de tipos (type X = "a" | "b") para resolver uniones nombradas.
    for alias in re.finditer(r"type\s+(\w+)\s*=\s*([^;]+);", text_nocomments):
        info.type_aliases[alias.group(1)] = alias.group(2).strip()

    # Props desde interface XxxProps (el cuerpo puede ser de una sola línea).
    for iface in _INTERFACE_RE.finditer(text_nocomments):
        for field_match in _PROP_FIELD_RE.finditer(iface.group(2)):
            prop_type = field_match.group(3).strip()
            info.props.append(
                {
                    "name": field_match.group(1),
                    "optional": bool(field_match.group(2)),
                    "type": prop_type,
                }
            )

    # Defaults desde destructuring en los parámetros: busca `{...}` tras el nombre.
    param_match = re.search(rf"{name}\s*\(\s*(\{{[^}}]*\}})", text_nocomments, re.DOTALL)
    if param_match:
        destructure = param_match.group(1)[1:-1]
        for token in destructure.split(","):
            token = token.strip()
            if not token:
                continue
            default_match = re.match(r"(\w+)\s*=\s*([^,]+)", token)
            prop_name = default_match.group(1) if default_match else token.split(":")[0].strip()
            if prop_name and not any(p["name"] == prop_name for p in info.props):
                info.props.append(
                    {
                        "name": prop_name,
                        "optional": bool(default_match),
                        "type": "unknown (destructuring)",
                    }
                )
            if default_match:
                for prop in info.props:
                    if prop["name"] == prop_name:
                        prop["default"] = default_match.group(2).strip()

    # Hooks e interactividad: hooks de React o props de eventos (on*).
    info.hooks = sorted(set(_HOOK_RE.findall(text)))
    info.interactive = bool(info.hooks) or any(
        _ONPROP_RE.fullmatch(prop["name"]) for prop in info.props
    )

    # Clases: literales y construcciones dinámicas.
    for class_match in _CLASSNAME_LITERAL_RE.finditer(text):
        for token in class_match.group(1).split():
            if token and token not in info.class_literals:
                info.class_literals.append(token)
    # className={expr}: detecta dinamismo y, si expr es un identificador con
    # asignación tipo ["btn", `btn--${variant}`], extrae los fragmentos estáticos.
    for dynamic in _DYNAMIC_CLASSNAME_RE.finditer(text):
        info.dynamic_classes = True
        expr = dynamic.group(1).strip()
        ident = re.fullmatch(r"(\w+)", expr)
        scope_text = text
        if ident:
            assign = re.search(
                rf"(?:const|let|var)\s+{ident.group(1)}\s*=\s*(\[[^\]]*\])", text, re.DOTALL
            )
            if assign:
                scope_text = assign.group(1)
        for piece in _TEMPLATE_INLINE_RE.finditer(scope_text):
            fragment = piece.group(1).strip()
            if not fragment or "${" in fragment:
                continue  # fragmentos con interpolación: no son clases concretas
            for token in fragment.split():
                if token not in info.class_literals:
                    info.class_literals.append(token)
    # Template literal inline también cuenta como dinámico.
    if re.search(r"""className=\{`""", text):
        info.dynamic_classes = True
    # Clases literales en JSX multilinea (componentes sin className={...}).
    for literal in re.findall(r"""className=["']([^"']+)["']""", text):
        for token in literal.split():
            if token not in info.class_literals:
                info.class_literals.append(token)

    # Imports.
    for import_match in _IMPORT_LINE_RE.finditer(text):
        ref = import_match.group(1) or import_match.group(2)
        if not ref:
            continue
        line = _line_of(text, import_match.start())
        if not ref.startswith("."):
            info.package_imports.append(ref)
        elif ref.endswith((".css", ".scss")):
            info.style_imports.append(f"{ref} (línea {line})")
            info.local_imports.append(ref)
        elif re.search(r"\.(svg|png|jpe?g|gif|webp|avif|ico|woff2?|ttf|otf)$", ref):
            info.asset_imports.append(f"{ref} (línea {line})")
            info.local_imports.append(ref)
        else:
            info.local_imports.append(f"{ref} (línea {line})")

    # Accesibilidad.
    for img in _A11Y_IMG_NO_ALT.finditer(text):
        info.a11y_findings.append(
            {
                "rule": "img-sin-alt",
                "line": _line_of(text, img.start()),
                "detail": "<img> sin atributo alt",
            }
        )
    for clickable in _A11Y_CLICKABLE.finditer(text):
        info.a11y_findings.append(
            {
                "rule": "click-sin-teclado",
                "line": _line_of(text, clickable.start()),
                "detail": f"<{clickable.group(1)}> con onClick sin manejo de teclado (Enter/Espacio)",
            }
        )
    for svg in _A11Y_SVG.finditer(text):
        tag = svg.group(0)
        if not re.search(r"aria-hidden|role=|<title", tag) and "<title" not in text[svg.start() : svg.start() + 400]:
            info.a11y_findings.append(
                {
                    "rule": "svg-sin-aria",
                    "line": _line_of(text, svg.start()),
                    "detail": "<svg> sin aria-hidden, role ni <title>",
                }
            )
    for field in _A11Y_INPUT_NO_LABEL.finditer(text):
        info.a11y_findings.append(
            {
                "rule": "input-sin-label",
                "line": _line_of(text, field.start()),
                "detail": "<input> sin aria-label ni id asociado",
            }
        )
    return info


# ---------------------------------------------------------------------------
# Parsing de CSS
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CUSTOM_PROP_RE = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")
_RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_COLOR_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\([^)]*\)", re.IGNORECASE
)
# Propiedades CSS que pueden llevar un color (sin los dos puntos: ya se separó).
_DECL_COLOR_RE = re.compile(r"^(?:color|background|border\w*|fill|stroke)$", re.IGNORECASE)


def _extract_media_blocks(text: str) -> list[tuple[str, str, int, int]]:
    """Extrae bloques @media con un escáner de llaves (soporta anidamiento).

    Devuelve (condición, cuerpo, inicio, fin) por cada bloque.
    """
    blocks: list[tuple[str, str, int, int]] = []
    index = 0
    while True:
        start = text.find("@media", index)
        if start == -1:
            break
        brace = text.find("{", start)
        if brace == -1:
            break
        condition = " ".join(text[start + len("@media") : brace].split())
        depth = 1
        cursor = brace + 1
        while cursor < len(text) and depth:
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
            cursor += 1
        if depth != 0:  # CSS malformado: ignoramos el bloque restante.
            break
        body = text[brace + 1 : cursor - 1]
        blocks.append((condition, body, start, cursor))
        index = cursor
    return blocks


def parse_css(path: str, text: str) -> CssInfo:
    clean = _COMMENT_RE.sub("", text)
    info = CssInfo(path=path)

    for match in _CUSTOM_PROP_RE.finditer(clean):
        # Frontera de declaración: solo cuentan al inicio de un bloque o tras
        # otro `;`. Evita falsos positivos como `.btn--primary:hover {...}`.
        before = clean[: match.start()].rstrip()
        if before and before[-1] not in "{;":
            continue
        info.custom_properties[match.group(1).strip()] = match.group(2).strip()

    def _ingest_rule(selector: str, body: str, media: str | None = None) -> None:
        declarations: list[dict[str, str]] = []
        for decl in body.split(";"):
            if ":" not in decl:
                continue
            prop, value = decl.split(":", 1)
            declarations.append({"property": prop.strip(), "value": value.strip()})
        for class_match in re.finditer(r"\.([\w-]+)", selector):
            info.class_selectors.setdefault(class_match.group(1), []).append(
                {
                    "selector": selector.strip(),
                    "media": media or "",
                    "declarations": declarations,
                }
            )
        for decl in declarations:
            if _DECL_COLOR_RE.match(decl["property"]):
                for color in _COLOR_RE.findall(decl["value"]):
                    if color not in info.colors:
                        info.colors.append(color)
            if decl["property"] == "font-family":
                info.font_families.append(decl["value"])
            if decl["property"] == "font-size":
                info.font_sizes.append(decl["value"])

    media_blocks = _extract_media_blocks(clean)

    # Reglas fuera de media queries: se elimina cada bloque y se parsea el resto.
    stripped = clean
    for _condition, _body, start, end in reversed(media_blocks):
        stripped = stripped[:start] + " " * (end - start) + stripped[end:]
    for match in _RULE_RE.finditer(stripped):
        _ingest_rule(match.group(1), match.group(2))

    # Reglas dentro de media queries.
    for condition, body, _start, _end in media_blocks:
        selectors: list[str] = []
        for inner in _RULE_RE.finditer(body):
            selectors.append(inner.group(1).strip())
            _ingest_rule(inner.group(1), inner.group(2), media=condition)
        info.media_queries.append({"condition": condition, "selectors": selectors})

    # Deduplicar listas.
    info.font_families = list(dict.fromkeys(info.font_families))
    info.font_sizes = list(dict.fromkeys(info.font_sizes))
    info.colors = list(dict.fromkeys(info.colors))
    return info


def css_declarations_for_class(css: CssInfo, class_name: str) -> list[dict[str, Any]]:
    """Reglas que afectan a una clase, incluyendo media queries."""
    results: list[dict[str, Any]] = []
    for rule in css.class_selectors.get(class_name, []):
        results.append({"selector": rule["selector"], "media": rule["media"]})
    return results


# ---------------------------------------------------------------------------
# Análisis del lote
# ---------------------------------------------------------------------------

def _normalize_for_similarity(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def analyze_batch(inventory: Inventory, root: Path) -> AnalysisResult:
    from design_pipeline.utils import iso_now

    result = AnalysisResult(
        created_at=iso_now(), inventory_fingerprint=inventory.source_fingerprint
    )

    files = inventory.files_by_path()
    texts: dict[str, str] = {}
    for entry in inventory.files:
        if entry.analyzed:
            texts[entry.path] = (root / entry.path).read_text(encoding="utf-8", errors="replace")

    # Componentes.
    for entry in inventory.files:
        if entry.category != "component":
            continue
        component = parse_component(entry.path, texts.get(entry.path, ""))
        if component is None:
            result.limitations.append(
                f"`{entry.path}` tiene extensión de componente pero no se reconoció una exportación de componente."
            )
            continue
        result.components.append(component)
        result.findings.append(
            Finding(
                kind="componente",
                classification=CLASSIFICATION_OBSERVED,
                message=f"Componente `{component.name}` exportado desde `{component.path}`",
                source=entry.path,
                justification="export function/const detectado en el archivo",
            )
        )
        for a11y in component.a11y_findings:
            result.findings.append(
                Finding(
                    kind="accesibilidad",
                    classification=CLASSIFICATION_OBSERVED,
                    message=f"{component.path}:{a11y['line']} — {a11y['detail']} (regla: {a11y['rule']})",
                    source=component.path,
                    justification="heurística determinista sobre el JSX exportado",
                )
            )
        if component.interactive:
            result.findings.append(
                Finding(
                    kind="interactividad",
                    classification=CLASSIFICATION_OBSERVED,
                    message=f"`{component.name}` usa hooks o manejadores de eventos: {', '.join(component.hooks) or 'on*'}",
                    source=component.path,
                )
            )
        if component.dynamic_classes:
            uncertainty_id = f"u-{len(result.uncertainties) + 1:03d}"
            result.uncertainties.append(
                Uncertainty(
                    id=uncertainty_id,
                    question=f"¿Qué valores pueden tomar las clases dinámicas de `{component.name}` (p. ej. variantes)?",
                    source=component.path,
                    category="variantes",
                    options=["Conservar solo las variantes observadas en el CSS", "Preguntar al diseñador"],
                    recommendation="Conservar las variantes observadas y registrar el resto como pendiente.",
                )
            )

    # Hojas de estilo: archivos .css del lote + CSS embebido al final de
    # componentes (issue #1: el CSS tras un marcador `/* nombre.css */` se
    # analiza como hoja de estilo virtual, no como referencia rota).
    stylesheet_sources: list[tuple[str, str]] = [
        (entry.path, texts.get(entry.path, ""))
        for entry in inventory.files
        if entry.category == "style"
    ]
    for entry in inventory.files:
        if entry.category != "component":
            continue
        text = texts.get(entry.path, "")
        if not text:
            continue
        for embedded in find_embedded_stylesheets(entry.path, text):
            known_paths = {path for path, _ in stylesheet_sources}
            if embedded.resolved in known_paths:
                continue  # ya cubierto (archivo real u otro componente): manda ese
            stylesheet_sources.append((embedded.resolved, embedded.css))
            result.findings.append(
                Finding(
                    kind="estilos",
                    classification=CLASSIFICATION_OBSERVED,
                    message=(
                        f"CSS embebido extraído de `{entry.path}` "
                        f"(marcador `/* {embedded.ref} */`, línea {embedded.marker_line}) "
                        f"→ hoja virtual `{embedded.resolved}`"
                    ),
                    source=entry.path,
                    justification=(
                        "el import del CSS no resuelve a un archivo; el bloque al final "
                        "del componente es CSS puro y se analiza como hoja de estilo"
                    ),
                )
            )
        suspicious = find_suspicious_css_tail(text)
        if suspicious is not None:
            result.limitations.append(
                f"Posible CSS sin separar en `{entry.path}` (marcador "
                f"`/* {suspicious.ref} */`, línea {suspicious.marker_line}): no se pudo "
                "confirmar como CSS válido; requiere revisión humana (NEEDS_REVIEW)."
            )

    for css_path, css_text in stylesheet_sources:
        css = parse_css(css_path, css_text)
        result.stylesheets.append(css)
        if css.custom_properties:
            result.tokens.update(css.custom_properties)
            result.findings.append(
                Finding(
                    kind="tokens",
                    classification=CLASSIFICATION_OBSERVED,
                    message=(
                        f"{len(css.custom_properties)} custom properties en `{css_path}`: "
                        + ", ".join(f"`{name}`" for name in list(css.custom_properties)[:8])
                    ),
                    source=css_path,
                )
            )

    # Relaciones entre componentes.
    component_paths = {component.path for component in result.components}
    for component in result.components:
        for local in component.local_imports:
            ref = local.split(" (línea")[0]
            resolved = _resolve_import(component.path, ref)
            for other in result.components:
                target = other.path
                if resolved == target or resolved + ".tsx" == target or resolved + ".jsx" == target:
                    component.related.append(other.name)
                    result.findings.append(
                        Finding(
                            kind="relación",
                            classification=CLASSIFICATION_OBSERVED,
                            message=f"`{component.name}` importa a `{other.name}`",
                            source=component.path,
                        )
                    )
    del component_paths

    # Assets no referenciados.
    referenced_assets: set[str] = set()
    for component in result.components:
        for asset in component.asset_imports:
            ref = asset.split(" (línea")[0]
            referenced_assets.add(_resolve_import(component.path, ref))
    for entry in inventory.files:
        if entry.category in {"vector", "image", "font"}:
            if entry.path not in referenced_assets:
                result.unused_assets.append(entry.path)
                result.findings.append(
                    Finding(
                        kind="recurso",
                        classification=CLASSIFICATION_OBSERVED,
                        message=f"Recurso sin referencias: `{entry.path}`",
                        source=entry.path,
                    )
                )

    # Duplicaciones aparentes (nunca afirmamos intercambiability).
    component_texts = [
        (component, _normalize_for_similarity(texts.get(component.path, "")))
        for component in result.components
    ]
    for index, (first, first_text) in enumerate(component_texts):
        for second, second_text in component_texts[index + 1 :]:
            if not first_text or not second_text:
                continue
            ratio = difflib.SequenceMatcher(None, first_text, second_text).ratio()
            if ratio >= 0.6:
                result.duplications.append(
                    {
                        "a": first.path,
                        "b": second.path,
                        "similarity": round(ratio, 3),
                        "status": "needs_review",
                    }
                )
                result.findings.append(
                    Finding(
                        kind="duplicación",
                        classification=CLASSIFICATION_INFERRED,
                        message=(
                            f"`{first.name}` y `{second.name}` comparten {ratio:.0%} de estructura de texto"
                        ),
                        source=f"{first.path}, {second.path}",
                        justification=(
                            "similitud de secuencia; NO implica que sean intercambiables: "
                            "falta comparar props, estados y comportamiento"
                        ),
                    )
                )

    # Colores ad-hoc fuera de tokens (propuesta, no cambio).
    adhoc_colors: list[str] = []
    token_values = {value.lower() for value in result.tokens.values()}
    for css in result.stylesheets:
        for color in css.colors:
            if color.lower() not in token_values:
                adhoc_colors.append(color)
    adhoc_colors = list(dict.fromkeys(adhoc_colors))
    if adhoc_colors:
        result.findings.append(
            Finding(
                kind="tokens",
                classification=CLASSIFICATION_PROPOSED,
                message="Colores literales sin token: " + ", ".join(f"`{c}`" for c in adhoc_colors),
                source="hojas de estilo del lote",
                justification="unificarlos en tokens reduce la deriva visual; requiere aprobación",
            )
        )
        result.uncertainties.append(
            Uncertainty(
                id=f"u-{len(result.uncertainties) + 1:03d}",
                question="¿Unificar los colores literales en tokens o conservarlos tal cual (fidelidad estricta)?",
                source="hojas de estilo del lote",
                category="tokens",
                options=["Conservar literales (fidelidad estricta)", "Unificar en tokens existentes"],
                recommendation="Conservar literales por defecto; unificar solo con aprobación explícita.",
            )
        )

    # Limitaciones de la exportación.
    for broken in inventory.broken_references:
        result.limitations.append(
            f"Referencia rota en la exportación: `{broken['from']}` → `{broken['ref']}` ({broken['reason']})."
        )
    for item in inventory.unanalyzed:
        result.limitations.append(f"No analizado: `{item['path']}` ({item['reason']}).")
    if result.unused_assets:
        result.limitations.append(
            "Recursos sin referencias en componentes: " + ", ".join(f"`{a}`" for a in result.unused_assets)
        )

    # Preguntas de accesibilidad pendientes.
    if any(f.kind == "accesibilidad" for f in result.findings):
        result.uncertainties.append(
            Uncertainty(
                id=f"u-{len(result.uncertainties) + 1:03d}",
                question="¿Corregir los hallazgos de accesibilidad detectados o preservar el export tal cual?",
                source="varios componentes",
                category="accesibilidad",
                options=["Preservar el export (fidelidad)", "Corregir los hallazgos al generar"],
                recommendation="Registrar como NEEDS_REVIEW y corregir solo con regla aprobada.",
            )
        )
    return result


def _resolve_import(from_rel: str, ref: str) -> str:
    base = Path(from_rel).parent
    parts = list(base.parts)
    for part in Path(ref).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)
