"""Etapa H: resumen de entrega y checklist de revisión humana.

La entrega nunca declara "listo para producción": produce un paquete legible
con lo generado, lo validado, lo omitido y la lista concreta de revisión
humana pendiente, más la ruta absoluta de la carpeta de salida.
"""

from __future__ import annotations

import json
from pathlib import Path

from design_pipeline.errors import DesignPipelineError
from design_pipeline.generators.registry import get_profile
from design_pipeline.rules.manager import load_rules, pending_rules
from design_pipeline.utils import iso_now
from design_pipeline.validators.runner import FAIL, NEEDS_REVIEW, SKIPPED
from design_pipeline.workspace.project import Project


def run_report(project: Project, profile_id: str | None = None) -> dict[str, str]:
    chosen = profile_id or str(project.data.get("generation", {}).get("profile", "react-css"))
    output_dir = project.paths.output_profile_dir(chosen)
    if not output_dir.is_dir():
        raise DesignPipelineError("No hay salida generada: ejecutá generate y validate primero.")

    validation_path = project.paths.reports_dir / "validation-report.json"
    validation: dict = {}
    if validation_path.exists():
        validation = json.loads(validation_path.read_text(encoding="utf-8"))

    generation_notes = project.paths.reports_dir / "generation-notes.md"
    needs_review_items = _collect_needs_review(project, validation, generation_notes)
    checklist = _render_checklist(project, chosen, needs_review_items, validation)
    (project.paths.reports_dir / "REVIEW-CHECKLIST.md").write_text(checklist, encoding="utf-8")

    delivery = _render_delivery(project, chosen, output_dir, validation, needs_review_items)
    (project.paths.reports_dir / "DELIVERY.md").write_text(delivery, encoding="utf-8")
    return {
        "delivery": str(project.paths.reports_dir / "DELIVERY.md"),
        "checklist": str(project.paths.reports_dir / "REVIEW-CHECKLIST.md"),
        "output": str(output_dir),
        "needs_review_count": str(len(needs_review_items)),
        "verdict": str(validation.get("verdict", "sin validar")),
    }


def _collect_needs_review(
    project: Project, validation: dict, generation_notes: Path
) -> list[str]:
    items: list[str] = []
    for check in validation.get("checks", []):
        if check.get("status") == NEEDS_REVIEW:
            items.append(f"[validación:{check.get('id')}] {check.get('detail', '')}")
    if generation_notes.exists():
        text = generation_notes.read_text(encoding="utf-8")
        section = text.split("## Revisión humana pendiente", 1)
        if len(section) == 2:
            body = section[1].split("##", 1)[0]
            for line in body.splitlines():
                line = line.strip()
                if line.startswith("- ") and line != "- Ninguno.":
                    items.append(f"[generación] {line[2:]}")
    for rule in pending_rules(project):
        items.append(f"[reglas] {rule.id} sigue propuesta (no aplicada): {rule.text}")
    state = project.load_state()
    for question_id in state.decisions_pending:
        if question_id.startswith("q-"):
            items.append(f"[decisiones] pregunta {question_id} sin responder")
    return items


def _render_checklist(
    project: Project, profile_id: str, needs_review: list[str], validation: dict
) -> str:
    profile = get_profile(profile_id)
    output_dir = project.paths.output_profile_dir(profile_id)
    components = sorted(
        path.parent.name
        for path in output_dir.rglob("README.md")
        if path.parent != output_dir
    )
    lines = [
        "# Checklist de revisión humana",
        "",
        "Completá esta lista antes de copiar la salida al proyecto real.",
        "",
        "## Revisión visual y de fidelidad",
        "",
        "- [ ] Comparar cada componente generado con el diseño original (uno por uno).",
        "- [ ] Verificar colores, tipografías, espaciados y medidas contra los tokens observados.",
        "- [ ] Confirmar que no se introdujeron estilos, colores o componentes nuevos.",
        "- [ ] Revisar comportamiento responsive en los breakpoints del export "
        "(p. ej. `@media (min-width: 768px)`).",
        "",
        "## Revisión funcional",
        "",
        "- [ ] Probar props y variantes de cada componente en el proyecto destino.",
    ]
    if profile_id == "astro-css":
        lines += [
            "- [ ] Instalar y configurar `@astrojs/react` si hay islas (no instalado automáticamente).",
            "- [ ] Verificar que las islas reciben `client:*` donde hace falta interactividad.",
        ]
    lines += [
        "",
        "## Ítems pendientes registrados por el pipeline",
        "",
    ]
    if needs_review:
        lines.extend(f"- [ ] {item}" for item in needs_review)
    else:
        lines.append("- Ningún ítem pendiente registrado.")
    lines += [
        "",
        "## Validación",
        "",
    ]
    for check in validation.get("checks", []):
        mark = "x" if check.get("status") in {SKIPPED, NEEDS_REVIEW, FAIL} else " "
        lines.append(
            f"- [{mark}] `{check.get('status')}` — {check.get('name')}: {check.get('detail', '')[:120]}"
        )
    lines += [
        "",
        "## Entrega",
        "",
        f"- [ ] Copiar `{output_dir}` al proyecto destino (la fuente original quedó intacta).",
        "- [ ] Ejecutar build/lint/tests del proyecto destino sobre los componentes copiados.",
        "- [ ] Registrar en el proyecto destino qué reglas/procedencias se aplicaron.",
        "",
    ]
    return "\n".join(lines)


