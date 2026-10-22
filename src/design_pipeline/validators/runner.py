"""Etapa G: validadores deterministas con resultados trazables.

Cada verificación produce un :class:`CheckResult` con estado `PASS`, `FAIL`,
`SKIPPED` o `NEEDS_REVIEW`, detalle, evidencia (comando/código de salida
cuando corresponde) y limitaciones. Ninguna comprobación se marca PASS sin
haberse ejecutado y registrado.

Validaciones externas (build/lint de npm, pruebas de navegador, comparación
visual) se marcan SKIPPED con el motivo cuando no hay herramienta disponible
o falta aprobación explícita.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from design_pipeline.analysis.analyzer import _A11Y_CLICKABLE, _A11Y_IMG_NO_ALT
from design_pipeline.errors import DesignPipelineError
from design_pipeline.generators.stage import load_specs
from design_pipeline.utils import dotted_get, iso_now, iter_files, tree_fingerprint
from design_pipeline.validators.schema import package_schemas_dir, validate_instance
from design_pipeline.workspace.project import Project

PASS = "PASS"
FAIL = "FAIL"
SKIPPED = "SKIPPED"
NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class CheckResult:
    id: str
    name: str
    status: str
    detail: str
    evidence: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    created_at: str
    profile: str
    checks: list[CheckResult] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    verdict: str = "unknown"

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)

    def finalize(self) -> None:
        self.summary = {
            status: sum(1 for check in self.checks if check.status == status)
            for status in (PASS, FAIL, SKIPPED, NEEDS_REVIEW)
        }
        if self.summary[FAIL]:
            self.verdict = "fail"
        elif self.summary[NEEDS_REVIEW]:
            self.verdict = "pass_with_review"
        else:
            self.verdict = "pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "profile": self.profile,
            "verdict": self.verdict,
            "summary": self.summary,
            "checks": [asdict(check) for check in self.checks],
        }


# ---------------------------------------------------------------------------
# Validadores
# ---------------------------------------------------------------------------

def check_files_integrity(project: Project, output_dir: Path) -> CheckResult:
    """Todos los archivos generados existen y no están vacíos; sin fugas de ruta."""
    missing: list[str] = []
    empty: list[str] = []
    total = 0
    for path in iter_files(output_dir):
        total += 1
        try:
            path.relative_to(output_dir)
        except ValueError:  # pragma: no cover - iter_files no puede salirse
            missing.append(f"{path} (fuera del árbol de salida)")
            continue
        if path.stat().st_size == 0:
            empty.append(path.relative_to(output_dir).as_posix())
    if not total:
        return CheckResult(
            id="integrity",
            name="Integridad de archivos de salida",
            status=FAIL,
            detail="La carpeta de salida está vacía.",
        )
    status = PASS if not missing and not empty else FAIL
    detail = (
        f"{total} archivos verificados; estructura completa."
        if status == PASS
        else f"Faltan: {missing or 'ninguno'}. Vacíos: {empty or 'ninguno'}."
    )
    return CheckResult(
        id="integrity",
        name="Integridad de archivos de salida",
        status=status,
        detail=detail,
        evidence={"files": total},
    )


def check_source_isolation(project: Project) -> CheckResult:
    """La exportación original no fue modificada (compara huella del inventario)."""
    import json as _json

    inventory_path = project.paths.inventory_json
    if not inventory_path.exists():
        return CheckResult(
            id="isolation",
            name="Aislamiento de la fuente",
            status=SKIPPED,
            detail="No hay inventario con qué comparar.",
        )
    data = _json.loads(inventory_path.read_text(encoding="utf-8"))
    recorded = data["source_fingerprint"]
    source = Path(data["source_path"])
    if not source.is_dir():
        return CheckResult(
            id="isolation",
            name="Aislamiento de la fuente",
            status=NEEDS_REVIEW,
            detail=f"La fuente importada ya no existe en disco: {source}",
        )
    current = tree_fingerprint(source, data.get("exclusions", []))
    if current == recorded:
        return CheckResult(
            id="isolation",
            name="Aislamiento de la fuente",
            status=PASS,
            detail="La huella de la exportación original coincide con la del momento de importar.",
            evidence={"fingerprint": current[:16] + "…"},
        )
    return CheckResult(
        id="isolation",
        name="Aislamiento de la fuente",
        status=FAIL,
        detail="La exportación original cambió después de importarse.",
        evidence={"recorded": recorded[:16] + "…", "current": current[:16] + "…"},
    )


def check_specs_schema(project: Project) -> CheckResult:
    specs_dir = project.paths.specs_dir / "components"
    schema = json.loads(
        (package_schemas_dir() / "component-spec.schema.json").read_text(encoding="utf-8")
    )
    errors: list[str] = []
    count = 0
    for path in sorted(specs_dir.glob("*.json")):
        count += 1
        instance = json.loads(path.read_text(encoding="utf-8"))
        errors.extend(validate_instance(instance, schema, path=f"$.{path.stem}"))
    if count == 0:
        return CheckResult(
            id="spec-schema",
            name="Esquema de especificaciones",
            status=FAIL,
            detail="No hay especificaciones que validar.",
        )
    return CheckResult(
        id="spec-schema",
        name="Esquema de especificaciones",
        status=PASS if not errors else FAIL,
        detail=f"{count} especificaciones validadas."
        if not errors
        else "; ".join(errors[:5]),
        evidence={"specs": count, "errors": len(errors)},
    )


def check_manifests(project: Project) -> CheckResult:
    """Validez de JSON/YAML de los manifiestos del workspace."""
    problems: list[str] = []
    checked = 0
    for path in (
        project.paths.inventory_json,
        project.paths.analysis_json,
        project.paths.specs_dir / "index.json",
        project.paths.design_rules_yaml,
        project.paths.questions_yaml,
        project.paths.state_yaml,
        project.paths.project_yaml,
    ):
        if not path.exists():
            continue
        checked += 1
        try:
            if path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            else:
                yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"{path.name}: {exc}")
    return CheckResult(
        id="manifests",
        name="Validez de manifiestos (JSON/YAML)",
        status=PASS if not problems else FAIL,
        detail=f"{checked} manifiestos verificados."
        if not problems
        else "; ".join(problems),
        evidence={"checked": checked},
    )


_IMPORT_REF_RE = re.compile(
    r"""(?:import|export)\s+[^'";]*?from\s+['"](\.[^'"]+)['"]|import\s+['"](\.[^'"]+)['"]|url\(\s*['"]?(\.[^'")]+)['"]?\s*\)"""
)


