"""Etapa B: orquestación de la importación y persistencia de artefactos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from design_pipeline.errors import DesignPipelineError, ImportSafetyError
from design_pipeline.importers.inventory import Inventory, build_inventory
from design_pipeline.reporting.import_report import render_import_report
from design_pipeline.utils import write_json
from design_pipeline.workspace.project import Project


def run_import(project: Project, source: Path) -> dict[str, Any]:
    """Importa ``source`` al proyecto. Nunca escribe dentro de ``source``."""
    if not source.exists():
        raise DesignPipelineError(f"La ruta de entrada no existe: {source}")
    if not source.is_dir():
        raise ImportSafetyError(f"La entrada debe ser un directorio: {source}")

    exclusions = list(project.config.get("exclusions", []) or [])
    text_ext = [str(ext).lower() for ext in project.config.get("text_extensions", []) or []]
    max_bytes = int(project.config.get("max_file_size_mb", 5)) * 1024 * 1024

    inventory = build_inventory(source, text_ext, exclusions, max_bytes)
    if not inventory.files:
        raise ImportSafetyError(
            "No se encontraron archivos tras aplicar las exclusiones. "
            "Revisá la ruta o la configuración de exclusiones."
        )

    _write_artifacts(project, inventory)
    project.set_source(Path(inventory.source_path))
    project.save_data()

    state = project.load_state()
    state.source_path = inventory.source_path
    return {
        "files": len(inventory.files),
        "duplicates": len(inventory.duplicate_groups),
        "broken_references": len(inventory.broken_references),
        "unanalyzed": len(inventory.unanalyzed),
        "report": "reports/IMPORT-REPORT.md",
    }


def _write_artifacts(project: Project, inventory: Inventory) -> None:
    data = inventory.to_dict()
    write_json(project.paths.inventory_json, data)
    report_path = project.paths.reports_dir / "IMPORT-REPORT.md"
    report_path.write_text(render_import_report(inventory), encoding="utf-8")


def load_inventory(project: Project) -> Inventory | None:
    """Rehidrata el inventario desde ``inventory.json``."""
    import json

    path = project.paths.inventory_json
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    from design_pipeline.importers.inventory import FileEntry

    files = [FileEntry(**entry) for entry in data.get("files", [])]
    inventory = Inventory(
        source_path=data["source_path"],
        created_at=data["created_at"],
        source_fingerprint=data["source_fingerprint"],
        exclusions=data.get("exclusions", []),
        max_file_size_bytes=data.get("max_file_size_bytes", 0),
        files=files,
        duplicate_groups=data.get("duplicate_groups", []),
        broken_references=data.get("broken_references", []),
        external_references=data.get("external_references", []),
        unanalyzed=data.get("unanalyzed", []),
        stats=data.get("stats", {}),
    )
    return inventory
