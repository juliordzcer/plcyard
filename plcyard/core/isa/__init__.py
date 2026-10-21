"""Instruction set: specs (operands, validation, drawing labels) and executors.

Executors get the rung-condition-in and return rung-condition-out, as in the
SLC-500 manual (1747-RM001). Output instructions pass their input through.
Families live in sibling modules and register themselves with `instruction`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from ..address import Address, AddressError, parse_address, parse_literal  # noqa: F401  (re-exported)
from ..datatable import DataTable, DataTableError, to_int16


class PlcFault(Exception):
    """Major fault: the processor stops and sets S:1/13 and S:6."""

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
    operands: tuple[str, ...]   # operand kinds, see KINDS
    labels: tuple[str, ...]
    output: bool                # output instructions are drawn against the right rail
    run: Callable
    on_download: Callable | None = None
    on_prescan: Callable | None = None
    optional: int = 0           # trailing operands that may be left out


KINDS = {
    "bit": "a bit address like I:1/0 or B3:0/5",
    "word": "a word address like N7:0",
    "value": "a number or a word address",
    "timer": "a timer like T4:0",
    "counter": "a counter like C5:0",
    "control": "a control element like R6:0",
    "element": "a timer, counter or control element",
    "file": "a file address with # like #B3:0",
    "int": "a whole number",
    "sub": "a subroutine file like U:3",
}

SPECS: dict[str, Spec] = {}


def instruction(mnemonic, title, family, operands, labels, output=False,
                on_download=None, on_prescan=None, optional=0):
    def deco(fn):
        SPECS[mnemonic] = Spec(mnemonic, title, family, tuple(operands), tuple(labels),
                               output, fn, on_download, on_prescan, optional)
        return fn
    return deco


# -- status file bits used by the instructions ------------------------------
CARRY, OVERFLOW, ZERO, SIGN = "S:0/0", "S:0/1", "S:0/2", "S:0/3"
OVERFLOW_TRAP = "S:5/0"
MATH_LOW, MATH_HIGH = "S:13", "S:14"
INT_MIN, INT_MAX = -32768, 32767


class Context:
    """What an executing instruction may touch during a scan."""

    def __init__(self, dt: DataTable):
        self.dt = dt
        self.now_ms = 0.0
        self.timer_marks: dict[str, float] = {}
        self.call: Callable[[int], None] = lambda n: None

    # operands
    def bit(self, op: str) -> bool:
        return self.dt.read_bit(op)

    def set_bit(self, op: str, on: bool) -> None:
        self.dt.write_bit(op, on)

    def value(self, op: str) -> int | float:
        lit = parse_literal(op)
        if lit is not None:
            return lit
        return self.dt.read_word(op)

    def word(self, op: str) -> int:
        return int(self.value(op))

    def is_float(self, op: str) -> bool:
        lit = parse_literal(op)
        if lit is not None:
            return isinstance(lit, float)
        return self.dt.addr(op).type == "F"

    def store(self, dest: str, value: int | float) -> None:
        self.dt.write_word(dest, value)

    def element_base(self, op: str) -> tuple[list, int]:
        """Words list and index of word 0 of a T/C/R element."""
        a = self.dt.addr(op)
        f, idx, _ = self.dt._locate(Address(a.type, a.file, a.element))
        return f.words, idx

    # arithmetic status
    def flags(self, *, carry=False, overflow=False, value=0) -> None:
        self.set_bit(CARRY, carry)
        self.set_bit(OVERFLOW, overflow)
        self.set_bit(ZERO, value == 0)
        self.set_bit(SIGN, value < 0)
        if overflow:
            self.set_bit(OVERFLOW_TRAP, True)

    def store_int_result(self, dest: str, result: int | float, *, carry=False) -> None:
        """Store a math result; integers saturate at ±32767 with overflow (S:2/14 clear)."""
        if self.dt.addr(dest).type == "F":
            self.store(dest, float(result))
            self.flags(carry=carry, value=result)
            return
        r = round_half_away(result) if isinstance(result, float) else result
        if r > INT_MAX or r < INT_MIN:
            self.store(dest, INT_MAX if r > 0 else INT_MIN)
            self.flags(carry=carry, overflow=True, value=r)
        else:
            self.store(dest, r)
            self.flags(carry=carry, value=r)


def round_half_away(x: float) -> int:
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)


# -- validation ----------------------------------------------------------------
_SUB = re.compile(r"^U:(\d+)$", re.I)


def _check(kind: str, op: str) -> str | None:
    if kind == "int":
        return None if re.fullmatch(r"-?\d+", op) else "must be a whole number"
    if kind == "sub":
        return None if _SUB.match(op) else "must be a subroutine file like U:3"
    if kind == "value" and parse_literal(op) is not None:
        return None
    try:
        a = parse_address(op)
    except AddressError as e:
        return str(e)
    if kind == "bit":
        if a.type == "F":
            return "float elements have no bits"
        return None if a.is_bit else f"{op} is a word; use a bit like {op}/0"
    if kind in ("word", "value"):
        if a.is_file_ref:
            return f"{op} is a file; remove the #"
        return f"{op} is a bit; use a word" if a.is_bit else None
    if kind == "file":
        return None if a.is_file_ref else f"{op} needs # in front (file address)"
    want = {"timer": "T", "counter": "C", "control": "R"}.get(kind)
    if want:
        ok = a.type == want and a.sub is None and a.bit is None
        return None if ok else f"must be {KINDS[kind]}"
    if kind == "element":
        ok = a.type in ("T", "C", "R") and a.sub is None and a.bit is None
        return None if ok else f"must be {KINDS[kind]}"
    return None


def validate(mnemonic: str, operands: list[str]) -> list[str]:
    """Problems with one instruction; empty list means it can be downloaded."""
    spec = SPECS.get(mnemonic)
    if spec is None:
        return [f"{mnemonic} is not supported yet"]
    ops = list(operands)
    if mnemonic == "RET" and len(ops) == 1 and _SUB.match(ops[0]):
        ops = []   # some files write RET,U:n
    n = len(spec.operands)
    if not n - spec.optional <= len(ops) <= n:
        return [f"{mnemonic} needs {n} operand(s), has {len(ops)}"]
    problems = []
    for kind, label, op in zip(spec.operands, spec.labels, ops):
        if op in ("", "?"):
            problems.append(f"{mnemonic}: {label} is not set")
            continue
        msg = _check(kind, op)
        if msg:
            problems.append(f"{mnemonic} {label}: {msg}")
        elif spec.family == "Timer/Counter" and label == "Preset" and mnemonic in ("TON", "TOF", "RTO"):
            lit = parse_literal(op)
            if lit is not None and not 0 <= lit <= 32767:
                problems.append(f"{mnemonic} Preset: a timer preset must be 0 to 32767")
    return problems


def is_output(mnemonic: str) -> bool:
    spec = SPECS.get(mnemonic)
    return bool(spec and spec.output)


from . import bit, timers, compare, math, files, program_control  # noqa: E402,F401  (register)

__all__ = ["SPECS", "Spec", "Context", "validate", "is_output", "PlcFault",
           "ReturnFromSubroutine", "DataTableError", "to_int16"]
