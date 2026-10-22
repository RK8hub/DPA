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
            code = ctx.read_source(source_path)
            ctx.write(source_path, code)
            result.add(source_path, "copied", "copia literal del componente de origen")

            # Hojas de estilo del componente.
            for stylesheet in spec["dependencies"].get("stylesheets", []):
                resolved = resolve_rel(source_path, stylesheet)
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
