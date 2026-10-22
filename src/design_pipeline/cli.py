"""Interfaz de línea de comandos de design-pipeline.

La CLI es una capa delgada: resuelve proyecto/configuración, llama al motor y
formatea la salida. Toda la lógica de negocio vive en los módulos del paquete
(inportadores, análisis, reglas, generadores, validadores), de modo que la TUI
y la CLI comparten el mismo motor.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

import yaml

from design_pipeline import __version__
from design_pipeline.config import load_config, workspace_root
from design_pipeline.doctor import render_text as doctor_render_text
from design_pipeline.doctor import run_doctor
from design_pipeline.engine import stages as stages_mod
from design_pipeline.engine.pipeline import Pipeline
from design_pipeline.engine.state import ProjectState
from design_pipeline.errors import DesignPipelineError
from design_pipeline.utils import dotted_get, iso_now
from design_pipeline.workspace import project as project_mod
from design_pipeline.workspace.project import Project, create_project, load_project

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Utilidades de CLI
# ---------------------------------------------------------------------------

def _print(data: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif isinstance(data, str):
        print(data)
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))


def _open_project(args: argparse.Namespace) -> tuple[Project, Pipeline]:
    if not getattr(args, "project", None):
        raise DesignPipelineError("Este comando requiere --project NOMBRE.")
    config = load_config()
    root = workspace_root(config, getattr(args, "workspace", None))
    project = load_project(args.project, root)
    pipeline = Pipeline(project)
    return project, pipeline


# ---------------------------------------------------------------------------
# Comandos base (etapas A, diagnóstico y estado)
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    config = load_config()
    root = workspace_root(config, args.workspace)
    root.mkdir(parents=True, exist_ok=True)
    project = create_project(args.name, root, config)
    from design_pipeline.skills.registry import seed_internal_skills

    enabled_skills = seed_internal_skills(project)
    pipeline = Pipeline(project)

    handle = pipeline.begin("init")
    report = run_doctor(workspace=root)
    missing = [check for check in report.checks if not check.ok]
    pipeline.state.source_path = None
    pipeline.complete(
        handle,
        artifacts=["project.yaml", "state.yaml"],
        notes=[
            f"workspace: {root}",
            "skills internas habilitadas: " + ", ".join(enabled_skills),
            "detectadas ausencias: " + (", ".join(c.name for c in missing) or "ninguna"),
        ],
        summary_lines=[
            f"- Proyecto **{project.name}** inicializado en `{project.paths.root}`.",
            f"- Dependencias ausentes: {', '.join(c.name for c in missing) or 'ninguna'}.",
        ],
    )
    if args.json:
        _print(
            {
                "project": project.name,
                "path": str(project.paths.root),
                "workspace": str(root),
                "missing_dependencies": [check.name for check in missing],
            },
            True,
        )
    else:
        print(f"Proyecto '{project.name}' creado en {project.paths.root}")
        print(f"Workspace: {root}")
        if missing:
            print("\nDependencias ausentes (no bloqueantes salvo que sean requeridas):")
            for check in missing:
                print(f"  - {check.name}: {check.detail}")
                if check.remedy:
                    print(f"    -> {check.remedy}")
        print("\nSiguiente paso sugerido:")
        print(f"  design-pipeline import <carpeta-exportacion> --project {project.name}")
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config()
    root = workspace_root(config, args.workspace)
    report = run_doctor(workspace=root if root.exists() else None)
    if args.json:
        _print(report.to_dict(), True)
    else:
        print(doctor_render_text(report))
    return EXIT_OK if report.ok else EXIT_ERROR


def cmd_import(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.importers.stage import run_import

    source = Path(args.source).expanduser().resolve()
    handle = pipeline.begin("import")
    try:
        summary = run_import(project, source)
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    pipeline.complete(
        handle,
        artifacts=["inventory.json", "reports/IMPORT-REPORT.md"],
        notes=[
            f"archivos: {summary['files']}",
            f"duplicados: {summary['duplicates']}",
            f"referencias rotas: {summary['broken_references']}",
            f"no analizados: {summary['unanalyzed']}",
        ],
        summary_lines=[
            f"- Importación de `{source}`: {summary['files']} archivos, "
            f"{summary['duplicates']} grupos duplicados, "
            f"{summary['broken_references']} referencias rotas."
        ],
    )
    payload = {"project": project.name, "source": str(source), **summary}
    if args.json:
        _print(payload, True)
    else:
        print(f"Importados {summary['files']} archivos desde {source}")
        print(f"Duplicados: {summary['duplicates']} | Referencias rotas: {summary['broken_references']}"
              f" | No analizados: {summary['unanalyzed']}")
        print(f"Informe: {project.paths.reports_dir / 'IMPORT-REPORT.md'}")
        print(f"\nSiguiente paso: design-pipeline analyze --project {project.name}")
    return EXIT_OK


def cmd_analyze(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.analysis.stage import run_analyze

    handle = pipeline.begin("analyze")
    try:
        result = run_analyze(project)
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    artifacts = [
        "analysis.json",
        "reports/ANALYSIS.md",
        "reports/COMPONENT-MAP.md",
        "reports/uncertainties.md",
    ]
    pipeline.complete(
        handle,
        artifacts=artifacts,
        notes=[
            f"componentes: {len(result.components)}",
            f"hallazgos: {len(result.findings)}",
            f"incertidumbres: {len(result.uncertainties)}",
        ],
        summary_lines=[
            f"- Análisis: {len(result.components)} componentes, "
            f"{len(result.stylesheets)} hojas de estilo, "
            f"{len(result.uncertainties)} incertidumbres."
        ],
    )
    payload = {
        "project": project.name,
        "components": [component.name for component in result.components],
        "findings": len(result.findings),
        "uncertainties": len(result.uncertainties),
        "limitations": len(result.limitations),
    }
    if args.json:
        _print(payload, True)
    else:
        print(f"Analizados {len(result.components)} componentes y {len(result.stylesheets)} hojas de estilo.")
        print(f"Hallazgos: {len(result.findings)} | Incertidumbres: {len(result.uncertainties)}"
              f" | Limitaciones: {len(result.limitations)}")
        print(f"Informe: {project.paths.reports_dir / 'ANALYSIS.md'}")
        print(f"\nSiguiente paso: design-pipeline rules init --mode discovery --project {project.name}")
    return EXIT_OK


def cmd_rules_init(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.rules.manager import import_rules_file, seed_discovery

    handle = pipeline.begin("rules")
    try:
        if args.mode == "guided":
            if not args.rules_file:
                raise DesignPipelineError(
                    "El modo guiado requiere --rules-file (YAML con `rules:` o Markdown con viñetas)."
                )
            imported = import_rules_file(
                project, Path(args.rules_file).expanduser().resolve(), approve=args.approve
            )
            detail = f"{len(imported)} reglas importadas desde {args.rules_file}"
        else:
            from design_pipeline.analysis.stage import load_analysis

            if not project.paths.analysis_json.exists():
                raise DesignPipelineError(
                    "El modo descubrimiento requiere la etapa analyze previa."
                )
            analysis = load_analysis(project)
            questions = seed_discovery(project, analysis)
            detail = f"{len(questions)} preguntas de descubrimiento generadas"
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    pipeline.complete(
        handle,
        artifacts=[
            "rules/design-rules.yaml",
            "rules/questions.yaml",
            "reports/DESIGN-RULES.md",
            "reports/DECISIONS.md",
        ],
        notes=[detail],
        summary_lines=[f"- Reglas: {detail}."],
    )
    payload = {"project": project.name, "mode": args.mode, "detail": detail}
    if args.json:
        _print(payload, True)
    else:
        print(detail)
        if args.mode == "discovery":
            print(f"Responder con: design-pipeline rules answer --project {project.name} --id q-001 --value <valor>")
            print(f"Ver preguntas:  design-pipeline rules show --project {project.name}")
        else:
            print(f"Aprobar reglas: design-pipeline rules approve --project {project.name} --all")
    return EXIT_OK


def cmd_rules_answer(args: argparse.Namespace) -> int:
    project, _pipeline = _open_project(args)
    from design_pipeline.rules.manager import (
        answer_question,
        derive_rules_from_answers,
    )

    answers: list[tuple[str, str]] = []
    if args.answers_file:
        data = yaml.safe_load(Path(args.answers_file).expanduser().read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise DesignPipelineError("El archivo de respuestas debe ser un mapping {id: valor}.")
        answers = [(key, str(value)) for key, value in data.items()]
    elif args.id and args.value:
        answers = [(args.id, args.value)]
    else:
        raise DesignPipelineError("Usá --id/--value o --answers-file.")

    answered = []
    errors = []
    for question_id, value in answers:
        try:
            question = answer_question(project, question_id, value, postpone=args.postpone)
            answered.append({"id": question.id, "status": question.status, "answer": question.answer})
        except DesignPipelineError as exc:
            errors.append(str(exc))
    created = derive_rules_from_answers(project)
    payload = {
        "project": project.name,
        "answered": answered,
        "rules_created": [rule.id for rule in created],
        "errors": errors,
    }
    if args.json:
        _print(payload, True)
    else:
        for item in answered:
            print(f"{item['id']}: {item['status']} → {item['answer'] or '(pospuesta)'}")
        if created:
            print(f"\nReglas propuestas generadas: {', '.join(r.id for r in created)}")
            print(f"Aprobar: design-pipeline rules approve --project {project.name} --all")
        for error in errors:
            print(f"Aviso: {error}")
    return EXIT_OK if not errors else EXIT_ERROR


def cmd_rules_approve(args: argparse.Namespace) -> int:
    project, _pipeline = _open_project(args)
    from design_pipeline.rules.manager import decide_rule, load_rules

    if args.all:
        targets = [rule.id for rule in load_rules(project) if rule.status == "proposed"]
    elif args.id:
        targets = list(args.id)
    else:
        raise DesignPipelineError("Usá --id <regla> (repetible) o --all.")
    decided = []
    for rule_id in targets:
        rule = decide_rule(project, rule_id, approve=not args.reject)
        decided.append({"id": rule.id, "status": rule.status})
    payload = {"project": project.name, "decided": decided}
    if args.json:
        _print(payload, True)
    else:
        for item in decided:
            print(f"{item['id']}: {item['status']}")
    return EXIT_OK


def cmd_rules_show(args: argparse.Namespace) -> int:
    project, _pipeline = _open_project(args)
    from design_pipeline.rules.manager import load_questions, load_rules

    questions = load_questions(project)
    rules = load_rules(project)
    payload = {
        "project": project.name,
        "questions": [
            {
                "id": question.id,
                "category": question.category,
                "status": question.status,
                "text": question.text,
                "options": [option["value"] for option in question.options],
                "recommendation": question.recommendation,
                "answer": question.answer,
                "source": question.source,
            }
            for question in questions
        ],
        "rules": [
            {
                "id": rule.id,
                "status": rule.status,
                "category": rule.category,
                "text": rule.text,
                "provenance": rule.provenance,
            }
            for rule in rules
        ],
    }
    if args.json:
        _print(payload, True)
        return EXIT_OK
    print(f"Proyecto: {project.name}")
    print("\nPreguntas:")
    if not questions:
        print("  (ninguna — ejecutá `rules init --mode discovery` o `--mode guided`)")
    for question in questions:
        answer = f" → {question.answer}" if question.answer else ""
        print(f"  {question.id} [{question.status}] ({question.category}){answer}: {question.text}")
        if question.status == "open" and question.options:
            opciones = ", ".join(o["value"] for o in question.options)
            rec = f" (recomendada: {question.recommendation})" if question.recommendation else ""
            print(f"      opciones: {opciones}{rec}")
    print("\nReglas:")
    if not rules:
        print("  (ninguna)")
    for rule in rules:
        origin = rule.provenance.get("origin", "?")
        print(f"  {rule.id} [{rule.status}] ({rule.category}) {rule.text}  <- {origin}")
    return EXIT_OK


def cmd_spec(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.spec.builder import build_specs

    handle = pipeline.begin("spec")
    try:
        payload = build_specs(project)
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    artifacts = ["specs/index.json"] + [
        f"specs/components/{item['name']}.json" for item in payload["components"]
    ]
    pipeline.complete(
        handle,
        artifacts=artifacts,
        notes=[f"componentes especificados: {len(payload['components'])}"],
        summary_lines=[
            f"- Especificación: {len(payload['components'])} componentes "
            f"(reglas aplicadas: {', '.join(payload['approved_rules']) or 'ninguna'})."
        ],
    )
    payload_out = {"project": project.name, **payload}
    if args.json:
        _print(payload_out, True)
    else:
        names = ", ".join(item["name"] for item in payload["components"])
        print(f"Especificaciones generadas: {names}")
        print(f"Índice: {project.paths.specs_dir / 'index.json'}")
        print(f"\nSiguiente paso: design-pipeline generate --project {project.name}")
    return EXIT_OK


def cmd_generate(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.generators.registry import get_profile
    from design_pipeline.generators.stage import run_generate

    profile_id = args.profile or str(
        project.data.get("generation", {}).get("profile", "react-css")
    )
    get_profile(profile_id)  # valida antes de abrir la etapa
    handle = pipeline.begin("generate")
    try:
        profile, result, output_dir = run_generate(project, profile_id)
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    artifacts = ["reports/generation-notes.md", "output/" + profile.id]
    pipeline.complete(
        handle,
        artifacts=artifacts,
        notes=[
            f"perfil: {profile.id}",
            f"archivos: {len(result.files)}",
            f"needs_review: {len(result.needs_review)}",
        ],
        summary_lines=[
            f"- Generación ({profile.id}): {len(result.files)} archivos, "
            f"{len(result.needs_review)} ítems de revisión."
        ],
    )
    payload = {
        "project": project.name,
        "profile": profile.id,
        "output": str(output_dir),
        "files": len(result.files),
        "needs_review": result.needs_review,
    }
    if args.json:
        _print(payload, True)
    else:
        print(f"Perfil: {profile.id} — {profile.label}")
        print(f"Archivos generados: {len(result.files)} en {output_dir}")
        if result.needs_review:
            print(f"Revisión humana pendiente ({len(result.needs_review)}):")
            for item in result.needs_review:
                print(f"  - {item}")
        print(f"\nSiguiente paso: design-pipeline validate --project {project.name}")
    return EXIT_OK


def cmd_validate(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.validators.runner import (
        FAIL,
        run_validate,
        write_validation_report,
    )

    profile_id = args.profile or str(
        project.data.get("generation", {}).get("profile", "react-css")
    )
    handle = pipeline.begin("validate")
    try:
        report = run_validate(project, profile_id, approve_external=args.approve_external)
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    write_validation_report(project, report)
    pipeline.complete(
        handle,
        artifacts=["reports/validation-report.json", "reports/VALIDATION.md"],
        notes=[
            f"veredicto: {report.verdict}",
            *[
                f"{check.id}: {check.status}"
                for check in report.checks
                if check.status != "PASS"
            ],
        ],
        summary_lines=[
            f"- Validación ({profile_id}): veredicto `{report.verdict}` "
            f"(PASS {report.summary.get('PASS', 0)}, FAIL {report.summary.get('FAIL', 0)}, "
            f"SKIPPED {report.summary.get('SKIPPED', 0)}, "
            f"NEEDS_REVIEW {report.summary.get('NEEDS_REVIEW', 0)})."
        ],
    )
    payload = {"project": project.name, **report.to_dict()}
    if args.json:
        _print(payload, True)
    else:
        print(f"Veredicto: {report.verdict}")
        print(
            f"PASS {report.summary.get('PASS', 0)} | FAIL {report.summary.get('FAIL', 0)} | "
            f"SKIPPED {report.summary.get('SKIPPED', 0)} | "
            f"NEEDS_REVIEW {report.summary.get('NEEDS_REVIEW', 0)}"
        )
        for check in report.checks:
            if check.status != "PASS":
                print(f"  [{check.status}] {check.name}: {check.detail[:100]}")
        print(f"\nInforme: {project.paths.reports_dir / 'VALIDATION.md'}")
        print(f"Siguiente paso: design-pipeline report --project {project.name}")
    if report.summary.get(FAIL):
        return EXIT_ERROR
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.reporting.summary import run_report

    handle = pipeline.begin("report")
    try:
        summary = run_report(project, args.profile)
    except DesignPipelineError as exc:
        pipeline.fail(handle, str(exc))
        raise
    pipeline.complete(
        handle,
        artifacts=["reports/DELIVERY.md", "reports/REVIEW-CHECKLIST.md"],
        notes=[f"veredicto: {summary['verdict']}", f"salida: {summary['output']}"],
        summary_lines=[
            f"- Entrega generada. Salida: `{summary['output']}` "
            f"(veredicto `{summary['verdict']}`, {summary['needs_review_count']} ítems de revisión)."
        ],
    )
    if args.json:
        _print({"project": project.name, **summary}, True)
    else:
        print(f"Entrega: {summary['delivery']}")
        print(f"Checklist: {summary['checklist']}")
        print(f"Salida: {summary['output']}")
        print(f"Veredicto de validación: {summary['verdict']}")
        print(f"Ítems de revisión humana: {summary['needs_review_count']}")
    return EXIT_OK


def _skills_context(args: argparse.Namespace) -> tuple[Project | None, dict[str, Any]]:
    config = load_config()
    project = None
    if getattr(args, "project", None):
        root = workspace_root(config, getattr(args, "workspace", None))
        project = load_project(args.project, root)
    return project, config


def cmd_skills_list(args: argparse.Namespace) -> int:
    project, config = _skills_context(args)
    from design_pipeline.skills.registry import discover_skills

    records = discover_skills(project, config)
    payload = {"skills": [record.to_dict() for record in records]}
    if args.json:
        _print(payload, True)
        return EXIT_OK
    if not records:
        print("Sin skills registradas.")
        return EXIT_OK
    print(f"{'NOMBRE':<22} {'ORIGEN':<9} {'MODO':<12} {'ETAPAS':<22} {'HAB':<4} VERSIÓN")
    for record in records:
        print(
            f"{record.name:<22} {record.origin:<9} {record.mode:<12} "
            f"{','.join(record.stages) or '-':<22} {'sí' if record.enabled else 'no':<4} "
            f"{record.version or '-'}"
        )
    if project is None:
        print("\n(Sin --project: no se muestra la habilitación por proyecto.)")
    return EXIT_OK


def cmd_skills_inspect(args: argparse.Namespace) -> int:
    project, config = _skills_context(args)
    from design_pipeline.skills.registry import find_skill

    record = find_skill(project, config, args.name)
    if record is None:
        raise DesignPipelineError(f"No existe la skill '{args.name}'.")
    if args.json:
        _print(record.to_dict(), True)
        return EXIT_OK
    print(f"Skill: {record.name}  (origen: {record.origin}, habilitada: {'sí' if record.enabled else 'no'})")
    print(f"Descripción: {record.description}")
    print(f"Versión: {record.version or '-'}   Modo: {record.mode}   Hash: {record.digest[:16]}…")
    print(f"Permisos: {', '.join(record.permissions) or 'ninguno'}")
    print(f"Herramientas: {', '.join(record.tools) or 'ninguna'}")
    print(f"Etapas: {', '.join(record.stages) or 'ninguna'}")
    if record.scripts:
        print("\nScripts declarados (NO se ejecutan automáticamente):")
        for script in record.scripts:
            print(f"  - {script}")
    else:
        print("\nScripts declarados: ninguno.")
    print(f"\nRuta: {record.path}")
    print("\n--- inicio del cuerpo (preview) ---")
    print(record.body_preview)
    return EXIT_OK


def cmd_skills_validate(args: argparse.Namespace) -> int:
    project, config = _skills_context(args)
    from design_pipeline.skills.registry import find_skill, validate_skill_dir

    target_path = Path(args.target).expanduser()
    if target_path.is_dir():
        validation = validate_skill_dir(target_path)
    else:
        record = find_skill(project, config, args.target)
        if record is None:
            raise DesignPipelineError(f"No existe la skill '{args.target}' ni la carpeta {target_path}.")
        validation = validate_skill_dir(Path(record.path), assumed_name=record.name)
    payload = {
        "ok": validation.ok,
        "errors": validation.errors,
        "warnings": validation.warnings,
    }
    if args.json:
        _print(payload, True)
    else:
        print("VÁLIDA" if validation.ok else "INVÁLIDA")
        for error in validation.errors:
            print(f"  error: {error}")
        for warning in validation.warnings:
            print(f"  aviso: {warning}")
    return EXIT_OK if validation.ok else EXIT_ERROR


def cmd_skills_add(args: argparse.Namespace) -> int:
    project, config = _skills_context(args)
    from design_pipeline.skills.registry import add_skill

    target = "project" if args.project else "global"
    record = add_skill(Path(args.path), project, config, target=target)
    payload = record.to_dict()
    if args.json:
        _print(payload, True)
    else:
        print(f"Skill '{record.name}' importada a {target} desde {args.path}")
        print(f"Hash de archivos: {record.digest[:16]}…")
        if record.scripts:
            print("Scripts declarados (NO ejecutados): " + ", ".join(record.scripts))
        print("Ningún archivo de la skill fue ejecutado durante la importación.")
        print(f"Habilitar con: design-pipeline skills enable {record.name}"
              + (f" --project {project.name}" if project else " --project <proyecto>"))
    return EXIT_OK


def cmd_skills_enable(args: argparse.Namespace) -> int:
    project, config = _skills_context(args)
    if project is None:
        raise DesignPipelineError("Habilitar/deshabilitar requiere --project.")
    from design_pipeline.skills.registry import find_skill, set_skill_enabled

    record = find_skill(project, config, args.name)
    if record is None:
        raise DesignPipelineError(f"No existe la skill '{args.name}'.")
    if record.mode == "executive" and args.enable and not bool(
        dotted_get(config, "skills.allow_executive")
    ):
        raise DesignPipelineError(
            f"'{record.name}' es executive: activá skills.allow_executive en la configuración "
            "para poder habilitarla."
        )
    set_skill_enabled(project, args.name, args.enable)
    state = "habilitada" if args.enable else "deshabilitada"
    if args.json:
        _print({"skill": args.name, "enabled": args.enable}, True)
    else:
        print(f"Skill '{args.name}' {state} para el proyecto {project.name}.")
    return EXIT_OK


def cmd_skills_remove(args: argparse.Namespace) -> int:
    project, config = _skills_context(args)
    from design_pipeline.skills.registry import remove_skill

    message = remove_skill(project, config, args.name, confirm=args.yes)
    if args.json:
        _print({"removed": args.name}, True)
    else:
        print(message)
    return EXIT_OK


def cmd_resume(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    from design_pipeline.engine.runner import resume_pipeline

    pending_before = pipeline.resumable()
    if not pending_before:
        if args.json:
            _print({"project": project.name, "executed": [], "pending": []}, True)
        else:
            print(f"Proyecto {project.name}: nada pendiente (todas las etapas al día).")
        return EXIT_OK

    options: dict[str, Any] = {
        "source": args.source,
        "profile": args.profile,
        "approve_external": args.approve_external,
    }
    try:
        outcomes = resume_pipeline(project, pipeline, options, until=args.until)
    except DesignPipelineError as exc:
        print(f"Reanudación detenida: {exc}", file=sys.stderr)
        return EXIT_ERROR

    payload = {
        "project": project.name,
        "executed": [
            {"stage": outcome.stage, "notes": outcome.notes, **outcome.payload}
            for outcome in outcomes
        ],
        "pending": pipeline.resumable(),
    }
    if args.json:
        _print(payload, True)
    else:
        print(f"Reanudado proyecto {project.name}: {len(outcomes)} etapas ejecutadas.")
        for outcome in outcomes:
            print(f"  - {outcome.stage}: {'; '.join(outcome.notes)}")
        still = pipeline.resumable()
        if still:
            print(f"\nQuedan pendientes: {', '.join(still)}")
            print("Reglas/decisiones sin resolver suelen ser la causa: revisá "
                  f"`design-pipeline rules show --project {project.name}`.")
        else:
            print("\nPipeline completo. Revisá reports/DELIVERY.md y REVIEW-CHECKLIST.md.")
    return EXIT_OK


def cmd_tui(args: argparse.Namespace) -> int:
    from design_pipeline.tui import run_tui

    return run_tui(args.workspace)


def cmd_context(args: argparse.Namespace) -> int:
    project, _pipeline = _open_project(args)
    from design_pipeline.adapters.context import export_context_pack

    paths = export_context_pack(project)
    if args.json:
        _print({"project": project.name, **paths}, True)
    else:
        print(f"Paquete de contexto exportado:")
        print(f"  Markdown: {paths['markdown']}")
        print(f"  Machine:  {paths['json']}")
        print("\nCargalo manualmente en tu agente o revisor; no contiene secretos.")
    return EXIT_OK


def cmd_agent_list(args: argparse.Namespace) -> int:
    config = load_config()
    if getattr(args, "project", None):
        root = workspace_root(config, getattr(args, "workspace", None))
        config = load_config(project_dir=root / args.project)
    from design_pipeline.adapters.registry import detect_adapters

    adapters = detect_adapters(config)
    payload = {"adapters": [adapter.to_dict() for adapter in adapters]}
    if args.json:
        _print(payload, True)
        return EXIT_OK
    if not adapters:
        print("Ningún adaptador declarado.")
        print("Declaralos en agent.adapters (ver docs/AGENT-ADAPTERS.md).")
        print("La detección informativa de CLIs de agente está en `design-pipeline doctor`.")
        return EXIT_OK
    print(f"{'ID':<16} {'DETECCIÓN':<14} {'ESTADO':<22} MÉTODO PROMPT")
    for adapter in adapters:
        print(
            f"{adapter.id:<16} {adapter.detection or '(solo config)':<14} "
            f"{adapter.status:<22} {adapter.prompt_method}"
        )
        if adapter.executable_path:
            print(f"  ejecutable: {adapter.executable_path}")
    print("\nEstado 'detected-not-run' = detectado pero NO ejecutado todavía.")
    print("Ejecutar exige agent.allow_execution + --allow-execution (y queda en el log).")
    return EXIT_OK


def cmd_agent_run(args: argparse.Namespace) -> int:
    project, _pipeline = _open_project(args)
    from design_pipeline.adapters.context import export_context_pack
    from design_pipeline.adapters.registry import run_adapter
    from design_pipeline.engine.log import RunLogger
    from design_pipeline.utils import new_run_id, sha256_text

    prompt = export_context_pack(project)["markdown"]
    prompt_text = Path(prompt).read_text(encoding="utf-8")
    if args.extra_instructions:
        prompt_text += "\n\n## Instrucciones adicionales del usuario\n\n" + args.extra_instructions

    logger = RunLogger(project.paths.runs_dir, new_run_id(), "agent")
    logger.event(
        "agent_run_requested",
        adapter=args.adapter,
        allow_execution_flag=args.allow_execution,
        config_allow=bool(dotted_get(project.config, "agent.allow_execution")),
        prompt_sha256_prefix=sha256_text(prompt_text)[:16],
    )
    try:
        result = run_adapter(
            project, args.adapter, prompt_text, allow_execution_flag=args.allow_execution
        )
    except DesignPipelineError as exc:
        logger.event("agent_run_blocked", reason=str(exc))
        logger.append_summary(project.paths.summary_md, [f"- Agente `{args.adapter}` bloqueado: {exc}"])
        raise
    logger.command(
        [str(item) for item in result.get("command", [])],
        result.get("exit_code"),
        float(result.get("duration_seconds") or 0.0),
        note=f"agente {result['adapter']} ({result['status']})",
    )
    logger.append_summary(
        project.paths.summary_md,
        [
            f"- Agente `{result['adapter']}` → `{result['status']}` "
            f"(exit {result.get('exit_code')})",
            f"  - prompt: {result.get('prompt_file')}",
            f"  - resultado: {result.get('result_file', '(sin archivo: timeout)')}",
        ],
    )
    if args.json:
        _print(result, True)
    else:
        print(f"Adaptador: {result['adapter']} → {result['status']} (exit {result.get('exit_code')})")
        if result.get("result_file"):
            print(f"Resultado: {result['result_file']}")
            print(f"Prompt:    {result['prompt_file']}")
        print("Salida capturada con redacción de secretos y registrada en runs/.")
    return EXIT_OK if result["status"] == "ok" else EXIT_ERROR


def cmd_status(args: argparse.Namespace) -> int:
    project, pipeline = _open_project(args)
    stale = pipeline.refresh_staleness()
    state = pipeline.state
    rows = []
    for stage_def in stages_mod.STAGES:
        stage_state = state.stage(stage_def.id)
        rows.append(
            {
                "stage": stage_def.id,
                "letter": stage_def.letter,
                "label": stage_def.label,
                "status": stage_state.status,
                "duration_seconds": stage_state.duration_seconds,
                "artifacts": stage_state.artifacts,
            }
        )
    payload = {
        "project": project.name,
        "path": str(project.paths.root),
        "source": state.source_path or project.source_path and str(project.source_path),
        "current_stage": state.current_stage(),
        "stages": rows,
        "decisions_pending": state.decisions_pending,
        "last_validation": state.last_validation,
        "recent_runs": [
            {
                "run_id": record.run_id,
                "stage": record.stage,
                "status": record.status,
                "started_at": record.started_at,
            }
            for record in state.runs[-5:]
        ],
        "just_marked_stale": [{"stage": stage, "reason": reason} for stage, reason in stale],
    }
    if args.json:
        _print(payload, True)
        return EXIT_OK
    print(f"Proyecto: {project.name}  ({project.paths.root})")
    print(f"Fuente:   {payload['source'] or 'sin importar'}")
    print(f"Etapa actual: {state.current_stage() or 'pipeline completo'}")
    print()
    print("Etapa  Estado       Duración    Artefactos")
    for row in rows:
        duration = (
            f"{row['duration_seconds']:.1f}s" if row["duration_seconds"] is not None else "-"
        )
        artifacts = ", ".join(row["artifacts"][:3])
        if len(row["artifacts"]) > 3:
            artifacts += f" (+{len(row['artifacts']) - 3})"
        print(f"{row['letter']:>2} {row['stage']:<10} {row['status']:<11} {duration:>9}   {artifacts}")
    if state.decisions_pending:
        print("\nDecisiones pendientes:")
        for item in state.decisions_pending:
            print(f"  - {item}")
    pending = pipeline.resumable()
    if pending:
        print(f"\nReanudar con: design-pipeline resume --project {project.name}")
        print(f"Etapas pendientes: {', '.join(pending)}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Construcción del parser
# ---------------------------------------------------------------------------

def _add_project_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", "-p", help="Nombre del proyecto en el workspace.")


def _add_workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        "-w",
        help="Directorio del workspace (default: ./workspace o config del usuario).",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="design-pipeline",
        description=(
            "Pipeline local para preparar contexto, registrar decisiones y generar "
            "componentes revisables a partir de exportaciones de diseño."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<comando>")

    p_init = sub.add_parser("init", help="Crea un proyecto nuevo en el workspace (etapa A).")
    p_init.add_argument("name", help="Nombre del proyecto (kebab-case).")
    _add_workspace_arg(p_init)
    p_init.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_init.set_defaults(func=cmd_init)

    p_doctor = sub.add_parser("doctor", help="Diagnostica dependencias y herramientas del entorno.")
    _add_workspace_arg(p_doctor)
    p_doctor.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_doctor.set_defaults(func=cmd_doctor)

    p_status = sub.add_parser("status", help="Muestra el estado del pipeline y la reanudación.")
    _add_project_args(p_status)
    _add_workspace_arg(p_status)
    p_status.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_status.set_defaults(func=cmd_status)

    p_import = sub.add_parser(
        "import", help="Inventarioa una exportación sin ejecutar ni modificar nada (etapa B)."
    )
    p_import.add_argument("source", help="Carpeta con la exportación de diseño.")
    _add_project_args(p_import)
    _add_workspace_arg(p_import)
    p_import.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_import.set_defaults(func=cmd_import)

    p_analyze = sub.add_parser(
        "analyze", help="Analiza el lote importado: componentes, tokens, accesibilidad (etapa C)."
    )
    _add_project_args(p_analyze)
    _add_workspace_arg(p_analyze)
    p_analyze.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_analyze.set_defaults(func=cmd_analyze)

    p_rules = sub.add_parser(
        "rules", help="Reglas de diseño y preguntas (etapa D). Sin acción, muestra el estado."
    )
    _add_project_args(p_rules)
    _add_workspace_arg(p_rules)
    p_rules.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_rules.set_defaults(func=cmd_rules_show)
    rules_sub = p_rules.add_subparsers(dest="rules_action", metavar="<acción>")

    p_rules_init = rules_sub.add_parser(
        "init", help="Crea reglas guiadas (--rules-file) o preguntas de descubrimiento."
    )
    p_rules_init.add_argument("--mode", choices=("discovery", "guided"), default="discovery")
    p_rules_init.add_argument("--rules-file", help="Archivo YAML/Markdown con reglas (modo guiado).")
    p_rules_init.add_argument(
        "--approve", action="store_true", help="Aprueba al importar las reglas guiadas."
    )
    _add_project_args(p_rules_init)
    _add_workspace_arg(p_rules_init)
    p_rules_init.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_rules_init.set_defaults(func=cmd_rules_init)

    p_rules_answer = rules_sub.add_parser("answer", help="Registra respuestas a preguntas.")
    p_rules_answer.add_argument("--id", help="Identificador de la pregunta (p. ej. q-001).")
    p_rules_answer.add_argument("--value", help="Valor de la respuesta (debe ser una opción válida).")
    p_rules_answer.add_argument(
        "--answers-file", help="YAML con mapping {id: valor} para responder en lote."
    )
    p_rules_answer.add_argument("--postpone", action="store_true", help="Pospone la pregunta.")
    _add_project_args(p_rules_answer)
    _add_workspace_arg(p_rules_answer)
    p_rules_answer.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_rules_answer.set_defaults(func=cmd_rules_answer)

    p_rules_approve = rules_sub.add_parser("approve", help="Aprueba o rechaza reglas propuestas.")
    p_rules_approve.add_argument("--id", action="append", help="Id de regla (repetible).")
    p_rules_approve.add_argument("--all", action="store_true", help="Todas las propuestas.")
    p_rules_approve.add_argument("--reject", action="store_true", help="Rechazar en vez de aprobar.")
    _add_project_args(p_rules_approve)
    _add_workspace_arg(p_rules_approve)
    p_rules_approve.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_rules_approve.set_defaults(func=cmd_rules_approve)

    p_rules_show = rules_sub.add_parser("show", help="Muestra preguntas y reglas con su estado.")
    _add_project_args(p_rules_show)
    _add_workspace_arg(p_rules_show)
    p_rules_show.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_rules_show.set_defaults(func=cmd_rules_show)

    p_spec = sub.add_parser(
        "spec", help="Genera la especificación intermedia por componente (etapa E)."
    )
    _add_project_args(p_spec)
    _add_workspace_arg(p_spec)
    p_spec.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_spec.set_defaults(func=cmd_spec)

    p_generate = sub.add_parser(
        "generate", help="Genera el código de salida por perfil de destino (etapa F)."
    )
    p_generate.add_argument(
        "--profile",
        choices=("react-css", "astro-css"),
        help="Perfil de destino (default: el del proyecto o react-css).",
    )
    _add_project_args(p_generate)
    _add_workspace_arg(p_generate)
    p_generate.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_generate.set_defaults(func=cmd_generate)

    p_validate = sub.add_parser(
        "validate", help="Valida la salida con evidencia: PASS/FAIL/SKIPPED/NEEDS_REVIEW (etapa G)."
    )
    p_validate.add_argument(
        "--profile", help="Perfil de salida a validar (default: el del proyecto)."
    )
    p_validate.add_argument(
        "--approve-external",
        action="store_true",
        help="Permite ejecutar comandos externos de build/lint si la config también lo autoriza.",
    )
    _add_project_args(p_validate)
    _add_workspace_arg(p_validate)
    p_validate.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_validate.set_defaults(func=cmd_validate)

    p_report = sub.add_parser(
        "report", help="Resumen de entrega y checklist de revisión humana (etapa H)."
    )
    p_report.add_argument("--profile", help="Perfil de salida (default: el del proyecto).")
    _add_project_args(p_report)
    _add_workspace_arg(p_report)
    p_report.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_report.set_defaults(func=cmd_report)

    p_skills = sub.add_parser(
        "skills",
        help="Skills y plugins: listar, inspeccionar, importar y habilitar (nunca ejecuta scripts).",
    )
    _add_project_args(p_skills)
    _add_workspace_arg(p_skills)
    p_skills.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills.set_defaults(func=cmd_skills_list)
    skills_sub = p_skills.add_subparsers(dest="skills_action", metavar="<acción>")

    p_skills_list = skills_sub.add_parser("list", help="Lista skills detectadas (interna/global/proyecto).")
    _add_project_args(p_skills_list)
    _add_workspace_arg(p_skills_list)
    p_skills_list.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills_list.set_defaults(func=cmd_skills_list)

    p_skills_inspect = skills_sub.add_parser(
        "inspect", help="Muestra metadatos, hashes, scripts declarados y preview."
    )
    p_skills_inspect.add_argument("name", help="Nombre de la skill.")
    _add_project_args(p_skills_inspect)
    _add_workspace_arg(p_skills_inspect)
    p_skills_inspect.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills_inspect.set_defaults(func=cmd_skills_inspect)

    p_skills_validate = skills_sub.add_parser(
        "validate", help="Valida una skill registrada o una carpeta local."
    )
    p_skills_validate.add_argument("target", help="Nombre registrado o ruta a una carpeta con SKILL.md.")
    _add_project_args(p_skills_validate)
    _add_workspace_arg(p_skills_validate)
    p_skills_validate.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills_validate.set_defaults(func=cmd_skills_validate)

    p_skills_add = skills_sub.add_parser(
        "add", help="Importa una skill desde una carpeta local (solo copia + hashes)."
    )
    p_skills_add.add_argument("path", help="Carpeta origen con SKILL.md.")
    _add_project_args(p_skills_add)
    _add_workspace_arg(p_skills_add)
    p_skills_add.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills_add.set_defaults(func=cmd_skills_add)

    p_skills_enable = skills_sub.add_parser("enable", help="Habilita una skill para el proyecto.")
    p_skills_enable.add_argument("name", help="Nombre de la skill.")
    _add_project_args(p_skills_enable)
    _add_workspace_arg(p_skills_enable)
    p_skills_enable.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills_enable.set_defaults(func=cmd_skills_enable, enable=True)

    p_skills_disable = skills_sub.add_parser("disable", help="Deshabilita una skill para el proyecto.")
    p_skills_disable.add_argument("name", help="Nombre de la skill.")
    _add_project_args(p_skills_disable)
    _add_workspace_arg(p_skills_disable)
    p_skills_disable.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills_disable.set_defaults(func=cmd_skills_enable, enable=False)

    p_skills_remove = skills_sub.add_parser(
        "remove", help="Elimina una skill externa (destructivo: requiere --yes)."
    )
    p_skills_remove.add_argument("name", help="Nombre de la skill.")
    p_skills_remove.add_argument("--yes", action="store_true", help="Confirmación de eliminación.")
    _add_project_args(p_skills_remove)
    _add_workspace_arg(p_skills_remove)
    p_skills_remove.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_skills_remove.set_defaults(func=cmd_skills_remove)

    p_resume = sub.add_parser(
        "resume",
        help="Reanuda el pipeline: ejecuta etapas pendientes/obsoletas/fallidas en orden.",
    )
    p_resume.add_argument(
        "--until",
        help="Etapa límite (inclusive), p. ej. spec. Default: todo lo pendiente.",
    )
    p_resume.add_argument(
        "--source",
        help="Ruta de la exportación si la etapa import debe reejecutarse sin registro previo.",
    )
    p_resume.add_argument("--profile", help="Perfil para generate/validate/report.")
    p_resume.add_argument(
        "--approve-external",
        action="store_true",
        help="Permite comandos externos en validate si la config también lo autoriza.",
    )
    _add_project_args(p_resume)
    _add_workspace_arg(p_resume)
    p_resume.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_resume.set_defaults(func=cmd_resume)

    p_tui = sub.add_parser(
        "tui",
        help="Asistente interactivo en terminal (selección de proyecto, preguntas, aprobaciones).",
    )
    _add_workspace_arg(p_tui)
    p_tui.set_defaults(func=cmd_tui)

    p_context = sub.add_parser(
        "context",
        help="Exporta el paquete de contexto (context/agent-package/) para cargar en un agente.",
    )
    _add_project_args(p_context)
    _add_workspace_arg(p_context)
    p_context.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_context.set_defaults(func=cmd_context)

    p_agent = sub.add_parser(
        "agent",
        help="Adaptadores de agentes: listar los declarados o ejecutar uno con doble permiso.",
    )
    _add_project_args(p_agent)
    _add_workspace_arg(p_agent)
    p_agent.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_agent.set_defaults(func=cmd_agent_list)
    agent_sub = p_agent.add_subparsers(dest="agent_action", metavar="<acción>")

    p_agent_list = agent_sub.add_parser("list", help="Lista adaptadores declarados y su detección.")
    _add_project_args(p_agent_list)
    _add_workspace_arg(p_agent_list)
    p_agent_list.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_agent_list.set_defaults(func=cmd_agent_list)

    p_agent_run = agent_sub.add_parser(
        "run", help="Ejecuta un adaptador (requiere agent.allow_execution + --allow-execution)."
    )
    p_agent_run.add_argument("adapter", help="Id del adaptador declarado en agent.adapters.")
    p_agent_run.add_argument(
        "--extra-instructions",
        help="Texto adicional que se adjunta al paquete de contexto como prompt.",
    )
    p_agent_run.add_argument(
        "--allow-execution",
        action="store_true",
        help="Permiso explícito para ejecutar la CLI externa (junto con la config).",
    )
    _add_project_args(p_agent_run)
    _add_workspace_arg(p_agent_run)
    p_agent_run.add_argument("--json", action="store_true", help="Salida machine-readable.")
    p_agent_run.set_defaults(func=cmd_agent_run)

    return parser


_DISPATCH: dict[str, Callable[[argparse.Namespace], int]] = {}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args)
    except DesignPipelineError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover
        print("\nInterrumpido por el usuario.", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
