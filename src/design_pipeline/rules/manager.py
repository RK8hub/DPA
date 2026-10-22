"""Etapa D: reglas de diseño, preguntas de descubrimiento y decisiones.

Dos modos:

- **Guiado**: el usuario trae reglas en un archivo YAML/Markdown al inicio.
- **Descubrimiento**: se generan preguntas concretas a partir del análisis y
  las respuestas derivan en reglas propuestas que requieren aprobación.

Cada regla y cada respuesta persisten con procedencia y estado. Nada queda
"aprobado" sin una acción explícita del usuario.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from design_pipeline.analysis.analyzer import AnalysisResult, ComponentInfo
from design_pipeline.errors import DesignPipelineError
from design_pipeline.utils import atomic_write_text, iso_now, sha256_text, write_json
from design_pipeline.workspace.project import Project

STATUS_OPEN = "open"
STATUS_ANSWERED = "answered"
STATUS_POSTPONED = "postponed"

RULE_PROPOSED = "proposed"
RULE_APPROVED = "approved"
RULE_REJECTED = "rejected"

VALID_STATUSES = (STATUS_OPEN, STATUS_ANSWERED, STATUS_POSTPONED)
VALID_RULE_STATUSES = (RULE_PROPOSED, RULE_APPROVED, RULE_REJECTED)


@dataclass
class Question:
    id: str
    category: str
    text: str
    options: list[dict[str, str]] = field(default_factory=list)
    recommendation: str = ""
    status: str = STATUS_OPEN
    answer: str | None = None
    source: str = "discovery"
    created_at: str = field(default_factory=iso_now)
    answered_at: str | None = None


@dataclass
class Rule:
    id: str
    text: str
    category: str
    status: str = RULE_PROPOSED
    provenance: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=iso_now)
    decided_at: str | None = None
    decision_by: str | None = None


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def load_questions(project: Project) -> list[Question]:
    path = project.paths.questions_yaml
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Question(**item) for item in data.get("questions", []) if isinstance(item, dict)]


def save_questions(project: Project, questions: list[Question]) -> None:
    payload = {
        "schema_version": 1,
        "updated_at": iso_now(),
        "questions": [asdict(question) for question in questions],
    }
    atomic_write_text(
        project.paths.questions_yaml, yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    )


def load_rules(project: Project) -> list[Rule]:
    path = project.paths.design_rules_yaml
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [Rule(**item) for item in data.get("rules", []) if isinstance(item, dict)]


def save_rules(project: Project, rules: list[Rule]) -> None:
    payload = {
        "schema_version": 1,
        "updated_at": iso_now(),
        "rules": [asdict(rule) for rule in rules],
    }
    atomic_write_text(
        project.paths.design_rules_yaml,
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
    )


# ---------------------------------------------------------------------------
# Preguntas de descubrimiento (generadas desde el análisis)
# ---------------------------------------------------------------------------

_REACT_EXTENSIONS = (".tsx", ".jsx")
_REACT_PACKAGES = {"react", "react-dom", "preact"}


def is_react_component(component: ComponentInfo) -> bool:
    """¿El componente es de React?

    Dos señales, en este orden:

    1. **Extensión JSX/TSX**: `.tsx` **y** `.jsx` son JSX de React. Una
       exportación 100% `.jsx` (el caso más común de Figma/FigCraft) ya es
       React: recomendar `astro-css` obligaría a una conversión adicional
       (issue #5).
    2. **Evidencia en el contenido**: import desde `react`/`preact` o hooks
       `use*`, para archivos con otras extensiones donde la extensión no
       alcanza para decidir.
    """
    if component.path.endswith(_REACT_EXTENSIONS):
        return True
    for importer in component.package_imports:
        if importer.split("/")[0] in _REACT_PACKAGES:
            return True
    return bool(component.hooks)


def build_discovery_questions(analysis: AnalysisResult) -> list[Question]:
    """Preguntas concretas y priorizadas; cada una con opciones y recomendación."""
    questions: list[Question] = []
    react_count = sum(1 for c in analysis.components if is_react_component(c))
    framework_rec = "react-css" if react_count >= len(analysis.components) / 2 else "astro-css"

    questions.append(
        Question(
            id="q-001",
            category="destino",
            text="¿A qué perfil de destino generamos los componentes?",
            options=[
                {
                    "value": "react-css",
                    "label": "React + CSS",
                    "rationale": "La exportación ya es TSX/JSX: máxima fidelidad con menos transformación.",
                },
                {
                    "value": "astro-css",
                    "label": "Astro + CSS",
                    "rationale": "Convierte componentes estáticos a .astro; los interactivos quedan como islas React.",
                },
            ],
            recommendation=framework_rec,
            source="discovery",
        )
    )
    questions.append(
        Question(
            id="q-002",
            category="estilos",
            text="¿Enfoque de estilos para la salida?",
            options=[
                {
                    "value": "css-puro",
                    "label": "CSS puro (archivos del export)",
                    "rationale": "Fidelidad directa; la conversión automática a Tailwind no está implementada.",
                },
                {
                    "value": "tailwind-manual",
                    "label": "Tailwind (conversión manual/asistida)",
                    "rationale": "Requiere trabajo posterior asistido por agente o humano; se documenta como pendiente.",
                },
            ],
            recommendation="css-puro",
            source="discovery",
        )
    )

    adhoc = any(f.kind == "tokens" and f.classification == "proposed" for f in analysis.findings)
    if adhoc:
        questions.append(
            Question(
                id=f"q-{len(questions) + 1:03d}",
                category="tokens",
                text="Hay colores literales sin token en el CSS. ¿Qué hacemos?",
                options=[
                    {
                        "value": "conservar",
                        "label": "Conservar literales (fidelidad estricta)",
                        "rationale": "No cambia nada visualmente.",
                    },
                    {
                        "value": "unificar",
                        "label": "Unificar en tokens existentes",
                        "rationale": "Reduce deriva visual futura, pero altera el CSS de origen (requiere aprobación).",
                    },
                ],
                recommendation="conservar",
                source="discovery",
            )
        )

    if any(c.interactive for c in analysis.components):
        questions.append(
            Question(
                id=f"q-{len(questions) + 1:03d}",
                category="interactividad",
                text="Hay componentes con hooks/eventos. ¿Cómo se generan?",
                options=[
                    {
                        "value": "isla",
                        "label": "Isla React dentro de Astro (fidelidad)",
                        "rationale": "Conserva el comportamiento; requiere integración de framework en Astro.",
                    },
                    {
                        "value": "verbatim",
                        "label": "Copia literal (solo perfil react)",
                        "rationale": "Sin transformación; máxima fidelidad.",
                    },
                ],
                recommendation="isla" if framework_rec == "astro-css" else "verbatim",
                source="discovery",
            )
        )

    if any(f.kind == "accesibilidad" for f in analysis.findings):
        questions.append(
            Question(
                id=f"q-{len(questions) + 1:03d}",
                category="accesibilidad",
                text="Los hallazgos de accesibilidad detectados (alt, teclado): ¿se corrigen o se reportan?",
                options=[
                    {
                        "value": "reportar",
                        "label": "Reportar como NEEDS_REVIEW",
                        "rationale": "Fidelidad estricta; el humano decide cada corrección.",
                    },
                    {
                        "value": "corregir",
                        "label": "Corregir automáticamente (alt, roles, teclado)",
                        "rationale": "Mejora a11y pero modifica el diseño de origen.",
                    },
                ],
                recommendation="reportar",
                source="discovery",
            )
        )

    if analysis.duplications:
        questions.append(
            Question(
                id=f"q-{len(questions) + 1:03d}",
                category="reutilizacion",
                text="Hay componentes con alta similitud textual. ¿Fusionar o mantener separados?",
                options=[
                    {
                        "value": "mantener",
                        "label": "Mantener separados",
                        "rationale": "Similitud textual no implica intercambiables (props/estados pueden diferir).",
                    },
                    {
                        "value": "revisar",
                        "label": "Marcar para revisión humana de fusión",
                        "rationale": "El humano compara props y comportamiento antes de fusionar.",
                    },
                ],
                recommendation="mantener",
                source="discovery",
            )
        )

    # Preguntas derivadas de las incertidumbres del análisis (procedencia trazable).
    for uncertainty in analysis.uncertainties:
        questions.append(
            Question(
                id=f"q-{len(questions) + 1:03d}",
                category=f"análisis:{uncertainty.category}",
                text=uncertainty.question,
                options=[
                    {"value": option_value(o), "label": o, "rationale": ""}
                    for o in uncertainty.options
                ]
                or [{"value": "defer", "label": "Diferir decisión", "rationale": ""}],
                recommendation=option_value(uncertainty.recommendation) if uncertainty.recommendation else "",
                source=f"análisis:{uncertainty.id}",
            )
        )
    return questions


def option_value(label: str) -> str:
    """Convierte una etiqueta en un valor slug usable como respuesta."""
    normalized = unicodedata.normalize("NFKD", label)
    ascii_label = normalized.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", ascii_label.lower()).strip("-")
    return value or "defer"


# ---------------------------------------------------------------------------
# Modo guiado: importar reglas de un archivo del usuario
# ---------------------------------------------------------------------------

def import_rules_file(project: Project, rules_path: Path, approve: bool = False) -> list[Rule]:
    """Importa reglas desde YAML (`rules:`) o Markdown (viñetas `- regla`)."""
    if not rules_path.exists():
        raise DesignPipelineError(f"No existe el archivo de reglas: {rules_path}")
    text = rules_path.read_text(encoding="utf-8")
    existing = load_rules(project)
    existing_texts = {rule.text for rule in existing}
    imported: list[Rule] = []

    entries: list[dict[str, Any]] = []
    if rules_path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict) or "rules" not in data:
            raise DesignPipelineError("El YAML de reglas debe tener la clave `rules` (lista).")
        entries = [item for item in data["rules"] if isinstance(item, dict)]
    else:
        for line in text.splitlines():
            match = re.match(r"^\s*[-*]\s+(.{4,})$", line)
            if match:
                entries.append({"text": match.group(1).strip()})

    digest = sha256_text(text)[:12]
    for index, entry in enumerate(entries, start=1):
        rule_text = str(entry.get("text", "")).strip()
        if not rule_text or rule_text in existing_texts:
            continue
        rule = Rule(
            id=_next_rule_id(existing + imported),
            text=rule_text,
            category=str(entry.get("category", "guiada")),
            status=RULE_APPROVED if approve else RULE_PROPOSED,
            provenance={
                "kind": "user",
                "origin": f"{rules_path.name}#{digest}",
                "note": f"importada línea/regla {index}",
            },
        )
        imported.append(rule)
    all_rules = existing + imported
    save_rules(project, all_rules)
    _sync_pending(project, all_rules, load_questions(project))
    render_rules_reports(project)
    return imported


# ---------------------------------------------------------------------------
# Respuestas y aprobaciones
# ---------------------------------------------------------------------------

def answer_question(
    project: Project, question_id: str, value: str, postpone: bool = False
) -> Question:
    questions = load_questions(project)
    question = _find_question(questions, question_id)
    if question.options and not postpone:
        allowed = {option["value"] for option in question.options}
        if value not in allowed:
            raise DesignPipelineError(
                f"Respuesta inválida para {question.id}: {value!r}. Opciones: {', '.join(sorted(allowed))}"
            )
    if postpone:
        question.status = STATUS_POSTPONED
        question.answer = None
    else:
        question.status = STATUS_ANSWERED
        question.answer = value
        question.answered_at = iso_now()
    save_questions(project, questions)
    return question


def derive_rules_from_answers(project: Project) -> list[Rule]:
    """Convierte respuestas en reglas propuestas (nunca aprobadas automáticamente)."""
    questions = {question.id: question for question in load_questions(project)}
    rules = load_rules(project)
    existing_origins = {
        rule.provenance.get("origin", "") for rule in rules
    }
    created: list[Rule] = []

    templates: dict[str, dict[str, str]] = {
        "q-001": {
            "react-css": "Generar los componentes con el perfil react-css (React + CSS puro).",
            "astro-css": "Generar los componentes con el perfil astro-css (Astro + CSS; islas React para interactivos).",
        },
        "q-002": {
            "css-puro": "Usar CSS puro basado en los archivos del export; no introducir frameworks de utilidades.",
            "tailwind-manual": "La conversión a Tailwind queda como trabajo manual/asistido posterior (pendiente explícito).",
        },
        "q-tokens-conservar": {
            "conservar": "Conservar los colores y medidas literales del export tal cual (fidelidad estricta).",
        },
    }

    # Reglas de preguntas base.
    for question_id, mapping in templates.items():
        question = questions.get(question_id)
        if question and question.status == STATUS_ANSWERED and question.answer in mapping:
            origin = f"answer:{question_id}"
            if origin in existing_origins:
                continue
            created.append(
                Rule(
                    id=_next_rule_id(rules + created),
                    text=mapping[question.answer],
                    category=question.category,
                    provenance={"kind": "derived", "origin": origin},
                )
            )

    # Reglas derivadas de las preguntas de incertidumbre del análisis.
    for question in questions.values():
        if question.status != STATUS_ANSWERED or not question.source.startswith("análisis:"):
            continue
        origin = f"answer:{question.id}"
        if origin in existing_origins:
            continue
        created.append(
            Rule(
                id=_next_rule_id(rules + created),
                text=f"{question.text} → Respuesta registrada: {question.answer}",
                category=question.category,
                provenance={"kind": "derived", "origin": origin},
            )
        )

    all_rules = rules + created
    save_rules(project, all_rules)
    # Refleja la elección de perfil en la configuración del proyecto.
    target = questions.get("q-001")
    if target and target.status == STATUS_ANSWERED and target.answer in {"react-css", "astro-css"}:
        generation = dict(project.data.get("generation") or {})
        generation["profile"] = target.answer
        project.data["generation"] = generation
        project.save_data()
    _sync_pending(project, all_rules, load_questions(project))
    render_rules_reports(project)
    return created


def decide_rule(
    project: Project, rule_id: str, approve: bool, decision_by: str = "usuario"
) -> Rule:
    rules = load_rules(project)
    rule = next((r for r in rules if r.id == rule_id), None)
    if rule is None:
        raise DesignPipelineError(f"No existe la regla {rule_id}.")
    rule.status = RULE_APPROVED if approve else RULE_REJECTED
    rule.decided_at = iso_now()
    rule.decision_by = decision_by
    save_rules(project, rules)
    _sync_pending(project, rules, load_questions(project))
    render_rules_reports(project)
    return rule


def approved_rules(project: Project) -> list[Rule]:
    return [rule for rule in load_rules(project) if rule.status == RULE_APPROVED]


def pending_rules(project: Project) -> list[Rule]:
    return [rule for rule in load_rules(project) if rule.status == RULE_PROPOSED]


# ---------------------------------------------------------------------------
# Reportes e informes
# ---------------------------------------------------------------------------

def _next_rule_id(rules: list[Rule]) -> str:
    numbers = []
    for rule in rules:
        match = re.match(r"r-(\d+)", rule.id)
        if match:
            numbers.append(int(match.group(1)))
    return f"r-{(max(numbers) + 1 if numbers else 1):03d}"


def _find_question(questions: list[Question], question_id: str) -> Question:
    for question in questions:
        if question.id == question_id:
            return question
    raise DesignPipelineError(
        f"No existe la pregunta {question_id}. Disponibles: "
        + ", ".join(q.id for q in questions[:20])
    )


def _sync_pending(project: Project, rules: list[Rule], questions: list[Question]) -> None:
    pending: list[str] = []
    pending.extend(question.id for question in questions if question.status == STATUS_OPEN)
    pending.extend(rule.id for rule in rules if rule.status == RULE_PROPOSED)
    if project.paths.state_yaml.exists():
        state = project.load_state()
    else:
        # La etapa D puede invocarse sin pasar por Pipeline.begin (p. ej. TUI).
        from design_pipeline.engine.state import ProjectState

        state = ProjectState(project=project.name)
        project.state = state
    state.decisions_pending = pending
    project.save_state()


def render_rules_reports(project: Project) -> None:
    """Genera DECISIONS.md y DESIGN-RULES.md de forma idempotente desde los datos."""
    questions = load_questions(project)
    rules = load_rules(project)

    decision_lines = [
        "# Decisiones del proyecto",
        "",
        "Registro de respuestas, procedencia y estado. Regenerado desde los datos máquina;",
        "editar directamente no tiene efecto (usar los comandos `rules answer` / `rules approve`).",
        "",
        "## Preguntas",
        "",
    ]
    if not questions:
        decision_lines.append("- Sin preguntas registradas (modo guiado o etapa no ejecutada).")
    for question in questions:
        decision_lines.append(f"### {question.id} ({question.category}) — {question.status}")
        decision_lines.append("")
        decision_lines.append(f"- Pregunta: {question.text}")
        decision_lines.append(f"- Procedencia: {question.source}")
        if question.answer is not None:
            decision_lines.append(f"- Respuesta: `{question.answer}` (registrada {question.answered_at})")
        if question.options:
            options = ", ".join(f"`{o['value']}`" for o in question.options)
            decision_lines.append(f"- Opciones: {options}")
        if question.recommendation:
            decision_lines.append(f"- Recomendación: `{question.recommendation}`")
        decision_lines.append("")

    decision_lines.append("## Reglas")
    decision_lines.append("")
    if not rules:
        decision_lines.append("- Sin reglas registradas.")
    for rule in rules:
        origin = rule.provenance.get("origin", "?")
        decision_lines.append(
            f"- **{rule.id}** [{rule.status}] ({rule.category}) — {rule.text}"
        )
        decision_lines.append(
            f"  - Procedencia: {rule.provenance.get('kind', '?')} → `{origin}`"
            + (f"; decisión: {rule.decision_by} {rule.decided_at}" if rule.decided_at else "")
        )
    decision_lines.append("")
    atomic_write_text(
        project.paths.reports_dir / "DECISIONS.md", "\n".join(decision_lines)
    )

    rules_lines = [
        "# Reglas de diseño",
        "",
        f"Actualizado: {iso_now()}",
        "",
        "Las reglas `proposed` todavía no se aplican. Aprobá con "
        "`design-pipeline rules approve --id <regla>` (o `--all`).",
        "",
    ]
    for status, title in (
        (RULE_APPROVED, "Aprobadas (se aplican en spec/generate)"),
        (RULE_PROPOSED, "Propuestas (pendientes de aprobación)"),
        (RULE_REJECTED, "Rechazadas"),
    ):
        subset = [rule for rule in rules if rule.status == status]
        rules_lines.append(f"## {title}")
        rules_lines.append("")
        if not subset:
            rules_lines.append("- (ninguna)")
        for rule in subset:
            rules_lines.append(f"- **{rule.id}** ({rule.category}): {rule.text}")
        rules_lines.append("")
    atomic_write_text(project.paths.reports_dir / "DESIGN-RULES.md", "\n".join(rules_lines))


def seed_discovery(project: Project, analysis: AnalysisResult) -> list[Question]:
    """Crea las preguntas de descubrimiento (idempotente: no duplica existentes)."""
    existing = load_questions(project)
    if existing:
        return existing
    questions = build_discovery_questions(analysis)
    save_questions(project, questions)
    _sync_pending(project, load_rules(project), questions)
    render_rules_reports(project)
    return questions
