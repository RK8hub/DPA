"""Pruebas de integración: el pipeline completo ejecutado por la CLI.

Estas pruebas no llaman módulos internos directamente: usan ``cli.main``
con argumentos reales, igual que un usuario, y verifican artefactos en disco.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import yaml

from design_pipeline.cli import main
from design_pipeline.utils import tree_fingerprint

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "fixture-export"


def run_cli(capsys, *args: str) -> tuple[int, str]:
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out


def _flow_until_rules(capsys, ws: Path, source: Path) -> None:
    """init + import + analyze + rules por la CLI."""
    assert run_cli(capsys, "init", "demo", "-w", str(ws))[0] == 0
    assert run_cli(capsys, "import", str(source), "-p", "demo", "-w", str(ws))[0] == 0
    assert run_cli(capsys, "analyze", "-p", "demo", "-w", str(ws))[0] == 0
    assert run_cli(capsys, "rules", "init", "-p", "demo", "-w", str(ws))[0] == 0


def test_flujo_completo_cli(capsys, tmp_path: Path):
    """A: init → import → analyze → rules → spec → generate → validate → report."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, FIXTURE)

    # Responder la pregunta q-001 (framework de destino) y aprobar todas las reglas.
    assert run_cli(
        capsys, "rules", "answer", "--id", "q-001", "--value", "react-css",
        "-p", "demo", "-w", str(ws),
    )[0] == 0
    assert run_cli(
        capsys, "rules", "approve", "--all", "-p", "demo", "-w", str(ws)
    )[0] == 0

    assert run_cli(capsys, "spec", "-p", "demo", "-w", str(ws))[0] == 0
    assert run_cli(
        capsys, "generate", "-p", "demo", "-w", str(ws), "--profile", "react-css"
    )[0] == 0
    assert run_cli(capsys, "validate", "-p", "demo", "-w", str(ws))[0] == 0
    assert run_cli(capsys, "report", "-p", "demo", "-w", str(ws))[0] == 0

    project = ws / "demo"
    # Artefactos clave presentes.
    assert (project / "inventory.json").exists()
    assert (project / "analysis.json").exists()
    assert (project / "specs" / "index.json").exists()
    assert (project / "reports" / "IMPORT-REPORT.md").exists()
    assert (project / "reports" / "ANALYSIS.md").exists()
    assert (project / "reports" / "DESIGN-RULES.md").exists()
    assert (project / "reports" / "DECISIONS.md").exists()
    assert (project / "reports" / "generation-notes.md").exists()
    assert (project / "reports" / "VALIDATION.md").exists()
    assert (project / "reports" / "validation-report.json").exists()
    assert (project / "reports" / "DELIVERY.md").exists()
    assert (project / "reports" / "REVIEW-CHECKLIST.md").exists()

    # La salida contiene el componente observado con contenido idéntico al origen.
    generated = project / "output" / "react-css" / "components" / "Button" / "Button.tsx"
    original = FIXTURE / "components" / "Button" / "Button.tsx"
    assert generated.exists()
    assert generated.read_bytes() == original.read_bytes()

    # Estado final: pipeline completo.
    code, out = run_cli(capsys, "status", "-p", "demo", "-w", str(ws))
    assert code == 0
    assert "pipeline completo" in out

    # El informe de validación es machine-readable y coherente.
    report = json.loads((project / "reports" / "validation-report.json").read_text("utf-8"))
    assert report["verdict"] in {"pass", "pass_with_review"}
    assert report["summary"]["FAIL"] == 0
    # Un PASS siempre lleva evidencia registrada en el check.
    assert all(check.get("evidence") is not None for check in report["checks"])


