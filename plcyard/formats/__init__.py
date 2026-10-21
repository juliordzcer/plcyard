"""Program files by extension: .plcy (PLCYard projects, any controller) and .rsl (SLC 500 ladder)."""

from __future__ import annotations

from pathlib import Path

from ..core.program import Program
from . import plcy, rsl

FILTER = "PLCYard projects (*.plcy);;SLC 500 ladder (*.rsl);;All programs (*.plcy *.rsl)"
OPEN_FILTER = "All programs (*.plcy *.rsl);;PLCYard projects (*.plcy);;SLC 500 ladder (*.rsl)"
FormatError = (rsl.RslError, plcy.PlcyError)


def _module(path: str | Path):
    return rsl if Path(path).suffix.lower() == ".rsl" else plcy


def load(path: str | Path) -> Program:
    return _module(path).load(path)


def save(program: Program, path: str | Path) -> list[str]:
    """Write `program`; returns characters the format could not hold."""
    return _module(path).save(program, path)
