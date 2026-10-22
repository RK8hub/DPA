"""Paquete de contexto exportable para cargar manualmente en cualquier agente.

Es el mecanismo por defecto de la sección 6: si el entorno no tiene una CLI
compatible (o no se quiere ejecutar nada), el usuario exporta
``context/agent-package/CONTEXT.md`` y lo pega/carga donde prefiera. El
paquete solo incluye datos del workspace (redactados por los mecanismos
existentes) y tareas de revisión; no contiene secretos ni credenciales.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from design_pipeline.engine import stages as stages_mod
from design_pipeline.errors import DesignPipelineError
from design_pipeline.utils import iso_now, write_json
from design_pipeline.workspace.project import Project


def build_context(project: Project) -> dict[str, Any]:
    """Reúne el estado legible por máquina del proyecto para el paquete."""
    state = project.load_state()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": iso_now(),
        "project": project.name,
        "source": str(project.source_path) if project.source_path else None,
        "stages": {},
        "decisions_pending": list(state.decisions_pending),
        "last_validation": state.last_validation,
    }
    for stage_def in stages_mod.STAGES:
        stage_state = state.stage(stage_def.id)
        payload["stages"][stage_def.id] = {
            "letter": stage_def.letter,
            "status": stage_state.status,
            "artifacts": list(stage_state.artifacts),
            "notes": list(stage_state.notes),
        }

    if project.paths.analysis_json.exists():
        analysis = json.loads(project.paths.analysis_json.read_text(encoding="utf-8"))
        payload["analysis"] = {
            "created_at": analysis.get("created_at"),
            "components": [
                component.get("name") for component in analysis.get("components", [])
            ],
            "findings_by_class": {
                kind: sum(
                    1 for f in analysis.get("findings", []) if f.get("classification") == kind
                )
                for kind in ("observed", "inferred", "proposed", "pending")
            },
            "uncertainties": [
                uncertainty.get("question")
                for uncertainty in analysis.get("uncertainties", [])
            ],
            "limitations": analysis.get("limitations", []),
        }
    return payload


def render_context_md(project: Project, payload: dict[str, Any]) -> str:
    from design_pipeline.rules.manager import load_questions, load_rules

    rules = load_rules(project)
    questions = load_questions(project)

    stage_lines = []
    for stage_id, info in payload["stages"].items():
        artifacts = ", ".join(f"`{item}`" for item in info["artifacts"][:3]) or "—"
        stage_lines.append(
            f"| {info['letter']} | `{stage_id}` | {info['status']} | {artifacts} |"
        )

    analysis = payload.get("analysis") or {}
    findings = analysis.get("findings_by_class", {})

    rules_lines = []
    for rule in rules:
        rules_lines.append(
            f"- **{rule.id}** [{rule.status}] ({rule.category}): {rule.text}"
        )
    question_lines = []
    for question in questions:
        answer = f" → `{question.answer}`" if question.answer else ""
        question_lines.append(
            f"- **{question.id}** [{question.status}] ({question.category})"
            f"{answer}: {question.text}"
        )

    output_rel = None
    profile = str(project.data.get("generation", {}).get("profile", "react-css"))
    output_dir = project.paths.output_profile_dir(profile)
    if output_dir.is_dir():
        output_rel = output_dir

    return f"""# Paquete de contexto — proyecto `{project.name}`

Generado: {payload['generated_at']}
Este archivo es el contexto completo exportable para cargar manualmente en un
agente o revisor. No contiene secretos ni credenciales.

## Estado del pipeline

| Letra | Etapa | Estado | Artefactos |
| --- | --- | --- | --- |
{chr(10).join(stage_lines)}

- **Fuente importada:** `{payload['source'] or 'sin importar'}`
- **Decisiones pendientes:** {', '.join(payload['decisions_pending']) or 'ninguna'}
- **Última validación:** `{json.dumps(payload.get('last_validation') or {}, ensure_ascii=False)}`

## Análisis (si existe)

- Componentes: {', '.join('`' + str(name) + '`' for name in analysis.get('components', [])) or '—'}
- Hallazgos por procedencia: Observado {findings.get('observed', 0)} · Inferido {findings.get('inferred', 0)} · Propuesto {findings.get('proposed', 0)} · Pendiente {findings.get('pending', 0)}
- Incertidumbres:
{chr(10).join('- ' + str(q) for q in analysis.get('uncertainties', [])) or '  (ninguna)'}
- Limitaciones de la exportación:
{chr(10).join('- ' + str(item) for item in analysis.get('limitations', [])) or '  (ninguna)'}

## Preguntas y respuestas

{chr(10).join(question_lines) or '- (ninguna registrada)'}

## Reglas de diseño

{chr(10).join(rules_lines) or '- (ninguna registrada)'}

## Salida generada

- Perfil: `{profile}`
- Ruta: `{output_rel or 'aún no generada'}`

## Tareas sugeridas de revisión

1. Comparar cada componente generado con la exportación original (fidelidad
   antes que reinterpretación).
2. Verificar los ítems `NEEDS_REVIEW` de `reports/VALIDATION.md`.
3. Confirmar que la exportación original siguió intacta (check `isolation`).
4. Reportar hallazgos clasificando cada uno como Observado / Inferido /
   Propuesto / Pendiente.

## Límites para el agente que reciba este paquete

- **No modifiques la exportación original** (solo lectura).
- **No ejecutes scripts** declarados en skills ni instales dependencias sin
  aprobación humana explícita.
- **No presentes nada como aprobado**: las reglas `proposed` y las preguntas
  `open` esperan decisión humana.
- Si un dato falta o es ambiguo, marcalo Pendiente en lugar de inventarlo.

## Informes para profundizar

- `reports/ANALYSIS.md` — hallazgos clasificados y procedencia.
- `reports/DECISIONS.md` — respuestas y procedencia de cada decisión.
- `reports/VALIDATION.md` — resultados PASS/FAIL/SKIPPED/NEEDS_REVIEW con evidencia.
- `reports/DELIVERY.md` y `reports/REVIEW-CHECKLIST.md` — entrega y checklist.
- `reports/generation-notes.md` — transformaciones aplicadas por la generación.
"""


def export_context_pack(project: Project) -> dict[str, str]:
    """Escribe ``context/agent-package/CONTEXT.md`` + ``context.json``."""
    if not project.paths.root.is_dir():  # pragma: no cover - load_project lo garantiza
        raise DesignPipelineError("Proyecto inexistente.")
    payload = build_context(project)
    context_dir = project.paths.context_dir
    context_dir.mkdir(parents=True, exist_ok=True)
    md_path = context_dir / "CONTEXT.md"
    md_path.write_text(render_context_md(project, payload), encoding="utf-8")
    json_path = context_dir / "context.json"
    write_json(json_path, payload)
    return {"markdown": str(md_path), "json": str(json_path)}
