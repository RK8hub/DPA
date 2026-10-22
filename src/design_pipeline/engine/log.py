"""Registro estructurado de ejecuciones (JSONL) con redacción de secretos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from design_pipeline.utils import atomic_write_text, iso_now, redact


class RunLogger:
    """Escribe eventos de una ejecución a ``runs/<run_id>.jsonl``.

    Nunca registra variables de entorno completas ni valores bajo claves
    sensibles (la redacción vive en :func:`design_pipeline.utils.redact`).
    """

    def __init__(self, runs_dir: Path, run_id: str, stage: str) -> None:
        self.runs_dir = runs_dir
        self.run_id = run_id
        self.stage = stage
        self.path = runs_dir / f"{run_id}.jsonl"
        self.events = 0
        runs_dir.mkdir(parents=True, exist_ok=True)

    def event(self, event_type: str, **fields: Any) -> dict[str, Any]:
        record: dict[str, Any] = {
            "ts": iso_now(),
            "run_id": self.run_id,
            "stage": self.stage,
            "type": event_type,
        }
        record.update(redact(fields))
        self.events += 1
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def command(
        self, cmd: list[str], exit_code: int | None, duration_s: float, note: str = ""
    ) -> None:
        """Registra la ejecución de un comando externo con su resultado."""
        self.event(
            "command",
            cmd=cmd,
            exit_code=exit_code,
            duration_seconds=round(duration_s, 3),
            note=note,
        )

    def append_summary(self, summary_path: Path, lines: list[str]) -> None:
        """Agrega un resumen humano en Markdown al log consolidado."""
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        block = [f"## Ejecución `{self.run_id}` — etapa `{self.stage}` ({iso_now()})", ""]
        block.extend(lines)
        block.append("")
        if summary_path.exists():
            existing = summary_path.read_text(encoding="utf-8")
            atomic_write_text(summary_path, existing + "\n".join(block))
        else:
            header = "# Resumen de ejecuciones\n"
            atomic_write_text(summary_path, header + "\n".join(block))


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
