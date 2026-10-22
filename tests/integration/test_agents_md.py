"""Consistencia de AGENTS.md: sólo puede citar comandos y docs reales.

Si alguien cambia la CLI sin actualizar las instrucciones para agentes
(el entrypoint que un agente lee al recibir el repo), estas pruebas fallan.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from design_pipeline.cli import build_parser

ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_MD = ROOT / "AGENTS.md"


def _command_tree() -> dict[str, set[str]]:
    parser = build_parser()
    tree: dict[str, set[str]] = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                subs: set[str] = set()
                for inner in sub._actions:
                    if isinstance(inner, argparse._SubParsersAction):
                        subs |= set(inner.choices)
                tree[name] = subs
    return tree


def test_agents_md_existe():
    assert AGENTS_MD.exists(), "AGENTS.md es el entrypoint de agentes: debe existir en la raíz."


def test_agents_md_cita_solo_comandos_reales():
    text = AGENTS_MD.read_text(encoding="utf-8")
    tree = _command_tree()
    cited = re.findall(
        r"design-pipeline[ \t]+([a-z][a-z-]*)((?:[ \t]+[a-z][a-z-]*)?)", text
    )
    assert cited, "Deben citarse comandos reales de la CLI."
    for top, rest in cited:
        assert top in tree, f"AGENTS.md cita un comando inexistente: '{top}'"
        second = rest.strip().split()
        if second:
            assert second[0] in tree[top], (
                f"AGENTS.md cita un subcomando inexistente: '{top} {second[0]}'"
            )


def test_agents_md_paso0_notificacion_obligatoria():
    text = AGENTS_MD.read_text(encoding="utf-8")
    assert "Notificación obligatoria" in text
    # Debe exigir avisar al usuario al terminar de instalar, en la conversación.
    assert re.search(r"misma\s+conversación", text)
    assert re.search(r"2 a 4\s+oraciones", text)


def test_agents_md_reglas_de_honestidad():
    text = AGENTS_MD.read_text(encoding="utf-8")
    assert "SKIPPED" in text and "NEEDS_REVIEW" in text
    assert "jamás" in text  # jamás PASS sin evidencia
    assert "solo lectura" in text or "sólo lectura" in text
    assert "AGENT-BUILT.md" in text
    assert "no afirmes compatibilidad" in text.lower() or "No afirmes compatibilidad" in text


def test_agents_md_referencia_documentacion_existente():
    text = AGENTS_MD.read_text(encoding="utf-8")
    for relative in re.findall(r"`((?:README\.md|docs/[A-Z-]+\.md))`", text):
        assert (ROOT / relative).exists(), (
            f"AGENTS.md referencia un documento inexistente: {relative}"
        )
