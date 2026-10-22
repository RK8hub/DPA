from __future__ import annotations

from pathlib import Path

from design_pipeline.tui import app, console

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fixture-export"


def _canned(responses: list[str]):
    iterator = iter(responses)

    def _input(_prompt: str) -> str:
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return _input


def test_tui_rechaza_terminal_no_interactiva(tmp_path: Path, capsys):
    code = app.run_tui(str(tmp_path))
    assert code == 1
    out = capsys.readouterr().out
    assert "terminal interactiva" in out
    assert "design-pipeline --help" in out


def test_tui_sesion_estado_y_salida(tmp_path: Path, monkeypatch, capsys):
    from tests.helpers import prepared_project

    project = prepared_project(tmp_path, FIXTURE)
    monkeypatch.setattr(console, "is_interactive", lambda: True)
    console.set_input(_canned([
        "1",   # proyectos: Proyecto demo (opción 1; 0=volver)
        "1",   # menú proyecto: ver estado
        "",    # pausa (Enter)
        "0",   # menú proyecto: volver
        "0",   # proyectos: salir
    ]))
    try:
        code = app.run_tui(str(Path(project.paths.root).parent))
    finally:
        console.set_input(input)
    assert code == 0
    out = capsys.readouterr().out
    assert "Proyecto demo" in out
    assert "etapa" in out and "estado" in out
    assert "Decisiones pendientes" in out or "Pendientes" in out


def test_tui_cambia_perfil_de_destino(tmp_path: Path, monkeypatch, capsys):
    from tests.helpers import prepared_project

    project = prepared_project(tmp_path, FIXTURE)
    assert project.data["generation"]["profile"] == "react-css"
    monkeypatch.setattr(console, "is_interactive", lambda: True)
    console.set_input(_canned([
        "1",   # proyectos: demo
        "6",   # elegir perfil de destino
        "2",   # astro-css
        "",    # pausa
        "0",   # volver
        "0",   # salir
    ]))
    try:
        code = app.run_tui(str(Path(project.paths.root).parent))
    finally:
        console.set_input(input)
    assert code == 0
    reloaded = project.load_state()  # estado legible tras la interacción
    assert reloaded is not None
    import yaml

    data = yaml.safe_load((project.paths.project_yaml).read_text(encoding="utf-8"))
    assert data["generation"]["profile"] == "astro-css"


def test_tui_flujo_completo_con_aprobaciones(tmp_path: Path, monkeypatch, capsys):
    """La TUI ejecuta generate→validate→report tras pedir las aprobaciones."""
    from tests.helpers import prepared_project

    project = prepared_project(tmp_path, FIXTURE)
    monkeypatch.setattr(console, "is_interactive", lambda: True)
    console.set_input(_canned([
        "1",   # proyectos: demo
        "7",   # ejecutar pipeline hasta la entrega
        "s",   # hay preguntas abiertas: continuar igual
        "s",   # aprobar la generación de código
        "n",   # NO permitir comandos externos en validate
        "s",   # continuar con validate/report tras generate
        "",    # pausa final
        "0",   # menú proyecto: volver
        "0",   # proyectos: salir
    ]))
    try:
        code = app.run_tui(str(Path(project.paths.root).parent))
    finally:
        console.set_input(input)
    assert code == 0

    out_dir = project.paths.output_profile_dir("react-css")
    assert (out_dir / "components" / "Button" / "Button.tsx").exists()
    assert (project.paths.reports_dir / "DELIVERY.md").exists()
    assert (project.paths.reports_dir / "VALIDATION.md").exists()

    # La TUI usa instancias propias del proyecto: releemos el estado de disco.
    from design_pipeline.engine.state import ProjectState

    state = ProjectState.load(project.paths.state_yaml)
    assert state.is_done("generate")
    assert state.is_done("validate")
    assert state.is_done("report")
    out = capsys.readouterr().out
    assert "Ruta de salida" in out


def test_tui_responde_pregunta_y_deriva_regla(tmp_path: Path, monkeypatch, capsys):
    from design_pipeline.analysis.stage import load_analysis
    from design_pipeline.rules.manager import load_questions, seed_discovery
    from tests.helpers import prepared_project

    project = prepared_project(tmp_path, FIXTURE)
    seed_discovery(project, load_analysis(project))
    monkeypatch.setattr(console, "is_interactive", lambda: True)
    console.set_input(_canned([
        "1",   # proyectos: demo
        "3",   # responder preguntas
        "1",   # q-001 → primera opción (react-css)
        "0",   # q-002: cancelar la ronda (el finally deriva las respuestas)
        "0",   # menú proyecto: volver
        "0",   # salir
    ]))
    try:
        code = app.run_tui(str(Path(project.paths.root).parent))
    finally:
        console.set_input(input)
    assert code == 0
    questions = {question.id: question for question in load_questions(project)}
    assert questions["q-001"].status == "answered"
    assert questions["q-001"].answer == "react-css"
    out = capsys.readouterr().out
    assert "respuestas registradas" in out