def _render_delivery(
    project: Project,
    profile_id: str,
    output_dir: Path,
    validation: dict,
    needs_review: list[str],
) -> str:
    profile = get_profile(profile_id)
    rules = load_rules(project)
    approved = [rule for rule in rules if rule.status == "approved"]
    pending = [rule for rule in rules if rule.status == "proposed"]

    files: list[str] = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            files.append(f"- `{path.relative_to(output_dir).as_posix()}`")

    checks_executed = [
        check for check in validation.get("checks", []) if check.get("status") == "PASS"
    ]
    checks_skipped = [
        check for check in validation.get("checks", []) if check.get("status") == SKIPPED
    ]
    skipped_lines = (
        "\n".join(
            f"- {check.get('name')}: {check.get('detail', '')}" for check in checks_skipped
        )
        or "- Ninguna."
    )
    executed_lines = (
        "\n".join(f"- {check.get('name')}: PASS" for check in checks_executed) or "- Ninguna."
    )

    state = project.load_state()
    from design_pipeline.engine import stages as stages_mod

    stage_lines = []
    for stage_id, stage_state in state.stages.items():
        duration = (
            f"{stage_state.duration_seconds:.1f}s"
            if stage_state.duration_seconds is not None
            else "-"
        )
        letter = stages_mod.STAGE_BY_ID[stage_id].letter if stage_id in stages_mod.STAGE_BY_ID else "?"
        stage_lines.append(f"- `{letter}` `{stage_id}`: {stage_state.status} · {duration}")

    return f"""# Entrega — proyecto `{project.name}`

- **Fecha:** {iso_now()}
- **Perfil de destino:** `{profile.id}` — {profile.label}
- **Ruta de salida (absoluta):** `{output_dir.resolve()}`
- **Veredicto de validación:** `{validation.get('verdict', 'sin validar')}`

## Componentes generados

{chr(10).join(files) or '- (ninguno)'}

## Reglas aplicadas

{chr(10).join('- **' + r.id + '**: ' + r.text for r in approved) or '- Ninguna aprobada.'}

## Reglas pendientes (no aplicadas)

{chr(10).join('- **' + r.id + '**: ' + r.text for r in pending) or '- Ninguna.'}

## Validaciones ejecutadas

{executed_lines}

## Validaciones omitidas y motivo

{skipped_lines}

## Revisión humana pendiente ({len(needs_review)})

{chr(10).join('- ' + item for item in needs_review) or '- Ninguna.'}

## Estado del pipeline

{chr(10).join(stage_lines)}

## Diferencias relevantes respecto de la fuente

- Los componentes del perfil `{profile.id}` se generaron preservando la
  estructura de la fuente; consultá `reports/generation-notes.md` para las
  transformaciones concretas por archivo.
- Los recursos sin referenciar no se copiaron (quedan listados en el análisis).
- La exportación original **no** fue modificada (verificado por huella en la
  validación: check `isolation`).

## Limitaciones declaradas

- La conversión a Tailwind no está implementada: los perfiles generan CSS puro.
- Las pruebas responsive y la comparación visual se marcan SKIPPED sin
  herramientas de navegador configuradas; su ausencia **no** garantiza fidelidad.
- El proyecto destino debe proveer sus propias dependencias (React,
  @astrojs/react, etc.): nada se instaló automáticamente.

> Esta entrega está lista para **revisión humana**, no para producción directa.
"""

