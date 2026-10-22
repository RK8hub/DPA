"""Utilidades comunes de las pruebas."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURE_EXPORT = Path(__file__).parent / "fixtures" / "fixture-export"


@pytest.fixture
def fixture_export() -> Path:
    return FIXTURE_EXPORT


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws


@pytest.fixture
def copied_export(tmp_path: Path, fixture_export: Path) -> Path:
    """Copia de la fixture para pruebas que pudiesen modificar la entrada."""
    dest = tmp_path / "export-copy"
    shutil.copytree(fixture_export, dest)
    return dest
