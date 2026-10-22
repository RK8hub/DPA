"""Primitivas de consola para la TUI (stdlib, probables de testear).

Todas las lecturas pasan por :func:`read_line` para poder inyectar entradas
en las pruebas sin terminal real (ver :func:`set_input`).
"""

from __future__ import annotations

import sys
from typing import Callable


class TuiAbort(Exception):
    """El usuario canceló la interacción (opción salir / EOF / Ctrl-C)."""


_INPUT: Callable[[str], str] = input


def set_input(func: Callable[[str], str]) -> None:
    """Reemplaza la función de lectura (usado por las pruebas)."""
    global _INPUT
    _INPUT = func


def read_line(prompt: str) -> str:
    try:
        return _INPUT(prompt)
    except (EOFError, KeyboardInterrupt):
        raise TuiAbort("Entrada cancelada por el usuario.") from None


def is_interactive() -> bool:
    stdin = getattr(sys.stdin, "isatty", None)
    return bool(stdin and stdin())


def menu(title: str, options: list[str], *, allow_cancel: bool = True) -> int:
    """Muestra un menú numerado. Devuelve el índice elegido (0-based).

    Opción 0 implícita: 'Salir/volver' cuando ``allow_cancel``.
    """
    print()
    print(f"== {title} ==")
    start = 1 if allow_cancel else 0
    if allow_cancel:
        print("  0. Volver")
    for offset, label in enumerate(options, start=start):
        print(f"  {offset}. {label}")
    while True:
        raw = read_line("> ").strip()
        if not raw:
            continue
        try:
            choice = int(raw)
        except ValueError:
            print("  Ingresá un número.")
            continue
        if allow_cancel and choice == 0:
            raise TuiAbort("Volver.")
        if start <= choice <= start + len(options) - 1:
            return choice - start
        print("  Opción fuera de rango.")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    raw = read_line(f"{prompt}{suffix}: ").strip()
    return raw or default


def confirm(prompt: str, *, default: bool = False) -> bool:
    hint = "s/N" if not default else "S/n"
    raw = read_line(f"{prompt} ({hint}): ").strip().lower()
    if not raw:
        return default
    return raw in {"s", "si", "sí", "y", "yes"}


def choose(title: str, options: list[tuple[str, str]], *, allow_cancel: bool = True) -> str | None:
    """Menú de opciones con clave/etiqueta; devuelve la clave elegida."""
    labels = [f"{key} — {label}" for key, label in options]
    index = menu(title, labels, allow_cancel=allow_cancel)
    return options[index][0]


def pause(message: str = "Continuar...") -> None:
    read_line(f"\n{message} [Enter] ")


def table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [
        max(len(headers[index]), *(len(str(row[index])) for row in rows)) if rows else len(headers[index])
        for index in range(len(headers))
    ]
    line = "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    print(line)
    print("  ".join("-" * widths[index] for index in range(len(headers))))
    for row in rows:
        print("  ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(row)))