def check_references(project: Project, output_dir: Path, specs: list[dict[str, Any]]) -> CheckResult:
    """Imports y url() relativos del output resuelven dentro del árbol."""
    known = {
        path.relative_to(output_dir).as_posix()
        for path in iter_files(output_dir)
    }
    known_noext = {path.rsplit(".", 1)[0] for path in known}

    # Limitaciones heredadas de la spec: no se cuentan como FAIL nuevas.
    known_broken: set[str] = set()
    for spec in specs:
        for limitation in spec.get("limitations", []):
            match = re.search(r"`([^`]+)`", limitation)
            if match:
                known_broken.add(match.group(1))

    broken: list[str] = []
    checked = 0
    extensions = (".tsx", ".ts", ".jsx", ".js", ".astro", ".css")
    for path in iter_files(output_dir):
        if path.suffix not in extensions:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _IMPORT_REF_RE.finditer(text):
            ref = next(group for group in match.groups() if group)
            checked += 1
            base = Path(path.relative_to(output_dir).as_posix()).parent
            parts = list(base.parts)
            traversal_ok = True
            for part in Path(ref).parts:
                if part == "..":
                    if parts:
                        parts.pop()
                    else:
                        traversal_ok = False
                elif part != ".":
                    parts.append(part)
            resolved = "/".join(parts)
            if not traversal_ok:
                broken.append(f"{path.name}: {ref} (sale del árbol)")
                continue
            if resolved in known or resolved in known_noext:
                continue
            if any(f"{resolved}{ext}" in known for ext in (".ts", ".tsx", ".astro", ".css", ".svg", ".png")):
                continue
            broken.append(f"{path.relative_to(output_dir).as_posix()}: {ref}")

    new_broken = [item for item in broken if not any(k in item for k in known_broken)]
    inherited = len(broken) - len(new_broken)
    if new_broken:
        status = FAIL
        detail = "Imports/refs rotos nuevos: " + "; ".join(new_broken[:6])
    elif inherited:
        status = NEEDS_REVIEW
        detail = f"Sin imports rotos nuevos; {inherited} heredados de la exportación (ya documentados)."
    else:
        status = PASS
        detail = f"{checked} referencias relativas verificadas."
    return CheckResult(
        id="references",
        name="Imports y recursos referenciados",
        status=status,
        detail=detail,
        evidence={"checked": checked, "broken": len(broken), "inherited": inherited},
    )


_CLASS_ATTR_RE = re.compile(r"""class(?:Name)?=["'`]([^"'`]*)["'`]""")