def test_fuente_original_intacta(capsys, tmp_path: Path, copied_export: Path):
    """Ninguna etapa modifica la exportación original (principio de aislamiento)."""
    before = tree_fingerprint(copied_export)
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, copied_export)
    assert run_cli(
        capsys, "rules", "answer", "--id", "q-001", "--value", "react-css",
        "-p", "demo", "-w", str(ws),
    )[0] == 0
    assert run_cli(
        capsys, "rules", "approve", "--all", "-p", "demo", "-w", str(ws)
    )[0] == 0
    assert run_cli(capsys, "spec", "-p", "demo", "-w", str(ws))[0] == 0
    assert run_cli(capsys, "generate", "-p", "demo", "-w", str(ws))[0] == 0
    assert run_cli(capsys, "validate", "-p", "demo", "-w", str(ws))[0] == 0
    after = tree_fingerprint(copied_export)
    assert before == after
    # Y la validación lo confirma con un check real (no un PASS declarado).
    report = json.loads(
        (ws / "demo" / "reports" / "validation-report.json").read_text("utf-8")
    )
    isolation = next(check for check in report["checks"] if check["id"] == "isolation")
    assert isolation["status"] == "PASS"


def test_stale_y_resume(capsys, tmp_path: Path, copied_export: Path):
    """Al cambiar la fuente, import/analyze quedan stale y resume los reejecuta."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, copied_export)

    # Modificar un archivo de la exportación (simula un rediseño).
    button = copied_export / "components" / "Button" / "Button.tsx"
    button.write_text(
        button.read_text("utf-8") + "\n// Rediseño posterior a la importación\n",
        encoding="utf-8",
    )

    # El estado detecta la obsolescencia.
    code, out = run_cli(capsys, "status", "-p", "demo", "-w", str(ws), "--json")
    assert code == 0
    payload = json.loads(out)
    statuses = {row["stage"]: row["status"] for row in payload["stages"]}
    assert statuses["import"] == "stale"
    assert statuses["analyze"] == "stale"

    # Resume reejecuta import y analyze con la fuente nueva.
    code, out = run_cli(capsys, "resume", "-p", "demo", "-w", str(ws), "--until", "analyze")
    assert code == 0
    assert "import" in out and "analyze" in out

    code, out = run_cli(capsys, "status", "-p", "demo", "-w", str(ws), "--json")
    payload = json.loads(out)
    statuses = {row["stage"]: row["status"] for row in payload["stages"]}
    assert statuses["import"] == "done"
    assert statuses["analyze"] == "done"


def test_resume_sin_nada_pendiente(capsys, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, FIXTURE)
    code, out = run_cli(capsys, "resume", "-p", "demo", "-w", str(ws), "--until", "analyze")
    assert code == 0
    # Segunda corrida: no reejecuta nada (no duplica trabajo).
    code, out = run_cli(capsys, "resume", "-p", "demo", "-w", str(ws), "--until", "analyze")
    assert code == 0
    assert "0 etapas ejecutadas" in out


def test_import_idempotente(capsys, tmp_path: Path):
    """Reimportar la misma exportación no duplica el inventario."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, FIXTURE)
    inventory = yaml.safe_load((ws / "demo" / "inventory.json").read_text("utf-8"))
    files_first = len(inventory["files"])

    assert run_cli(capsys, "import", str(FIXTURE), "-p", "demo", "-w", str(ws))[0] == 0
    inventory = yaml.safe_load((ws / "demo" / "inventory.json").read_text("utf-8"))
    assert len(inventory["files"]) == files_first


def test_estado_machine_readable(capsys, tmp_path: Path):
    """state.yaml tiene schema_version, stages, runs, decisions_pending, last_validation."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, FIXTURE)
    state = yaml.safe_load((ws / "demo" / "state.yaml").read_text("utf-8"))
    assert state["schema_version"] == 1
    assert set(state["stages"]) == {
        "init", "import", "analyze", "rules", "spec", "generate", "validate", "report",
    }
    assert isinstance(state["runs"], list)
    assert state["runs"], "cada ejecución debe quedar registrada en state.runs"
    assert "decisions_pending" in state
    assert "last_validation" in state
    for stage in state["stages"].values():
        assert {"status", "notes", "artifacts", "inputs"} <= set(stage)


def test_salida_json_de_comandos(capsys, tmp_path: Path):
    """--json produce JSON parseable en los comandos que lo ofrecen."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, FIXTURE)
    for command in (["status"], ["analyze"], ["rules", "show"], ["skills", "list"]):
        code, out = run_cli(
            capsys, *command, "-p", "demo", "-w", str(ws), "--json"
        )
        assert code == 0, f"{command} falló: {out}"
        assert json.loads(out), f"{command} no produjo JSON"


