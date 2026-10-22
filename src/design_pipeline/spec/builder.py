"""Etapa E: especificación intermedia independiente del framework.

Toma el análisis (etapa C) y las reglas aprobadas (etapa D) y produce una
especificación por componente en JSON (validado contra
``component-spec.schema.json``) y en Markdown para revisión humana. La
especificación es el contrato que consumen los perfiles de generación: los
generadores no vuelven a analizar todo el lote.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from design_pipeline.analysis.analyzer import AnalysisResult, ComponentInfo, CssInfo
from design_pipeline.errors import DesignPipelineError
from design_pipeline.importers.stage import load_inventory
from design_pipeline.rules.manager import Rule, approved_rules, load_questions
from design_pipeline.utils import iso_now
from design_pipeline.validators.schema import package_schemas_dir, validate_instance
from design_pipeline.workspace.project import Project

_TAG_RE = re.compile(r"<\s*([A-Za-z][\w.]*)\b([^>]*?)(/?)>|<\s*/\s*([\w.]+)\s*>")
_CLASSES_ATTR_RE = re.compile(r"""className=["']([^"']+)["']""")
_UNION_RE = re.compile(r"""["']([^"']+)["']\s*\|?""")


@dataclass
class ComponentSpec:
    schema_version: int
    name: str
    source: dict[str, str]
    identity: dict[str, Any] = field(default_factory=dict)
    props: list[dict[str, Any]] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    variants: list[dict[str, Any]] = field(default_factory=list)
    structure: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: list[dict[str, Any]] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    responsive: list[dict[str, Any]] = field(default_factory=list)
    interactions: list[str] = field(default_factory=list)
    accessibility: list[str] = field(default_factory=list)
    fidelity_constraints: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)
    applied_rules: list[dict[str, str]] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "source": self.source,
            "identity": self.identity,
            "props": self.props,
            "states": self.states,
            "variants": self.variants,
            "structure": self.structure,
            "tokens_used": self.tokens_used,
            "dependencies": self.dependencies,
            "responsive": self.responsive,
            "interactions": self.interactions,
            "accessibility": self.accessibility,
            "fidelity_constraints": self.fidelity_constraints,
            "related": self.related,
            "applied_rules": self.applied_rules,
            "open_questions": self.open_questions,
            "limitations": self.limitations,
        }


def _jsx_skeleton(text: str) -> list[dict[str, Any]]:
    """Esqueleto superficial del JSX: tags, profundidad y clases literales."""
    structure: list[dict[str, Any]] = []
    depth = 0
    for match in _TAG_RE.finditer(text):
        tag = match.group(1) or match.group(4)
        if not tag:
            depth = max(0, depth - 1)
            continue
        if match.group(1) is None:  # cierre
            continue
        attrs = match.group(2) or ""
        classes: list[str] = []
        class_match = _CLASSES_ATTR_RE.search(attrs)
        if class_match:
            classes = class_match.group(1).split()
        self_closing = bool(match.group(3)) or tag.lower() in _VOID_TAGS
        structure.append(
            {
                "tag": tag,
                "depth": depth,
                "classes": classes,
                "children_text": False,
            }
        )
        if not self_closing:
            depth += 1
    return structure


_VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


def _stylesheets_for(component: ComponentInfo, stylesheets: list[CssInfo]) -> list[CssInfo]:
    wanted: list[str] = []
    for style_import in component.style_imports:
        ref = style_import.split(" (línea")[0]
        base = Path(component.path).parent
        parts = list(base.parts)
        for part in Path(ref).parts:
            if part == "..":
                if parts:
                    parts.pop()
            elif part != ".":
                parts.append(part)
        wanted.append("/".join(parts))
    return [css for css in stylesheets if css.path in wanted]


def build_component_spec(
    component: ComponentInfo,
    analysis: AnalysisResult,
    inventory_sha: dict[str, str],
    rules: list[Rule],
    open_question_texts: list[str],
) -> ComponentSpec:
    spec = ComponentSpec(
        schema_version=1,
        name=component.name,
        source={"path": component.path, "sha256": inventory_sha.get(component.path, "")},
    )

    # Identidad: observada (nombre/export) + propósito inferido.
    purpose = f"Componente de interfaz exportado como `{component.name}` desde `{component.path}`."
    spec.identity = {
        "purpose": purpose,
        "classification": "observed",
        "export_default": bool(component.export_default),
    }

    # Props con procedencia (resolviendo aliases nombrados en el tipo mostrado).
    for prop in component.props:
        resolved_type = component.type_aliases.get(
            prop.get("type", ""), prop.get("type", "unknown")
        )
        entry: dict[str, Any] = {
            "name": prop["name"],
            "type": resolved_type,
            "optional": bool(prop.get("optional", False)),
            "provenance": "observed" if prop.get("type") != "unknown (destructuring)" else "inferred",
        }
        if "default" in prop:
            entry["default"] = prop["default"]
        spec.props.append(entry)

    # Variantes desde uniones de strings observadas en props (resolviendo aliases).
    for prop in component.props:
        prop_type = prop.get("type", "")
        resolved = component.type_aliases.get(prop_type, prop_type)
        values = _UNION_RE.findall(resolved)
        if len(values) >= 2:
            spec.variants.append(
                {"prop": prop["name"], "values": values, "provenance": "observed"}
            )

    # Estados observados (useState) + estados semánticos de props.
    for hook in component.hooks:
        if hook == "useState":
            spec.states.append("estado interno (useState) — ver componente fuente")
    for prop in component.props:
        if prop["name"] in {"disabled", "expanded", "open", "selected", "checked"}:
            spec.states.append(f"prop `{prop['name']}`")

    # Estructura superficial.
    spec.structure = _jsx_skeleton(_read_source(component))

    # Tokens/clases usadas: clases del JSX presentes en sus hojas de estilo.
    own_css = _stylesheets_for(component, analysis.stylesheets)
    for css in own_css:
        for class_name, rules_for_class in css.class_selectors.items():
            declarations: list[dict[str, str]] = []
            for rule in rules_for_class:
                for declaration in rule.get("declarations", []):
                    item = {
                        "property": declaration["property"],
                        "value": declaration["value"],
                    }
                    if rule.get("media"):
                        item["media"] = rule["media"]
                    declarations.append(item)
            spec.tokens_used.append({"class": class_name, "declarations": declarations})

    # Dependencias.
    local: list[str] = []
    assets: list[str] = []
    packages: list[str] = []
    stylesheets_paths: list[str] = []
    for ref in component.local_imports:
        clean = ref.split(" (línea")[0]
        if clean.endswith((".css", ".scss")):
            stylesheets_paths.append(clean)
        elif re.search(r"\.(svg|png|jpe?g|gif|webp|avif|ico|woff2?|ttf|otf)$", clean):
            assets.append(clean)
        else:
            local.append(clean)
    packages = list(component.package_imports)
    spec.dependencies = {
        "local": sorted(set(local)),
        "packages": sorted(set(packages)),
        "assets": sorted(set(assets)),
        "stylesheets": sorted(set(stylesheets_paths)),
    }

    # Responsive: media queries de sus hojas que mencionan sus clases.
    component_classes = {c for rule in spec.tokens_used for c in [rule["class"]]}
    for css in own_css:
        for media in css.media_queries:
            matched = [
                selector
                for selector in media["selectors"]
                for class_name in component_classes
                if f".{class_name}" in selector
            ]
            if matched:
                spec.responsive.append(
                    {
                        "condition": media["condition"],
                        "classes": sorted(
                            {
                                name
                                for selector in matched
                                for name in component_classes
                                if f".{name}" in selector
                            }
                        ),
                    }
                )

    # Interacciones observadas.
    source_text = _read_source(component)
    for handler in sorted(set(re.findall(r"\bon([A-Z]\w*)=", source_text))):
        spec.interactions.append(f"on{handler} (observado en JSX)")
    for hook in component.hooks:
        spec.interactions.append(f"{hook} (hook de estado/efecto)")

    # Accesibilidad: hallazgos observados + nota de revisión.
    for a11y in component.a11y_findings:
        spec.accessibility.append(
            f"{a11y['detail']} (línea {a11y['line']}, regla {a11y['rule']}) — NEEDS_REVIEW"
        )

    # Restricciones de fidelidad: valores concretos observados en sus clases.
    constraints: list[str] = []
    for used in spec.tokens_used:
        for declaration in used["declarations"]:
            if declaration["property"] in {"color", "background", "font-size", "padding", "gap", "border-radius"}:
                constraints.append(
                    f".{used['class']} {{{declaration['property']}: {declaration['value']}}}"
                )
    spec.fidelity_constraints = sorted(set(constraints)) or [
        "Sin restricciones específicas observadas; conservar el aspecto general del export."
    ]

    # Relaciones.
    spec.related = sorted(set(component.related))

    # Reglas aprobadas aplicadas.
    spec.applied_rules = [{"id": rule.id, "text": rule.text} for rule in rules]

    # Preguntas abiertas que mencionan a este componente o sus archivos.
    for question in open_question_texts:
        if component.name in question or component.path in question:
            spec.open_questions.append(question)

    # Limitaciones de la exportación que lo afectan.
    for broken_ref in component.local_imports:
        clean = broken_ref.split(" (línea")[0]
        if clean.endswith((".css", ".scss")) and not _ref_exists(component, clean, analysis):
            spec.limitations.append(f"Referencia de estilos sin resolver: `{clean}`")

    return spec


def _read_source(component: ComponentInfo) -> str:
    return _SOURCE_ROOT.get(component.path, "")


# El builder se ejecuta con el root de la fuente accesible para leer archivos.
_SOURCE_ROOT: dict[str, str] = {}


def build_specs(project: Project) -> dict[str, Any]:
    """Etapa E completa: genera specs por componente + índice, validados por esquema."""
    if not project.paths.analysis_json.exists():
        raise DesignPipelineError("No hay análisis: ejecutá primero la etapa analyze.")
    from design_pipeline.analysis.stage import load_analysis

    analysis = load_analysis(project)
    inventory = load_inventory(project)
    if inventory is None:  # pragma: no cover - analyze lo garantiza
        raise DesignPipelineError("No hay inventario.")
    source_root = project.source_path
    if source_root is None or not source_root.is_dir():
        raise DesignPipelineError("La fuente importada no está disponible.")

    # Carga el texto fuente de cada componente para el esqueleto JSX.
    _SOURCE_ROOT.clear()
    for component in analysis.components:
        path = source_root / component.path
        if path.exists():
            _SOURCE_ROOT[component.path] = path.read_text(
                encoding="utf-8", errors="replace"
            )

    rules = approved_rules(project)
    questions = [q for q in load_questions(project) if q.status in {"open", "postponed"}]
    open_question_texts = [f"{q.id}: {q.text}" for q in questions]
    inventory_sha = {entry.path: entry.sha256 for entry in inventory.files}

    schema = _load_component_schema()
    components_dir = project.paths.specs_dir / "components"
    components_dir.mkdir(parents=True, exist_ok=True)

    index: list[dict[str, Any]] = []
    errors_all: list[str] = []
    for component in analysis.components:
        spec = build_component_spec(
            component, analysis, inventory_sha, rules, open_question_texts
        )
        data = spec.to_dict()
        errors = validate_instance(data, schema, path=f"$.{spec.name}")
        if errors:
            errors_all.extend(errors)
            continue
        (components_dir / f"{spec.name}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (components_dir / f"{spec.name}.md").write_text(
            render_spec_markdown(spec), encoding="utf-8"
        )
        index.append(
            {
                "name": spec.name,
                "source": spec.source["path"],
                "interactive": bool(component.interactive),
                "props": len(spec.props),
                "variants": len(spec.variants),
                "related": spec.related,
            }
        )

    if errors_all:
        raise DesignPipelineError(
            "Las especificaciones no cumplen el esquema: " + "; ".join(errors_all[:5])
        )

    payload = {
        "schema_version": 1,
        "created_at": iso_now(),
        "analysis_fingerprint": analysis.created_at,
        "approved_rules": [rule.id for rule in rules],
        "components": index,
    }
    (project.paths.specs_dir / "index.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return payload


def _load_component_schema() -> dict[str, Any]:
    schema_path = package_schemas_dir() / "component-spec.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _ref_exists(component: ComponentInfo, ref: str, analysis: AnalysisResult) -> bool:
    base = Path(component.path).parent
    parts = list(base.parts)
    for part in Path(ref).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    resolved = "/".join(parts)
    return any(css.path == resolved for css in analysis.stylesheets)


def render_spec_markdown(spec: ComponentSpec) -> str:
    data = spec.to_dict()
    lines = [
        f"# Especificación: `{spec.name}`",
        "",
        f"- **Fuente:** `{spec.source['path']}`",
        f"- **sha256:** `{spec.source['sha256'][:16]}…`",
        f"- **Propósito:** {spec.identity.get('purpose', '')}",
        "",
        "## Props",
        "",
    ]
    if spec.props:
        lines.append("| Prop | Tipo | Opcional | Default | Procedencia |")
        lines.append("| --- | --- | --- | --- | --- |")
        for prop in spec.props:
            lines.append(
                f"| `{prop['name']}` | `{prop.get('type', '?')}` | "
                f"{'sí' if prop.get('optional') else 'no'} | "
                f"`{prop.get('default', '—')}` | {prop.get('provenance', '?')} |"
            )
    else:
        lines.append("- Sin props declaradas.")
    lines.append("")

    if spec.variants:
        lines.append("## Variantes")
        lines.append("")
        for variant in spec.variants:
            values = ", ".join(f"`{v}`" for v in variant["values"])
            lines.append(f"- `{variant['prop']}`: {values} ({variant['provenance']})")
        lines.append("")

    if spec.states:
        lines.append("## Estados")
        lines.append("")
        lines.extend(f"- {state}" for state in spec.states)
        lines.append("")

    lines.append("## Estructura (superficie)")
    lines.append("")
    for node in spec.structure[:40]:
        indent = "  " * node["depth"]
        classes = f" .{' .'.join(node['classes'])}" if node["classes"] else ""
        lines.append(f"- {indent}<{node['tag']}{classes}>")
    if len(spec.structure) > 40:
        lines.append(f"- … ({len(spec.structure) - 40} nodos más)")
    lines.append("")

    if spec.tokens_used:
        lines.append("## Clases y tokens observados")
        lines.append("")
        for used in spec.tokens_used:
            decls = "; ".join(
                f"{d['property']}: {d['value']}" for d in used["declarations"][:6]
            )
            lines.append(f"- `.{used['class']}` — {decls or '(sin declaraciones)'}")
        lines.append("")

    if spec.responsive:
        lines.append("## Responsive")
        lines.append("")
        for media in spec.responsive:
            classes = ", ".join(f"`.{c}`" for c in media["classes"])
            lines.append(f"- `@media {media['condition']}`: {classes}")
        lines.append("")

    lines.append("## Dependencias")
    lines.append("")
    deps = spec.dependencies
    lines.append(f"- Locales: {', '.join(f'`{d}`' for d in deps.get('local', [])) or 'ninguna'}")
    lines.append(
        f"- Paquetes: {', '.join(f'`{p}`' for p in deps.get('packages', [])) or 'ninguno'}"
    )
    lines.append(
        f"- Recursos: {', '.join(f'`{a}`' for a in deps.get('assets', [])) or 'ninguno'}"
    )
    lines.append("")

    if spec.interactions:
        lines.append("## Interacciones")
        lines.append("")
        lines.extend(f"- {item}" for item in spec.interactions)
        lines.append("")

    if spec.accessibility:
        lines.append("## Accesibilidad (NEEDS_REVIEW)")
        lines.append("")
        lines.extend(f"- {item}" for item in spec.accessibility)
        lines.append("")

    lines.append("## Restricciones de fidelidad")
    lines.append("")
    lines.extend(f"- `{item}`" for item in spec.fidelity_constraints)
    lines.append("")

    if spec.applied_rules:
        lines.append("## Reglas aprobadas aplicadas")
        lines.append("")
        lines.extend(
            f"- **{rule['id']}**: {rule['text']}" for rule in spec.applied_rules
        )
        lines.append("")

    if spec.open_questions:
        lines.append("## Preguntas abiertas")
        lines.append("")
        lines.extend(f"- {question}" for question in spec.open_questions)
        lines.append("")

    if spec.limitations:
        lines.append("## Limitaciones")
        lines.append("")
        lines.extend(f"- {item}" for item in spec.limitations)
        lines.append("")
    return "\n".join(lines)
