"""Flujo de la TUI: menús que delegan siempre en el motor del paquete."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from design_pipeline.config import load_config, workspace_root
from design_pipeline.engine import stages as stages_mod
from design_pipeline.engine.pipeline import Pipeline
from design_pipeline.errors import DesignPipelineError, SkillError
from design_pipeline.tui import console
from design_pipeline.tui.console import TuiAbort, choose, confirm, menu, pause, table
from design_pipeline.utils import dotted_get
from design_pipeline.workspace.project import (
    Project,
    create_project,
    list_projects,
    load_project,
)


def run_tui(workspace_arg: str | None = None) -> int:
    """Bucle principal de la TUI. Devuelve el código de salida."""
    if not console.is_interactive():
        print(
            "La TUI necesita una terminal interactiva.\n"
            "Usá los comandos CLI (design-pipeline --help) para scripting, "
            "o exportá el contexto con `design-pipeline context`."
        )
        return 1
    config = load_config()
    root = workspace_root(config, workspace_arg)
    root.mkdir(parents=True, exist_ok=True)
    try:
        _projects_loop(root)
    except TuiAbort as abort:
        print(f"\n{abort} ¡Hasta luego!")
        return 0
    return 0


# ---------------------------------------------------------------------------
# Selección de proyecto
# ---------------------------------------------------------------------------

def _projects_loop(root: Path) -> None:
    while True:
        names = list_projects(root)
        options = [*(f"Proyecto: {name}" for name in names), "Crear proyecto nuevo"]
        index = menu(f"Workspace: {root}", options)
        if index == len(names):
            _create_project_flow(root)
            continue
        project = load_project(names[index], root)
        _project_loop(project)


def _create_project_flow(root: Path) -> None:
    name = console.ask("Nombre del proyecto (kebab-case)")
    config = load_config()
    try:
        project = create_project(name, root, config)
    except DesignPipelineError as exc:
        print(f"No se pudo crear: {exc}")
        pause()
        return
    from design_pipeline.skills.registry import seed_internal_skills

    seed_internal_skills(project)
    pipeline = Pipeline(project)
    handle = pipeline.begin("init")
    from design_pipeline.doctor import run_doctor

    report = run_doctor(workspace=root)
    missing = [check for check in report.checks if not check.ok]
    pipeline.complete(
        handle,
        artifacts=["project.yaml", "state.yaml"],
        notes=["creado desde la TUI"],
        summary_lines=[f"- Proyecto **{project.name}** inicializado desde la TUI."],
    )
    print(f"Proyecto '{project.name}' creado en {project.paths.root}")
    if missing:
        print("Ausencias detectadas (informativo): " + ", ".join(c.name for c in missing))
    _project_loop(project)


# ---------------------------------------------------------------------------
# Menú del proyecto
# ---------------------------------------------------------------------------

def _project_loop(project: Project) -> None:
    while True:
        pipeline = Pipeline(project)
        try:
            index = menu(
                f"Proyecto {project.name}",
                [
                    "Ver estado del pipeline",
                    "Ejecutar la etapa siguiente (reanudar)",
                    "Responder preguntas de descubrimiento",
                    "Revisar reglas propuestas (aprobar/rechazar)",
                    "Gestionar skills del proyecto",
                    "Elegir perfil de destino",
                    "Ejecutar pipeline hasta la entrega",
                    "Exportar contexto para un agente",
                ],
            )
        except TuiAbort:
            return
        try:
            [
                lambda: _show_status(project),
                lambda: _run_next_stage(project),
                lambda: _answer_questions_flow(project),
                lambda: _rules_flow(project),
                lambda: _skills_flow(project),
                lambda: _profile_flow(project),
                lambda: _full_run_flow(project),
                lambda: _context_flow(project),
            ][index]()
        except DesignPipelineError as exc:
            print(f"\nError: {exc}")
            pause()
        except TuiAbort as abort:
            print(f"\n{abort}")


def _show_status(project: Project) -> None:
    pipeline = Pipeline(project)
    state = project.load_state()
    rows = []
    for stage_def in stages_mod.STAGES:
        stage_state = state.stage(stage_def.id)
        duration = (
            f"{stage_state.duration_seconds:.1f}s"
            if stage_state.duration_seconds is not None
            else "-"
        )
        rows.append(
            [stage_def.letter, stage_def.id, stage_state.status, duration,
             str(len(stage_state.artifacts))]
        )
    table(["", "etapa", "estado", "duración", "#artef"], rows)
    if state.decisions_pending:
        print(f"\nDecisiones pendientes: {', '.join(state.decisions_pending)}")
    pending = pipeline.resumable()
    print(f"Pendientes: {', '.join(pending) or 'ninguna (pipeline completo)'}")
    pause()


def _run_next_stage(project: Project) -> None:
    from design_pipeline.engine.runner import run_stage

    pipeline = Pipeline(project)
    pending = pipeline.resumable()
    if not pending:
        print("Nada pendiente: el pipeline está al día.")
        pause()
        return
    target = pending[0]
    options: dict[str, Any] = {}
    if target == "import":
        source = console.ask("Ruta de la carpeta de la exportación")
        options["source"] = source
    if not confirm(f"Ejecutar etapa `{target}` ahora?", default=True):
        return
    outcome = run_stage(project, pipeline, target, options)
    print(f"Etapa {outcome.stage} completada: {'; '.join(outcome.notes)}")
    pause()


def _answer_questions_flow(project: Project) -> None:
    from design_pipeline.rules.manager import (
        answer_question,
        derive_rules_from_answers,
        load_questions,
    )

    questions = [question for question in load_questions(project) if question.status == "open"]
    if not questions:
        print("No hay preguntas abiertas.")
        print("Iniciá el flujo con: design-pipeline rules init --mode discovery")
        pause()
        return
    answered = 0
    try:
        for question in questions:
            print(f"\n{question.id} ({question.category}) — {question.text}")
            if question.source.startswith("análisis:"):
                print(f"  Procedencia: {question.source}")
            if question.options:
                options = [
                    (option["value"], f"{option['label']}"
                     + ("  (recomendada)" if option["value"] == question.recommendation else ""))
                    for option in question.options
                ]
                options.append(("posponer", "Posponer esta pregunta"))
                value = choose(f"Pregunta {question.id}", options)
                if value is None or value == "posponer":
                    if value == "posponer":
                        answer_question(project, question.id, "", postpone=True)
                    continue
                answer_question(project, question.id, value)
                answered += 1
            else:
                value = console.ask("Tu respuesta (Enter para posponer)")
                if not value:
                    answer_question(project, question.id, "", postpone=True)
                    continue
                answer_question(project, question.id, value)
                answered += 1
    finally:
        # Deriva de reglas idempotente: también si el usuario salió a mitad
        # de la ronda (las respuestas dadas quedan persistidas).
        if answered or any(
            question.status == "answered" for question in load_questions(project)
        ):
            created = derive_rules_from_answers(project)
            if answered:
                print(f"\n{answered} respuestas registradas.")
            if created:
                print(f"Reglas propuestas generadas: {', '.join(rule.id for rule in created)}")
                print("Revisá la sección siguiente del menú para aprobarlas.")
    pause()


def _rules_flow(project: Project) -> None:
    from design_pipeline.rules.manager import decide_rule, load_rules, pending_rules

    rules = pending_rules(project)
    if not rules:
        all_rules = load_rules(project)
        print(f"Sin reglas propuestas. Total registradas: {len(all_rules)}.")
        pause()
        return
    for rule in rules:
        print(f"\n{rule.id} ({rule.category}) — {rule.text}")
        print(f"  Procedencia: {rule.provenance}")
        action = choose(
            f"Regla {rule.id}",
            [
                ("aprobar", "Aprobar (se aplica en spec/generate)"),
                ("rechazar", "Rechazar"),
                ("salir", "Dejar para después"),
            ],
        )
        if action == "aprobar":
            decide_rule(project, rule.id, approve=True)
            print(f"{rule.id}: approved")
        elif action == "rechazar":
            decide_rule(project, rule.id, approve=False)
            print(f"{rule.id}: rejected")
        else:
            break
    pause()


def _skills_flow(project: Project) -> None:
    from design_pipeline.skills.registry import (
        discover_skills,
        set_skill_enabled,
    )

    while True:
        records = discover_skills(project, project.config)
        index = menu(
            "Skills (enter=habilitada, -=deshabilitada)",
            [
                f"{'[x]' if record.enabled else '[ ]'} {record.name} "
                f"({record.origin}, {record.mode}) — {', '.join(record.stages) or '-'}"
                for record in records
            ],
        )
        record = records[index]
        if record.mode == "executive" and not record.enabled:
            allow = bool(dotted_get(project.config, "skills.allow_executive"))
            if not allow:
                print(
                    f"'{record.name}' es executive: requiere skills.allow_executive "
                    "en la configuración para habilitarla."
                )
                pause()
                continue
        set_skill_enabled(project, record.name, not record.enabled)
        print(f"{record.name}: {'habilitada' if not record.enabled else 'deshabilitada'}")


def _profile_flow(project: Project) -> None:
    from design_pipeline.generators.registry import list_profiles

    current = str(project.data.get("generation", {}).get("profile", "react-css"))
    options = [
        (profile["id"], f"{profile['label']} — {profile['description']}")
        for profile in list_profiles()
    ]
    print(f"Perfil actual: {current}")
    choice = choose("Perfil de destino", options)
    if choice:
        generation = dict(project.data.get("generation") or {})
        generation["profile"] = choice
        project.data["generation"] = generation
        project.save_data()
        print(f"Perfil guardado: {choice}")
    pause()


def _context_flow(project: Project) -> None:
    from design_pipeline.adapters.context import export_context_pack

    paths = export_context_pack(project)
    print("Paquete de contexto exportado:")
    print(f"  {paths['markdown']}")
    print(f"  {paths['json']}")
    pause()


def _full_run_flow(project: Project) -> None:
    """Ejecuta todas las etapas pendientes con las puertas de aprobación."""
    from design_pipeline.engine.runner import run_stage

    pipeline = Pipeline(project)
    pending = pipeline.resumable()
    if not pending:
        print("Pipeline completo: nada por ejecutar.")
        pause()
        return

    from design_pipeline.rules.manager import load_questions

    open_questions = [
        question for question in load_questions(project) if question.status == "open"
    ]
    if open_questions:
        print(
            f"\nAtención: {len(open_questions)} preguntas siguen sin responder. "
            "Las reglas derivadas no existirán; se aplicarán solo las aprobadas."
        )
        if not confirm("Continuar igual?", default=False):
            return

    print(f"\nEjecutaré: {', '.join(pending)}")
    if "generate" in pending:
        if not confirm(
            "Aprobás generar el código de salida ahora? (se escribirá en output/)",
            default=False,
        ):
            return
    approve_external = False
    if "validate" in pending:
        approve_external = confirm(
            "¿Permitir comandos externos (build/lint) en validate? Recomendado: no.",
            default=False,
        )

    options: dict[str, Any] = {"approve_external": approve_external}
    if "import" in pending:
        source = console.ask("Ruta de la carpeta de la exportación")
        options["source"] = source

    executed: list[str] = []
    while True:
        still = pipeline.resumable()
        if not still:
            break
        target = still[0]
        try:
            outcome = run_stage(project, pipeline, target, options)
        except DesignPipelineError as exc:
            print(f"\nSe detuvo en `{target}`: {exc}")
            print(f"Etapas ejecutadas en esta corrida: {', '.join(executed) or 'ninguna'}")
            pause()
            return
        executed.append(target)
        print(f"  [ok] {target}: {'; '.join(outcome.notes)}")
        if target == "generate":
            if not confirm("Continuar con validate/report?", default=True):
                break

    print(f"\nCompletadas: {', '.join(executed) or 'ninguna'}")
    still = pipeline.resumable()
    if still:
        print(f"Pendientes: {', '.join(still)}")
    output_dir = project.paths.output_profile_dir(
        str(project.data.get("generation", {}).get("profile", "react-css"))
    )
    if output_dir.is_dir():
        print(f"Ruta de salida: {output_dir.resolve()}")
        print(f"Entrega: {project.paths.reports_dir / 'DELIVERY.md'}")
        print(f"Checklist: {project.paths.reports_dir / 'REVIEW-CHECKLIST.md'}")
    pause()
