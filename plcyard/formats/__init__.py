"""Program files: .plcy projects (open and save) and .rsl ladder files of the older data-table style
(open only; converted to the PLC on load)."""

from __future__ import annotations

from pathlib import Path

from ..core.program import Program
from . import plcy, rsl

FILTER = "PLCYard projects (*.plcy)"
OPEN_FILTER = "All programs (*.plcy *.rsl);;PLCYard projects (*.plcy);;Older ladder files (*.rsl)"
FormatError = (rsl.RslError, plcy.PlcyError)


def load(path: str | Path) -> Program:
    if Path(path).suffix.lower() == ".rsl":
        return rsl.load(path)
    return plcy.load(path)


def save(program: Program, path: str | Path) -> list[str]:
    """Write `program` as a .plcy project; returns characters that could not be stored (none)."""
    return plcy.save(program, path)
