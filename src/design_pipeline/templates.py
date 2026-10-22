"""Plantillas de documentación generada (sin dependencias de template engine).

``{placeholders}`` se llenan con ``str.format``. Los textos entre llaves
dobles escapadas (``{{``/``}}``) son literales.
"""

from __future__ import annotations

from typing import Any


def _props_table(spec: dict[str, Any]) -> str:
    props = spec.get("props", [])
    if not props:
        return "Sin props declaradas en la exportación."
    lines = ["| Prop | Tipo | Opcional | Default |", "| --- | --- | --- | --- |"]
    for prop in props:
        lines.append(
            "| `{name}` | `{type}` | {optional} | {default} |".format(
                name=prop["name"],
                type=prop.get("type", "?"),
                optional="sí" if prop.get("optional") else "no",
                default="`{0}`".format(prop["default"]) if prop.get("default") else "—",
            )
        )
    return "\n".join(lines)


def _variants(spec: dict[str, Any]) -> str:
    variants = spec.get("variants", [])
    if not variants:
        return "Sin variantes detectadas."
    return "\n".join(
        "- `{prop}`: {values}".format(
            prop=variant["prop"], values=", ".join("`{0}`".format(v) for v in variant["values"])
        )
        for variant in variants
    )


def _limitations(spec: dict[str, Any]) -> str:
    items: list[str] = []
    items.extend(f"NEEDS_REVIEW: {item}" for item in spec.get("accessibility", []))
    items.extend(f"Limitación: {item}" for item in spec.get("limitations", []))
    items.extend(f"Pregunta abierta: {item}" for item in spec.get("open_questions", []))
    if not items:
        return "- Ninguna registrada."
    return "\n".join(f"- {item}" for item in items)


def render_component_readme(spec: dict[str, Any], profile: str) -> str:
    name = spec["name"]
    return f"""# {name}

Componente generado por el perfil `{profile}` de design-pipeline.

- **Fuente original:** `{spec['source']['path']}` (sha256 `{spec['source']['sha256'][:12]}…`)
- **Propósito (observado):** {spec['identity'].get('purpose', '')}

## Uso

```tsx
import {{ {name} }} from "<ruta-relativa>";
```

## Props

{_props_table(spec)}

## Variantes

{_variants(spec)}

## Reglas aprobadas aplicadas

{chr(10).join('- **' + r['id'] + '**: ' + r['text'] for r in spec.get('applied_rules', [])) or '- Ninguna.'}

## Limitaciones y revisión humana

{_limitations(spec)}

> Generado automáticamente. Revisá esta lista antes de usar el componente en producción.
"""


def render_profile_readme(ctx: Any, result: Any) -> str:
    rows = []
    for spec in ctx.specs:
        source_path = spec["source"]["path"]
        rows.append(
            "| `{name}` | `{path}` | {props} |".format(
                name=spec["name"], path=source_path, props=len(spec.get("props", []))
            )
        )
    components_table = "\n".join(rows) or "| (ninguno) | | |"
    review = "\n".join(f"- {item}" for item in result.needs_review) or "- Ninguno."
    notes = "\n".join(f"- {note}" for note in result.notes) or "- Ninguna."
    return f"""# Salida del perfil `{result.profile}`

Estructura de componentes generada por design-pipeline. **Ninguna dependencia
fue instalada automáticamente**: si el proyecto de destino no tiene React
(u otra integración declarada), agregala manualmente al clonar estos archivos.

## Componentes

| Componente | Archivo | Props |
| --- | --- | ---: |
{components_table}

## Notas de generación

{notes}

## Revisión humana pendiente

{review}

> La exportación original no fue modificada. Esta carpeta es autosuficiente y
> puede copiarse al proyecto real una vez revisada.
"""
