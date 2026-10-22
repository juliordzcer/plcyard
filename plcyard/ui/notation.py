"""How the program is shown and typed: the learner picks a notation in Tools → Options; files always
keep one canonical form (core/plc).

  A  mnemonics:   XIC / XIO / OTE / OTL / OTU, MOV, EQU…, timers with PRE / ACC / DN,
                  I/O as Local:1:I.Data.0, Local:7:I.Ch0Data, first scan S:FS
  B  IEC symbols: NO / NC contacts, S / R coils, MOVE, CMP ==…, timers with PT / ET / Q,
                  I/O as %I0.0, %IW64, first scan FirstScan
"""

from __future__ import annotations

import re

from PySide6.QtCore import QSettings

from ..core.plc import PLC
from ..core.plc.memory import absolute_to_module

A, B = "A", "B"
NAMES = {A: "Mnemonics (XIC, OTE, MOV; Local:1:I.Data.0; TIMER .PRE .ACC .DN)",
         B: "IEC symbols (NO/NC contacts, MOVE; %I0.0; timer .PT .ET .Q)"}

_current = None

MNEMONICS_B = {"MOV": "MOVE", "EQU": "CMP ==", "NEQ": "CMP <>", "LES": "CMP <", "LEQ": "CMP <=", "GRT": "CMP >",
               "GEQ": "CMP >=", "LIM": "IN_RANGE", "RES": "RESET", "JSR": "CALL", "OTL": "S", "OTU": "R",
               "XIC": "NO", "XIO": "NC", "OTE": "COIL", "ONS": "P_TRIG", "SQR": "SQRT", "TOD": "TO_BCD", "FRD": "FROM_BCD"}
WORDS_B = {"XIC": "NO contact", "XIO": "NC contact", "OTE": "coil", "OTL": "set coil (S)", "OTU": "reset coil (R)",
           "MOV": "MOVE", "EQU": "CMP ==", "NEQ": "CMP <>", "LES": "CMP <", "LEQ": "CMP <=", "GRT": "CMP >",
           "GEQ": "CMP >=", "LIM": "IN_RANGE", "RES": "RESET", "JSR": "CALL", "TOD": "TO_BCD", "FRD": "FROM_BCD",
           "ONS": "P_TRIG"}
LABELS_B = {
    "TON": ["Instance", "PT", "ET"], "TOF": ["Instance", "PT", "ET"], "TP": ["Instance", "PT", "ET"],
    "RTO": ["Instance", "PT", "ET"],
    "CTU": ["Instance", "PV", "R"], "CTD": ["Instance", "PV", "LD"], "MOV": ["IN", "OUT"], "CLR": ["OUT"],
    "LIM": ["MIN", "VAL", "MAX"], "RES": ["Instance"],
    **{m: ["IN1", "IN2"] for m in ("EQU", "NEQ", "LES", "LEQ", "GRT", "GEQ")},
    **{m: ["IN1", "IN2", "OUT"] for m in ("ADD", "SUB", "MUL", "DIV", "MOD", "AND", "OR", "XOR")},
    **{m: ["IN", "OUT"] for m in ("NEG", "SQR", "NOT", "TOD", "FRD")},
}
LETTERS = {A: {"OTL": "L", "OTU": "U"}, B: {"OTL": "S", "OTU": "R"}}
LIVE_B = {"Accum": "ET", "Position": "POS"}
PINS_B = {"DN": "Q", "TT": "", "EN": ""}
MEMBERS_B = {"TIMER": {"PRE": "PT", "ACC": "ET", "DN": "Q", "EN": "IN"},
             "COUNTER": {"PRE": "PV", "ACC": "CV", "DN": "Q"}}
MEMBERS_A = {t: {b: a for a, b in m.items()} for t, m in MEMBERS_B.items()}
TYPES_B = {"BOOL": "Bool", "SINT": "SInt", "INT": "Int", "DINT": "DInt", "REAL": "Real", "TIME": "Time"}
SYSTEM_A = {"FirstScan": "S:FS", "Overflow": "S:V"}

_IO = re.compile(r"%[IQ]W?\d+(?:\.\d)?")
_REF = re.compile(r'^(#?"?)([A-Za-z_]\w*)("?)((?:\[[^\]]*\])*)\.([A-Za-z_]\w*)$')


def current() -> str:
    global _current
    if _current is None:
        _current = str(QSettings("PLCYard", "PLCYard").value("notation", A))
        if _current not in (A, B):
            _current = A
    return _current


def set_current(n: str) -> None:
    global _current
    _current = n
    QSettings("PLCYard", "PLCYard").setValue("notation", n)


def mnemonic(m: str) -> str:
    return MNEMONICS_B.get(m, m) if current() == B else m


def labels(m: str, default: list[str]) -> list[str]:
    if current() == B and m in LABELS_B:
        return LABELS_B[m] + default[len(LABELS_B[m]):]
    return default


def letter(m: str, default: str) -> str:
    return LETTERS[current()].get(m, default)


def live_label(label: str, m: str = "") -> str:
    if current() != B:
        return label
    if label == "Accum" and m in ("CTU", "CTD"):
        return "CV"
    return LIVE_B.get(label, label)


def pin(name: str) -> str:
    return PINS_B.get(name, name) if current() == B else name


def type_name(t: str) -> str:
    return TYPES_B.get(t, t) if current() == B else t


def _types(program) -> dict[str, str]:
    """Tag name (lower case) → element type of the tag (TIMER for T4: TIMER[10])."""
    out = {}
    for n, d in (program.tags.items() if program is not None else ()):
        t = str(d.get("type", "")).upper()
        m = re.match(r"^(\w+)\s*\[", t) or re.match(r"^ARRAY\s*\[.*\]\s+OF\s+(\w+)$", t)
        out[n.lower()] = m[1] if m else t
    return out


def _members(op: str, program, table: dict) -> str:
    m = _REF.match(op)
    if not m:
        return op
    t = _types(program).get(m[2].lower())
    new = table.get(t, {}).get(m[5].upper())
    return f"{m[1]}{m[2]}{m[3]}{m[4]}.{new}" if new else op


def show(op: str, program=None) -> str:
    """A canonical operand as the current notation writes it."""
    if not op or op == "?":
        return op
    if current() == A:
        op = SYSTEM_A.get(op, op)
        return absolute_to_module(op) or op
    return _members(op, program, MEMBERS_B)


def store(op: str, program=None) -> str:
    """A typed operand in canonical form (either notation is accepted)."""
    op = PLC.normalize(op)
    return _members(op, program, MEMBERS_A)


def io_name(direction: str, slot: int, bit: int | None = None) -> str:
    """Name of a simulated I/O point in the current notation."""
    return show(PLC.io_name(direction, slot, bit))


def analog_name(direction: str, channel: int) -> str:
    return show(PLC.analog_name(direction, channel))


def show_comment(text: str) -> str:
    """A rung comment or description: canonical addresses in it, in the current notation."""
    if current() == A:
        return _IO.sub(lambda m: absolute_to_module(m.group()) or m.group(), text)
    return text


def show_text(text: str) -> str:
    """Exercise text: addresses (written canonical) and, in notation B, instruction names."""
    if current() == A:
        text = _IO.sub(lambda m: absolute_to_module(m.group()) or m.group(), text)
        return re.sub(r"\bFirstScan\b", "S:FS", text)
    return re.sub(r"`(XIC|XIO|OTE|OTL|OTU|MOV|EQU|NEQ|LES|LEQ|GRT|GEQ|LIM|RES|JSR|TOD|FRD|ONS)`",
                  lambda m: f"`{WORDS_B[m[1]]}`", text)