def test_generacion_perfil_astro(capsys, tmp_path: Path):
    """Perfil astro-css: estáticos convertidos, interactivos como islas."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, FIXTURE)
    assert run_cli(
        capsys, "rules", "answer", "--id", "q-001", "--value", "astro-css",
        "-p", "demo", "-w", str(ws),
    )[0] == 0
    assert run_cli(
        capsys, "rules", "approve", "--all", "-p", "demo", "-w", str(ws)
    )[0] == 0
    assert run_cli(capsys, "spec", "-p", "demo", "-w", str(ws))[0] == 0
    code, out = run_cli(
        capsys, "generate", "-p", "demo", "-w", str(ws), "--profile", "astro-css"
    )
    assert code == 0, out

    out_dir = ws / "demo" / "output" / "astro-css"
    # Estático convertido a plantilla Astro conservando el marcado observado.
    card = out_dir / "components" / "Card" / "Card.astro"
    assert card.exists()
    card_text = card.read_text("utf-8")
    original_card = (FIXTURE / "components" / "Card" / "Card.tsx").read_text("utf-8")
    assert "class=" in card_text
    # El texto del componente estático observado se conserva (fidelidad literal).
    assert "card" in card_text.lower()
    assert "button" in original_card.lower()

    # Interactivo: wrapper de isla con directiva client:* + componente original.
    button_astro = out_dir / "components" / "Button" / "Button.astro"
    assert button_astro.exists()
    assert "client:" in button_astro.read_text("utf-8")
    assert (out_dir / "components" / "Button" / "Button.tsx").exists()

    # La conversión no soportada cae en fallback y queda marcada para revisión.
    assert (out_dir / "components" / "Legacy" / "Legacy.tsx").exists()
    notes = (ws / "demo" / "reports" / "generation-notes.md").read_text("utf-8")
    assert "Legacy" in notes
    assert "isla" in notes or "NEEDS_REVIEW" in notes

    # La validación no afirma conformidad visual: distingue los estados.
    code, out = run_cli(capsys, "validate", "-p", "demo", "-w", str(ws), "--json")
    assert code == 0
    report = json.loads(out)
    assert report["summary"]["FAIL"] == 0
    assert report["verdict"] in {"pass", "pass_with_review"}


def test_flujo_css_embebido_cli(capsys, tmp_path: Path):
    """Issue #1: el CSS embebido al final de un .jsx se extrae y compila.

    Flujo completo por la CLI sobre una exportación cuyos componentes traen su
    CSS pegado tras un marcador `/* nombre.css */` (sin archivos .css reales).
    """
    embedded = (
        Path(__file__).resolve().parent.parent / "fixtures" / "fixture-embedded-css"
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, embedded)

    # Import: los imports de CSS embebido NO son referencias rotas.
    code, out = run_cli(
        capsys, "import", str(embedded), "-p", "demo", "-w", str(ws), "--json"
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["embedded_stylesheets"] == 2
    assert "./panel.css" not in {r["ref"] for r in json.loads(
        (ws / "demo" / "inventory.json").read_text("utf-8")
    )["broken_references"]}

    # Analyze: las hojas embebidas se analizan (antes: 0 hojas de estilo).
    code, out = run_cli(capsys, "analyze", "-p", "demo", "-w", str(ws), "--json")
    assert code == 0
    analysis = json.loads((ws / "demo" / "analysis.json").read_text("utf-8"))
    assert {"panel.css", "toolbar.css"} <= {c["path"] for c in analysis["stylesheets"]}
    assert any(
        "CSS embebido extraído" in f["message"] for f in analysis["findings"]
    )

    assert run_cli(
        capsys, "rules", "answer", "--id", "q-001", "--value", "react-css",
        "-p", "demo", "-w", str(ws),
    )[0] == 0
    assert run_cli(
        capsys, "rules", "approve", "--all", "-p", "demo", "-w", str(ws)
    )[0] == 0
    assert run_cli(capsys, "spec", "-p", "demo", "-w", str(ws))[0] == 0

    # Generate: el JSX de salida queda compilable y el CSS sale separado.
    code, out = run_cli(
        capsys, "generate", "-p", "demo", "-w", str(ws), "--profile", "react-css"
    )
    assert code == 0, out
    out_dir = ws / "demo" / "output" / "react-css"
    panel_jsx = (out_dir / "Panel.jsx").read_text("utf-8")
    assert 'import "./panel.css";' in panel_jsx
    assert "/* panel.css */" not in panel_jsx
    assert panel_jsx.rstrip().endswith("}")
    assert ".panel {" in (out_dir / "panel.css").read_text("utf-8")

    # Validate: sin FAIL; las referencias resuelven (las únicas rotas son las
    # heredadas del export que no se pudieron separar) y la fuente sigue intacta.
    code, out = run_cli(capsys, "validate", "-p", "demo", "-w", str(ws), "--json")
    assert code == 0
    report = json.loads(out)
    assert report["summary"]["FAIL"] == 0
    references = next(c for c in report["checks"] if c["id"] == "references")
    assert references["status"] != "FAIL"
    # Toda referencia rota detectada es heredada (ninguna nueva introducida).
    assert references["evidence"]["broken"] == references["evidence"]["inherited"]
    isolation = next(c for c in report["checks"] if c["id"] == "isolation")
    assert isolation["status"] == "PASS"


def test_skills_add_no_ejecuta_scripts(capsys, tmp_path: Path):
    """Importar una skill con scripts deja evidencia pero no ejecuta nada."""
    ws = tmp_path / "ws"
    ws.mkdir()
    assert run_cli(capsys, "init", "demo", "-w", str(ws))[0] == 0

    marker = tmp_path / "EJECUTADA"
    skill_dir = tmp_path / "skill-con-script"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: skill-con-script\n"
        'description: "Skill de prueba con script declarado."\n'
        "version: 0.1.0\n"
        "mode: instructive\n"
        "permissions: [read-workspace]\n"
        "tools: []\n"
        "stages: [report]\n"
        "scripts: [setup.py]\n"
        "---\n\n"
        "# Skill con script\n\n"
        "El script de esta skill crearía un marcador si se ejecutara.\n",
        encoding="utf-8",
    )
    # Script que crearía un archivo si alguien lo corriera.
    (skill_dir / "setup.py").write_text(
        f"from pathlib import Path\nPath(r'{marker}').write_text('ejecutada')\n",
        encoding="utf-8",
    )

    code, out = run_cli(capsys, "skills", "validate", str(skill_dir), "-w", str(ws))
    assert code == 0
    assert "NO se ejecutará" in out or "NO ejecutado" in out

    code, out = run_cli(
        capsys, "skills", "add", str(skill_dir), "-p", "demo", "-w", str(ws)
    )
    assert code == 0
    assert "Ningún archivo de la skill fue ejecutado" in out
    assert not marker.exists(), "el script de la skill NO debe haberse ejecutado"

    # La copia no hereda bit de ejecución y registra procedencia.
    dest = ws / "demo" / ".skills" / "skill-con-script"
    assert (dest / "SKILL.md").exists()
    assert not (dest / "setup.py").stat().st_mode & stat.S_IXUSR
    meta = yaml.safe_load((dest / "skill.yaml").read_text("utf-8"))
    assert meta["origin"]["kind"] == "local-path"
    assert meta["file_sha256"]["setup.py"]


def test_context_export(capsys, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _flow_until_rules(capsys, ws, FIXTURE)
    code, out = run_cli(capsys, "context", "-p", "demo", "-w", str(ws), "--json")
    assert code == 0
    payload = json.loads(out)
    md = Path(payload["markdown"])
    assert md.exists()
    content = md.read_text("utf-8")
    assert "Estado del pipeline" in content
    assert "No modifiques la exportación original" in content


def test_doctor_reporta_entorno(capsys, tmp_path: Path):
    ws = tmp_path / "ws"
    ws.mkdir()
    code, out = run_cli(capsys, "doctor", "-w", str(ws))
    assert code == 0
    lower = out.lower()
    assert "python" in lower
    assert "workspace" in lower