def check_class_coverage(output_dir: Path) -> CheckResult:
    """Clases usadas en el markup vs clases definidas en el CSS copiado."""
    defined: set[str] = set()
    for path in iter_files(output_dir):
        if path.suffix == ".css":
            text = path.read_text(encoding="utf-8", errors="replace")
            defined.update(re.findall(r"\.([\w-]+)", text))
    used: set[str] = set()
    for path in iter_files(output_dir):
        if path.suffix in {".tsx", ".jsx", ".astro", ".html"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in _CLASS_ATTR_RE.finditer(text):
                used.update(token for token in match.group(1).split() if "${" not in token)
    missing = sorted(used - defined)
    if missing:
        return CheckResult(
            id="class-coverage",
            name="Cobertura de clases (markup vs CSS)",
            status=NEEDS_REVIEW,
            detail=(
                f"{len(missing)} clases usadas sin definir en el CSS copiado "
                "(pueden venir de estilos globales del proyecto destino): "
                + ", ".join(f".{name}" for name in missing[:10])
            ),
            evidence={"missing": missing},
        )
    return CheckResult(
        id="class-coverage",
        name="Cobertura de clases (markup vs CSS)",
        status=PASS,
        detail=f"{len(used)} clases usadas encuentran definición en el CSS copiado.",
    )


def check_accessibility(output_dir: Path) -> CheckResult:
    findings: list[str] = []
    for path in iter_files(output_dir):
        if path.suffix not in {".tsx", ".jsx", ".astro"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(output_dir).as_posix()
        for match in _A11Y_IMG_NO_ALT.finditer(text):
            findings.append(f"{rel}: <img> sin alt")
        for match in _A11Y_CLICKABLE.finditer(text):
            findings.append(f"{rel}: <{match.group(1)}> con onClick sin teclado")
    if findings:
        return CheckResult(
            id="accessibility",
            name="Accesibilidad automatizable",
            status=NEEDS_REVIEW,
            detail=f"{len(findings)} hallazgos: " + "; ".join(findings[:6]),
            evidence={"findings": findings},
            limitations=["Heurísticas limitadas: no cubren contraste, foco ni orden de tabulación."],
        )
    return CheckResult(
        id="accessibility",
        name="Accesibilidad automatizable",
        status=PASS,
        detail="Sin hallazgos de las heurísticas aplicadas.",
        limitations=["Heurísticas limitadas: no cubren contraste, foco ni orden de tabulación."],
    )


def check_framework_integration(project: Project, profile_id: str, specs: list[dict[str, Any]]) -> CheckResult:
    """Para astro-css: las islas React requieren @astrojs/react (no instalado)."""
    if profile_id != "astro-css":
        return CheckResult(
            id="framework-integration",
            name="Integración de framework destino",
            status=SKIPPED,
            detail="El perfil no requiere integración de framework adicional.",
        )
    output_dir = project.paths.output_profile_dir(profile_id)
    islands = [
        path.relative_to(output_dir).as_posix()
        for path in iter_files(output_dir)
        if path.suffix == ".tsx" and "components" in path.parts
    ]
    if not islands:
        return CheckResult(
            id="framework-integration",
            name="Integración de framework destino",
            status=PASS,
            detail="Sin islas: no se requiere integración de framework.",
        )
    return CheckResult(
        id="framework-integration",
        name="Integración de framework destino",
        status=NEEDS_REVIEW,
        detail=(
            f"{len(islands)} islas React en la salida. El proyecto Astro destino necesita "
            "la integración `@astrojs/react` (NO se instaló automáticamente)."
        ),
        evidence={"islands": islands},
    )


def check_external_build(
    project: Project, profile_id: str, approve_external: bool
) -> CheckResult:
    """Build/lint externo: solo con salida npm-like y aprobación explícita."""
    output_dir = project.paths.output_profile_dir(profile_id)
    package_json = output_dir / "package.json"
    if not package_json.exists():
        return CheckResult(
            id="external-build",
            name="Build/lint del proyecto destino",
            status=SKIPPED,
            detail=(
                "El output no incluye un proyecto npm (los perfiles generan archivos sueltos "
                "para copiar a un proyecto existente). Copialo al proyecto destino y ejecutá "
                "su build/lint ahí."
            ),
        )
    config_ok = bool(dotted_get(project.config, "validation.approve_external_commands"))
    if not (approve_external and config_ok):
        return CheckResult(
            id="external-build",
            name="Build/lint del proyecto destino",
            status=SKIPPED,
            detail=(
                "Hay package.json pero falta aprobación explícita "
                "(flag --approve-external y validation.approve_external_commands en config)."
            ),
        )
    npm = shutil.which("npm")
    if not npm:
        return CheckResult(
            id="external-build",
            name="Build/lint del proyecto destino",
            status=SKIPPED,
            detail="npm no está disponible en el entorno.",
        )
    command = [npm, "run", "--silent", "build"]
    started = time.monotonic()
    try:
        proc = subprocess.run(  # noqa: S603 - comando aprobado explícitamente por el usuario
            command,
            cwd=output_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            id="external-build",
            name="Build/lint del proyecto destino",
            status=FAIL,
            detail="El build excedió el tiempo máximo (300s).",
            evidence={"cmd": command},
        )
    duration = round(time.monotonic() - started, 2)
    status = PASS if proc.returncode == 0 else FAIL
    return CheckResult(
        id="external-build",
        name="Build/lint del proyecto destino",
        status=status,
        detail=f"npm run build terminó con código {proc.returncode}.",
        evidence={
            "cmd": command,
            "exit_code": proc.returncode,
            "duration_seconds": duration,
            "stderr_tail": proc.stderr[-500:],
        },
    )


def check_responsive(config: dict[str, Any]) -> CheckResult:
    viewports = dotted_get(config, "validation.viewports", [375, 768, 1280])
    return CheckResult(
        id="responsive",
        name="Pruebas responsive en viewports",
        status=SKIPPED,
        detail=(
            "Requiere un ejecutor de navegador (p. ej. Playwright), que no está "
            "implementado ni instalado en esta versión. No se ejecutó ninguna prueba."
        ),
        evidence={"viewports_configurados": viewports},
        limitations=["Ninguna prueba responsive se ejecutó; no implica que el output sea responsive."],
    )


def check_visual_comparison() -> CheckResult:
    return CheckResult(
        id="visual",
        name="Captura y comparación visual",
        status=SKIPPED,
        detail=(
            "Sin herramienta de captura ni referencias visuales configuradas; "
            "no se realizó ninguna comparación."
        ),
        limitations=["La fidelidad visual no está verificada por comparación de píxeles."],
    )


# ---------------------------------------------------------------------------
# Orquestación
# ---------------------------------------------------------------------------

def run_validate(project: Project, profile_id: str, approve_external: bool = False) -> ValidationReport:
    output_dir = project.paths.output_profile_dir(profile_id)
    if not output_dir.is_dir():
        raise DesignPipelineError(
            f"No hay salida para el perfil {profile_id}: ejecutá generate primero."
        )
    specs = load_specs(project)
    config = project.config

    report = ValidationReport(created_at=iso_now(), profile=profile_id)
    report.add(check_files_integrity(project, output_dir))
    report.add(check_source_isolation(project))
    report.add(check_specs_schema(project))
    report.add(check_manifests(project))
    report.add(check_references(project, output_dir, specs))
    report.add(check_class_coverage(output_dir))
    report.add(check_accessibility(output_dir))
    report.add(check_framework_integration(project, profile_id, specs))
    report.add(check_external_build(project, profile_id, approve_external))
    report.add(check_responsive(config))
    report.add(check_visual_comparison())
    report.finalize()
    return report


def write_validation_report(project: Project, report: ValidationReport) -> None:
    payload = report.to_dict()
    (project.paths.reports_dir / "validation-report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (project.paths.reports_dir / "VALIDATION.md").write_text(
        render_validation_markdown(report), encoding="utf-8"
    )
    state = project.load_state()
    state.last_validation = {
        "created_at": report.created_at,
        "profile": report.profile,
        "verdict": report.verdict,
        "summary": report.summary,
    }
    project.save_state()


def render_validation_markdown(report: ValidationReport) -> str:
    marks = {
        PASS: "✅ PASS",
        FAIL: "❌ FAIL",
        SKIPPED: "⏭️ SKIPPED",
        NEEDS_REVIEW: "🔍 NEEDS_REVIEW",
    }
    lines = [
        "# Validación",
        "",
        f"- **Fecha:** {report.created_at}",
        f"- **Perfil:** `{report.profile}`",
        f"- **Veredicto:** `{report.verdict}`",
        f"- **Resumen:** PASS {report.summary.get(PASS, 0)} · FAIL {report.summary.get(FAIL, 0)} · "
        f"SKIPPED {report.summary.get(SKIPPED, 0)} · NEEDS_REVIEW {report.summary.get(NEEDS_REVIEW, 0)}",
        "",
    ]
    for check in report.checks:
        lines.append(f"## {marks.get(check.status, check.status)} — {check.name}")
        lines.append("")
        lines.append(f"- **Detalle:** {check.detail}")
        if check.evidence:
            evidence = json.dumps(check.evidence, ensure_ascii=False)
            lines.append(f"- **Evidencia:** `{evidence[:400]}`")
        for limitation in check.limitations:
            lines.append(f"- **Limitación:** {limitation}")
        lines.append("")
    lines += [
        "## Recordatorio",
        "",
        "- Los estados SKIPPED y NEEDS_REVIEW **no** significan que la comprobación pasó: "
        "significan que no se ejecutó o que requiere revisión humana.",
    ]
    return "\n".join(lines) + "\n"
