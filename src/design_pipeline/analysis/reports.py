"""Render de los entregables de la etapa C (Markdown legible + JSON máquina)."""

from __future__ import annotations

from design_pipeline.analysis.analyzer import (
    CLASSIFICATION_LABELS,
    CLASSIFICATION_OBSERVED,
    CLASSIFICATION_INFERRED,
    CLASSIFICATION_PROPOSED,
    CLASSIFICATION_PENDING,
    AnalysisResult,
)


def render_analysis(result: AnalysisResult) -> str:
    lines = [
        "# Análisis del lote",
        "",
        f"- **Fecha:** {result.created_at}",
        f"- **Huella del inventario:** `{result.inventory_fingerprint[:16]}…`",
        f"- **Componentes:** {len(result.components)}",
        f"- **Hojas de estilo:** {len(result.stylesheets)}",
        "",
        "> Cada hallazgo está clasificado como **Observado** (respaldado por los archivos), "
        "**Inferido** (interpretación con justificación), **Propuesto** (cambio sugerido, "
        "requiere aprobación) o **Pendiente** (pregunta sin resolver).",
        "",
    ]

    sections = [
        (CLASSIFICATION_OBSERVED, "Observado"),
        (CLASSIFICATION_INFERRED, "Inferido"),
        (CLASSIFICATION_PROPOSED, "Propuesto"),
        (CLASSIFICATION_PENDING, "Pendiente"),
    ]
    for classification, title in sections:
        findings = result.by_classification(classification)
        lines.append(f"## {title}")
        lines.append("")
        if not findings:
            lines.append("- (sin hallazgos)")
            lines.append("")
            continue
        for finding in findings:
            lines.append(f"- **[{finding.kind}]** {finding.message}")
            lines.append(f"  - Fuente: `{finding.source}`")
            if finding.justification:
                lines.append(f"  - Justificación: {finding.justification}")
        lines.append("")

    lines.append("## Componentes")
    lines.append("")
    lines.append("| Componente | Archivo | Props | Interactivo | Relaciones |")
    lines.append("| --- | --- | --- | --- | --- |")
    for component in result.components:
        props = ", ".join(p["name"] for p in component.props) or "—"
        relations = ", ".join(sorted(set(component.related))) or "—"
        lines.append(
            f"| `{component.name}` | `{component.path}` | {props} | "
            f"{'sí' if component.interactive else 'no'} | {relations} |"
        )
    lines.append("")

    lines.append("## Tokens detectados")
    lines.append("")
    if result.tokens:
        lines.append("| Token | Valor |")
        lines.append("| --- | --- |")
        for name, value in sorted(result.tokens.items()):
            lines.append(f"| `{name}` | `{value}` |")
    else:
        lines.append("- Sin custom properties detectadas.")
    lines.append("")

    if result.duplications:
        lines.append("## Duplicaciones aparentes (requieren revisión)")
        lines.append("")
        for item in result.duplications:
            lines.append(
                f"- `{item['a']}` ↔ `{item['b']}`: {item['similarity']:.0%} de similitud textual. "
                "No se concluye que sean intercambiables."
            )
        lines.append("")

    lines.append("## Limitaciones de la exportación")
    lines.append("")
    if result.limitations:
        lines.extend(f"- {item}" for item in result.limitations)
    else:
        lines.append("- Ninguna detectada.")
    lines.append("")
    return "\n".join(lines)


def render_component_map(result: AnalysisResult) -> str:
    lines = [
        "# Mapa de componentes",
        "",
        f"Generado: {result.created_at}",
        "",
    ]
    by_name = {component.name: component for component in result.components}
    for component in result.components:
        lines.append(f"## `{component.name}` (`{component.path}`)")
        lines.append("")
        prop_names = ", ".join("`{0}`".format(p["name"]) for p in component.props)
        lines.append(f"- **Props:** {prop_names or 'ninguna declarada'}")
        if component.interactive:
            hooks = ", ".join(component.hooks) or "manejadores on*"
            lines.append(f"- **Interactivo:** sí ({hooks})")
        else:
            lines.append("- **Interactivo:** no")
        if component.related:
            lines.append("- **Importa a:** " + ", ".join(f"`{name}`" for name in sorted(set(component.related))))
        if component.style_imports:
            lines.append("- **Estilos:** " + ", ".join(f"`{ref}`" for ref in component.style_imports))
        if component.asset_imports:
            lines.append("- **Recursos:** " + ", ".join(f"`{ref}`" for ref in component.asset_imports))
        if component.package_imports:
            lines.append("- **Paquetes:** " + ", ".join(f"`{ref}`" for ref in component.package_imports))
        if component.a11y_findings:
            lines.append("- **Hallazgos de accesibilidad:**")
            for a11y in component.a11y_findings:
                lines.append(f"  - línea {a11y['line']}: {a11y['detail']}")
        lines.append("")
    # Gráfico textual de relaciones.
    relations = [
        (component.name, other)
        for component in result.components
        for other in sorted(set(component.related))
        if other in by_name
    ]
    if relations:
        lines.append("## Relaciones")
        lines.append("")
        lines.extend(f"- `{origin}` → `{target}`" for origin, target in relations)
        lines.append("")
    return "\n".join(lines)


def render_uncertainties(result: AnalysisResult) -> str:
    lines = [
        "# Incertidumbres y preguntas pendientes",
        "",
        "Estas preguntas requieren decisión humana o regla de proyecto. Algunas se",
        "reutilizan como preguntas de descubrimiento en la etapa `rules`.",
        "",
    ]
    if not result.uncertainties:
        lines.append("- Ninguna incertidumbre registrada.")
    for uncertainty in result.uncertainties:
        lines.append(f"## {uncertainty.id} — {uncertainty.category}")
        lines.append("")
        lines.append(f"- **Pregunta:** {uncertainty.question}")
        lines.append(f"- **Fuente:** `{uncertainty.source}`")
        if uncertainty.options:
            lines.append("- **Opciones:**")
            lines.extend(f"  - {option}" for option in uncertainty.options)
        if uncertainty.recommendation:
            lines.append(f"- **Recomendación:** {uncertainty.recommendation}")
        lines.append("")
    return "\n".join(lines)
