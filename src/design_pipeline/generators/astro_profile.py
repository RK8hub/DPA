"""Perfil astro-css: Astro + CSS con fallback a islas React.

Estrategia por componente:

- **Estático** (sin hooks ni handlers en elementos HTML): se convierte a
  ``.astro`` con el convertor conservador (ver ``astro_converter``).
- **Interactivo**: se copia el TSX tal cual (isla React) y se genera un
  wrapper ``.astro`` con ``client:load``. La integración de framework
  (``@astrojs/react``) NO se instala automáticamente; queda como requisito
  documentado y como NEEDS_REVIEW en la validación.
"""

from __future__ import annotations

from pathlib import Path

from design_pipeline.generators.astro_converter import (
    UnsupportedConversion,
    classify,
    convert,
    island_wrapper,
)
from design_pipeline.generators.base import GenerationContext, GenerationResult, Profile
from design_pipeline.generators.react_profile import resolve_rel, strip_extension
from design_pipeline.importers.embedded_css import (
    EmbeddedStylesheet,
    find_embedded_stylesheets,
    find_suspicious_css_tail,
    strip_embedded,
)
from design_pipeline.templates import render_component_readme, render_profile_readme


class AstroCssProfile(Profile):
    id = "astro-css"
    label = "Astro + CSS"
    description = (
        "Convierte componentes estáticos a .astro; los interactivos quedan como "
        "islas React (copia literal + wrapper con client:load)."
    )

    def generate(self, ctx: GenerationContext) -> GenerationResult:
        result = GenerationResult(profile=self.id)

        # Pasada 1: leer, separar CSS embebido (issue #1) y clasificar.
        codes: dict[str, str] = {}
        tentative: dict[str, str] = {}
        embedded_by_component: dict[str, dict[str, EmbeddedStylesheet]] = {}
        for spec in ctx.specs:
            source_path = spec["source"]["path"]
            raw = ctx.read_source(source_path)
            # Red de seguridad: chequear la cola sospechosa sobre el texto
            # original, antes de separar el CSS embebido (issue #1).
            suspicious = find_suspicious_css_tail(raw)
            embedded = find_embedded_stylesheets(source_path, raw)
            if embedded:
                embedded_by_component[source_path] = {
                    item.resolved: item for item in embedded
                }
                raw = strip_embedded(raw, embedded)
            codes[source_path] = raw
            mode, reasons = classify(raw)
            tentative[source_path] = "astro" if mode == "static" else "tsx"
            if reasons:
                result.needs_review.append(
                    f"{source_path}: isla React — {'; '.join(reasons)}"
                )
            if suspicious is not None:
                result.needs_review.append(
                    f"{source_path}: posible CSS crudo pegado al final del archivo "
                    f"(marcador `/* {suspicious.ref} */`, línea {suspicious.marker_line}) "
                    "que no se pudo separar como CSS válido; revisar antes de integrar "
                    "(NEEDS_REVIEW)."
                )

        # Pasada 2: intentar conversiones; los fallos caen a isla.
        converted: dict[str, object] = {}
        modes = dict(tentative)

        def attempt_conversions() -> None:
            for source_path, code in codes.items():
                if modes[source_path] != "astro":
                    continue
                module_modes = {
                    strip_extension(path): mode for path, mode in modes.items()
                }
                try:
                    conversion = convert(
                        spec_name_of(ctx, source_path), code, source_path, module_modes
                    )
                except UnsupportedConversion as exc:
                    modes[source_path] = "tsx"
                    result.needs_review.append(
                        f"{source_path}: conversión no soportada ({exc.reason}); "
                        "se deja como isla React."
                    )
                else:
                    converted[source_path] = conversion

        attempt_conversions()
        # Si algún módulo cambió a isla, se re-convierten los estáticos para
        # que sus imports reflejen el modo final (cadenas cortas de dependencias).
        if len(converted) + sum(1 for m in modes.values() if m == "tsx") != len(codes) or any(
            modes[path] == "tsx" and tentative[path] == "astro" for path in modes
        ):
            converted.clear()
            attempt_conversions()

        # Pasada 3: escribir archivos.
        for spec in ctx.specs:
            source_path = spec["source"]["path"]
            name = spec["name"]
            code = codes[source_path]

            if source_path in converted:
                conversion = converted[source_path]
                astro_rel = str(Path(source_path).with_suffix(".astro"))
                ctx.write(astro_rel, conversion.text)
                result.add(astro_rel, "transformed", "JSX/TSX convertido a Astro (estático)")
                result.needs_review.extend(
                    f"{source_path}: {warning}" for warning in conversion.warnings
                )
            else:
                # Isla React: copia literal + wrapper.
                ctx.write(source_path, code)
                result.add(source_path, "copied", "isla React (comportamiento de cliente)")
                wrapper_rel = str(Path(source_path).with_suffix(".astro"))
                ctx.write(
                    wrapper_rel,
                    island_wrapper(Path(source_path).name, name),
                )
                result.add(
                    wrapper_rel,
                    "created",
                    "wrapper de isla con client:load (requiere @astrojs/react)",
                )
                result.notes.append(
                    f"{name}: isla React. Requiere `npx astro add react` (o instalación "
                    "manual de @astrojs/react) en el proyecto de destino."
                )

            # CSS embebido separado: se escribe como hoja .css real (issue #1).
            written_embedded: set[str] = set()
            for resolved, item in embedded_by_component.get(source_path, {}).items():
                if (ctx.source_root / resolved).exists():
                    continue  # existe el archivo real: manda ese
                ctx.write(resolved, item.css)
                written_embedded.add(resolved)
                result.add(
                    resolved,
                    "created",
                    f"CSS embebido extraído de {source_path} (marcador `/* {item.ref} */`)",
                )

            # Hojas de estilo y recursos (mismo criterio que react-css).
            for stylesheet in spec["dependencies"].get("stylesheets", []):
                resolved = resolve_rel(source_path, stylesheet)
                if resolved in written_embedded:
                    continue  # ya escrito desde el bloque embebido
                if (ctx.source_root / resolved).exists():
                    ctx.copy(resolved)
                    result.add(resolved, "copied", "hoja de estilos del componente")
                else:
                    result.needs_review.append(
                        f"{name}: hoja de estilos referenciada sin resolver `{stylesheet}`"
                    )
            for asset in spec["dependencies"].get("assets", []):
                resolved = resolve_rel(source_path, asset)
                if (ctx.source_root / resolved).exists():
                    ctx.copy(resolved)
                    result.add(resolved, "copied", "recurso referenciado")
                else:
                    result.needs_review.append(
                        f"{name}: recurso referenciado sin resolver `{asset}`"
                    )

            readme_rel = str(Path(source_path).parent / "README.md")
            ctx.write(readme_rel, render_component_readme(spec, self.id))
            result.add(readme_rel, "created", "documentación del componente")

        ctx.write("README.md", render_profile_readme(ctx, result))
        result.add("README.md", "created", "índice del perfil de salida")
        result.notes.append(
            "Los componentes interactivos permanecen como React: Astro no ejecuta "
            "hooks ni handlers en plantillas estáticas."
        )
        return result


def spec_name_of(ctx: GenerationContext, source_path: str) -> str:
    for spec in ctx.specs:
        if spec["source"]["path"] == source_path:
            return spec["name"]
    return Path(source_path).stem
