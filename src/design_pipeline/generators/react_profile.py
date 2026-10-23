"""Perfil react-css: React + CSS con fidelidad literal.

Estrategia (decisión documentada): se preserva la estructura de directorios de
la fuente dentro de ``output/react-css/`` y los componentes se copian tal cual.
Como los imports relativos apuntan a rutas que mantienen la misma posición,
siguen resolviendo sin reescritura. Solo se agregan READMEs por componente,
un barrel ``index.ts`` y las notas de generación.
"""

from __future__ import annotations

from pathlib import Path

from design_pipeline.generators.base import GenerationContext, GenerationResult, Profile
from design_pipeline.importers.embedded_css import (
    find_embedded_stylesheets,
    find_suspicious_css_tail,
    strip_embedded,
)
from design_pipeline.templates import render_component_readme, render_profile_readme


def resolve_rel(from_rel: str, ref: str) -> str:
    base = Path(from_rel).parent
    parts = list(base.parts)
    for part in Path(ref).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def strip_extension(path: str) -> str:
    for ext in (".tsx", ".ts", ".jsx", ".js"):
        if path.endswith(ext):
            return path[: -len(ext)]
    return path


class ReactCssProfile(Profile):
    id = "react-css"
    label = "React + CSS"
    description = (
        "Copia literal de los componentes TSX/JSX y su CSS, preservando la "
        "estructura de la fuente. Máxima fidelidad, mínima transformación."
    )

    def generate(self, ctx: GenerationContext) -> GenerationResult:
        result = GenerationResult(profile=self.id)
        barrel: list[str] = []

        for spec in ctx.specs:
            name = spec["name"]
            source_path = spec["source"]["path"]
            original = ctx.read_source(source_path)

            # Issue #1: el CSS embebido al final del componente (marcador
            # `/* nombre.css */`) se separa a un archivo .css real; el
            # JSX/TSX de salida queda compilable.
            embedded = find_embedded_stylesheets(source_path, original)
            embedded_by_path = {item.resolved: item for item in embedded}
            written_embedded: set[str] = set()
            if embedded:
                for item in embedded:
                    if (ctx.source_root / item.resolved).exists():
                        continue  # existe el archivo real: manda ese
                    ctx.write(item.resolved, item.css)
                    written_embedded.add(item.resolved)
                    result.add(
                        item.resolved,
                        "created",
                        f"CSS embebido extraído de {source_path} (marcador `/* {item.ref} */`)",
                    )
                ctx.write(source_path, strip_embedded(original, embedded))
                result.add(
                    source_path,
                    "transformed",
                    "CSS embebido separado a archivo .css (el bloque crudo no compila en JSX/TSX)",
                )
            else:
                ctx.write(source_path, original)
                result.add(source_path, "copied", "copia literal del componente de origen")

            # Red de seguridad: un marcador de CSS no separable no se copia
            # en silencio (issue #1: nada de sintaxis inválida sin avisar).
            suspicious = find_suspicious_css_tail(original)
            if suspicious is not None:
                result.needs_review.append(
                    f"{name}: posible CSS crudo pegado al final del archivo "
                    f"(marcador `/* {suspicious.ref} */`, línea {suspicious.marker_line}) "
                    "que no se pudo separar como CSS válido; el archivo puede no "
                    "compilar hasta revisarlo (NEEDS_REVIEW)."
                )

            # Hojas de estilo del componente.
            for stylesheet in spec["dependencies"].get("stylesheets", []):
                resolved = resolve_rel(source_path, stylesheet)
                if resolved in written_embedded:
                    continue  # ya escrito desde el bloque embebido
                if (ctx.source_root / resolved).exists():
                    ctx.copy(resolved)
                    result.add(resolved, "copied", "hoja de estilos del componente")
                else:
                    result.needs_review.append(
                        f"{name}: hoja de estilos referenciada sin resolver `{stylesheet}` "
                        "(referencia rota heredada del export)"
                    )

            # Recursos referenciados (los no referenciados se excluyen por decisión).
            for asset in spec["dependencies"].get("assets", []):
                resolved = resolve_rel(source_path, asset)
                if (ctx.source_root / resolved).exists():
                    ctx.copy(resolved)
                    result.add(resolved, "copied", "recurso referenciado")
                else:
                    result.needs_review.append(
                        f"{name}: recurso referenciado sin resolver `{asset}`"
                    )

            # README del componente.
            readme_rel = str(Path(source_path).parent / "README.md")
            ctx.write(readme_rel, render_component_readme(spec, self.id))
            result.add(readme_rel, "created", "documentación del componente")

            # Barrel.
            module = "./" + strip_extension(source_path)
            if spec["identity"].get("export_default"):
                barrel.append(f'export {{ default as {name} }} from "{module}";')
            else:
                barrel.append(f'export {{ {name} }} from "{module}";')

        ctx.write("index.ts", "\n".join(barrel) + "\n")
        result.add("index.ts", "created", "barrel de exportaciones")
        ctx.write("README.md", render_profile_readme(ctx, result))
        result.add("README.md", "created", "índice del perfil de salida")
        result.notes.append(
            "Componentes copiados literalmente; la estructura de la fuente se preserva "
            "para que los imports relativos sigan resolviendo."
        )
        result.notes.append(
            "Los recursos sin referenciar se excluyen de la salida (ver "
            "reports/ANALYSIS.md, sección de recursos no usados)."
        )
        return result
