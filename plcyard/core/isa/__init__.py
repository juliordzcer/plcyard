"""Instruction registry: specs (operands, labels, how the ladder draws them) and executors.

Executors get the rung condition in and return the condition out. The PLC's instruction set lives
in core/plc/instructions.py and registers itself with `instruction(..., into=SPECS)`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable


class PlcFault(Exception):
    """Major fault: the processor stops."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


class ReturnFromSubroutine(Exception):
    pass


@dataclass(frozen=True)
class Spec:
    mnemonic: str
    title: str
    family: str
    operands: tuple[str, ...]   # operand kinds (see core/plc/instructions.KINDS)
    labels: tuple[str, ...]
    output: bool                # output instructions are drawn against the right rail
    run: Callable
    on_download: Callable | None = None
    on_prescan: Callable | None = None
    optional: int = 0           # trailing operands that may be left out
    shape: str = "block"        # contact | contact_nc | coil | small | block (how the ladder draws it)
    letter: str = ""            # drawn inside a coil or small box (L, U, S, R, P…)


SPECS: dict[str, Spec] = {}     # the PLC's instruction set, filled by core/plc/instructions.py

SHAPES = {"XIC": ("contact", ""), "XIO": ("contact_nc", ""), "OTE": ("coil", ""),
          "OTL": ("coil", "L"), "OTU": ("coil", "U"), "OSR": ("small", "OSR"), "NOP": ("small", "NOP")}


def instruction(mnemonic, title, family, operands, labels, output=False,
                on_download=None, on_prescan=None, optional=0, *, into=None, shape=None, letter=None):
    """Register an executor in `into` (the PLC's SPECS by default)."""
    default_shape, default_letter = SHAPES.get(mnemonic, ("block", ""))

    def deco(fn):
        (SPECS if into is None else into)[mnemonic] = Spec(mnemonic, title, family, tuple(operands), tuple(labels), output, fn, on_download,
                              on_prescan, optional, shape or default_shape, default_letter if letter is None else letter)
        return fn
    return deco


def is_output(mnemonic: str, specs: dict[str, Spec] | None = None) -> bool:
    spec = (SPECS if specs is None else specs).get(mnemonic)
    return bool(spec and spec.output)


_NUMBER = re.compile(r"^[-+]?(\d[\d_]*\.?\d*([eE][-+]?\d+)?|\.\d+)$")
_BASED = re.compile(r"^(2|8|16)#([0-9A-Fa-f_]+)$")
_HEX = re.compile(r"^-?[0-9A-F]+H$", re.I)


def parse_literal(text: str) -> int | float | None:
    """A number (100, -2.5, 1e3, 16#FF, 2#1010, 0FFH); None when the text is not one."""
    s = text.strip()
    m = _BASED.match(s)
    if m:
        return int(m[2].replace("_", ""), int(m[1]))
    if _HEX.match(s) and s[0].isdigit():
        return int(s[:-1], 16)
    if not _NUMBER.match(s):
        return None
    s = s.replace("_", "")
    try:
        return int(s)
    except ValueError:
        return float(s)
