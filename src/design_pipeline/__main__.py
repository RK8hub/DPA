"""Permite ejecutar ``python -m design_pipeline`` sin entry point instalado."""

from design_pipeline.cli import main

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
