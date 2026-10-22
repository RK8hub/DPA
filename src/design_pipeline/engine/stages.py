"""Definición explícita de las etapas del pipeline (máquina de estados)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StageDef:
    """Contrato de una etapa: id estable, requisitos y artefactos esperados."""

    id: str
    letter: str
    label: str
    requires: tuple[str, ...] = ()
    description: str = ""
    expected_artifacts: tuple[str, ...] = ()


STAGES: tuple[StageDef, ...] = (
    StageDef(
        id="init",
        letter="A",
        label="Inicialización",
        requires=(),
        description="Crea el workspace del proyecto, detecta herramientas y registra la configuración inicial.",
        expected_artifacts=("project.yaml", "state.yaml"),
    ),
    StageDef(
        id="import",
        letter="B",
        label="Importación e inventario",
        requires=("init",),
        description="Inventarioa la exportación (rutas, tipos, hashes, referencias, duplicados) sin ejecutar ni modificar nada.",
        expected_artifacts=("inventory.json", "reports/IMPORT-REPORT.md"),
    ),
    StageDef(
        id="analyze",
        letter="C",
        label="Análisis del lote",
        requires=("import",),
        description="Analiza componentes, estilos, tokens, relaciones, accesibilidad e incertidumbres.",
        expected_artifacts=("analysis.json", "reports/ANALYSIS.md", "reports/COMPONENT-MAP.md", "reports/uncertainties.md"),
    ),
    StageDef(
        id="rules",
        letter="D",
        label="Reglas de diseño y preguntas",
        requires=("import",),
        description="Construye reglas de diseño (modo guiado o descubrimiento) con procedencia y estado de aprobación.",
        expected_artifacts=("rules/design-rules.yaml", "rules/questions.yaml", "reports/DESIGN-RULES.md", "reports/DECISIONS.md"),
    ),
    StageDef(
        id="spec",
        letter="E",
        label="Especificación intermedia",
        requires=("analyze",),
        description="Produce especificaciones independientes del framework por componente (JSON validado + Markdown).",
        expected_artifacts=("specs/index.json",),
    ),
    StageDef(
        id="generate",
        letter="F",
        label="Generación",
        requires=("spec",),
        description="Genera el código de salida por perfil de destino en una carpeta aislada.",
        expected_artifacts=("output", "reports/generation-notes.md"),
    ),
    StageDef(
        id="validate",
        letter="G",
        label="Validación",
        requires=("generate",),
        description="Ejecuta validadores deterministas y registra PASS/FAIL/SKIPPED/NEEDS_REVIEW con evidencia.",
        expected_artifacts=("reports/validation-report.json", "reports/VALIDATION.md"),
    ),
    StageDef(
        id="report",
        letter="H",
        label="Revisión y entrega",
        requires=("validate",),
        description="Produce el resumen de entrega y la checklist de revisión humana.",
        expected_artifacts=("reports/DELIVERY.md", "reports/REVIEW-CHECKLIST.md"),
    ),
)

STAGE_BY_ID: dict[str, StageDef] = {stage.id: stage for stage in STAGES}
STAGE_IDS: tuple[str, ...] = tuple(stage.id for stage in STAGES)

# Estados posibles de una etapa.
PENDING = "pending"
IN_PROGRESS = "in_progress"
DONE = "done"
FAILED = "failed"
STALE = "stale"

STAGE_STATUSES = (PENDING, IN_PROGRESS, DONE, FAILED, STALE)


def downstream(stage_id: str) -> list[str]:
    """Devuelve las etapas posteriores a ``stage_id`` en orden."""
    index = STAGE_IDS.index(stage_id)
    return list(STAGE_IDS[index + 1 :])
