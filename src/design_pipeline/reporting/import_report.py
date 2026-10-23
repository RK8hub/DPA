"""Render del informe de importación (etapa B)."""

from __future__ import annotations

from design_pipeline.importers.inventory import Inventory
from design_pipeline.utils import format_bytes


def render_import_report(inventory: Inventory) -> str:
    stats = inventory.stats
    lines: list[str] = [
        "# Informe de importación",
        "",
        f"- **Fuente:** `{inventory.source_path}`",
        f"- **Fecha:** {inventory.created_at}",
        f"- **Huella de la fuente (sha256 del árbol):** `{inventory.source_fingerprint}`",
        f"- **Archivos:** {stats.get('total_files', 0)} ({stats.get('total_size_human', '0 B')})",
        "",
        "## Categorías",
        "",
        "| Categoría | Archivos |",
        "| --- | ---: |",
    ]
    for category, count in (stats.get("by_category") or {}).items():
        lines.append(f"| {category} | {count} |")

    lines += ["", "## Exclusiones aplicadas", ""]
    lines += [f"- `{pattern}`" for pattern in inventory.exclusions] or ["- (ninguna)"]

    lines += ["", "## Duplicados por contenido", ""]
    if inventory.duplicate_groups:
        for group in inventory.duplicate_groups:
            lines.append(
                f"- sha256 `{group['sha256'][:12]}…` ({format_bytes(group['size'])}): "
                + ", ".join(f"`{path}`" for path in group["paths"])
            )
    else:
        lines.append("- No se detectaron archivos duplicados exactos.")

    lines += ["", "## Referencias rotas", ""]
    if inventory.broken_references:
        lines.append("| Archivo | Referencia | Motivo |")
        lines.append("| --- | --- | --- |")
        for broken in inventory.broken_references:
            lines.append(
                f"| `{broken['from']}` | `{broken['ref']}` | {broken['reason']} |"
            )
    else:
        lines.append("- Sin referencias locales rotas detectadas.")

    lines += ["", "## CSS embebido en componentes", ""]
    if inventory.embedded_stylesheets:
        lines.append("| Componente | Referencia | Hoja resuelta | Línea |")
        lines.append("| --- | --- | --- | ---: |")
        for embedded in inventory.embedded_stylesheets:
            lines.append(
                f"| `{embedded['component']}` | `{embedded['ref']}` | "
                f"`{embedded['resolved']}` | {embedded['marker_line']} |"
            )
        lines.append("")
        lines.append(
            "- No son referencias rotas: el CSS viene pegado al final del componente "
            "tras el marcador y se analiza/extrae como hoja de estilo."
        )
    else:
        lines.append("- Ninguno detectado.")

    lines += ["", "## Referencias externas (paquetes o URLs)", ""]
    if inventory.external_references:
        seen: dict[tuple[str, str], None] = {}
        for external in inventory.external_references:
            seen.setdefault((external["from"], external["ref"]), None)
        for (origin, ref) in list(seen)[:40]:
            lines.append(f"- `{origin}` → `{ref}`")
        if len(seen) > 40:
            lines.append(f"- … y {len(seen) - 40} más (ver `inventory.json`).")
    else:
        lines.append("- Ninguna.")

    lines += ["", "## Archivos no analizados", ""]
    if inventory.unanalyzed:
        for item in inventory.unanalyzed:
            lines.append(f"- `{item['path']}`: {item['reason']}")
    else:
        lines.append("- Todos los archivos restantes se analizaron como texto.")

    lines += [
        "",
        "## Notas de seguridad",
        "",
        "- La exportación original no fue modificada: este informe se generó en el workspace del proyecto.",
        "- Ningún archivo de entrada fue ejecutado durante la importación.",
        "",
    ]
    return "\n".join(lines)
