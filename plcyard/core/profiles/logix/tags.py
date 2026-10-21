"""Logix tag memory (Studio 5000 style): named, typed tags instead of a file data table.

References: `Start`, `Count.ACC`, `Timer1.DN`, `Flags.3` (bit of an integer), module tags
`Local:1:I.Data.0`, system flags `S:FS` (first scan) and `S:V` (overflow). Names are
case-insensitive, as in Studio 5000.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TYPES = ("BOOL", "INT", "DINT", "REAL", "TIMER", "COUNTER")
STRUCTS = {
    "TIMER": {"PRE": "DINT", "ACC": "DINT", "EN": "BOOL", "TT": "BOOL", "DN": "BOOL"},
    "COUNTER": {"PRE": "DINT", "ACC": "DINT", "CU": "BOOL", "CD": "BOOL", "DN": "BOOL",
                "OV": "BOOL", "UN": "BOOL"},
}
BITS = {"INT": 16, "DINT": 32}
INPUT_SLOTS, OUTPUT_SLOTS = (1, 3, 5), (2, 4, 6)
SYSTEM = {"S:FS": "BOOL", "S:V": "BOOL"}

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_REF = re.compile(rf"^(?P<base>Local:\d+:[IO]|S:FS|S:V|{_NAME})(?P<members>(?:\.{_NAME})*)(?:\.(?P<bit>\d+))?$", re.I)


class TagError(Exception):
    pass


@dataclass(frozen=True)
class Ref:
    base: str            # canonical (declared) tag name
    member: str | None   # TIMER/COUNTER member, or "DATA" of a module tag
    bit: int | None
    type: str            # type of what the reference points at: BOOL, INT, DINT, REAL, TIMER, COUNTER


def module_tags() -> dict[str, str]:
    out = {f"Local:{s}:I": "MODULE" for s in INPUT_SLOTS}
    out.update({f"Local:{s}:O": "MODULE" for s in OUTPUT_SLOTS})
    return out


def wrap(value: int, type_: str) -> tuple[int, bool]:
    """Two's-complement wrap to the type's width; second value says whether it overflowed."""
    n = BITS.get(type_)
    if n is None:
        return value, False
    lo, hi = -(1 << (n - 1)), (1 << (n - 1)) - 1
    if lo <= value <= hi:
        return value, False
    return ((value - lo) % (1 << n)) + lo, True


def default(type_: str):
    if type_ in STRUCTS:
        return {m: (False if t == "BOOL" else 0) for m, t in STRUCTS[type_].items()}
    return {"BOOL": False, "REAL": 0.0}.get(type_, 0)


class TagTable:
    def __init__(self, decls: dict[str, dict] | None = None):
        self.types: dict[str, str] = {}
        self.values: dict[str, object] = {}
        self._canon: dict[str, str] = {}
        for name, t in {**module_tags(), **SYSTEM}.items():
            self._add(name, t)
        self.declare(decls or {})

    # -- declarations ----------------------------------------------------------
    def _add(self, name: str, type_: str, value=None) -> None:
        self._canon[name.lower()] = name
        self.types[name] = type_
        self.values[name] = {"DATA": 0} if type_ == "MODULE" else default(type_)
        if value is not None and type_ not in STRUCTS:
            self.values[name] = float(value) if type_ == "REAL" else (bool(value) if type_ == "BOOL" else int(value))

    def declare(self, decls: dict[str, dict]) -> None:
        """Program tags: {name: {"type": "DINT", "value": 0}}. Raises TagError for a bad declaration."""
        for name, d in decls.items():
            t = str(d.get("type", "")).upper()
            if not re.fullmatch(_NAME, name):
                raise TagError(f"{name!r} is not a valid tag name (letters, digits and _; no leading digit)")
            if t not in TYPES:
                raise TagError(f"tag {name}: unknown type {d.get('type')!r} (use {', '.join(TYPES)})")
            if name.lower() in self._canon:
                raise TagError(f"tag {name} is declared twice")
            self._add(name, t, d.get("value"))

    def clear(self, decls: dict[str, dict], keep_io: bool = True) -> None:
        io = {n: dict(v) for n, v in self.values.items() if self.types[n] == "MODULE"}
        self.__init__(decls)
        if keep_io:
            self.values.update(io)

    # -- references ------------------------------------------------------------
    def ref(self, text: str) -> Ref:
        m = _REF.match(text.strip())
        if not m:
            raise TagError(f"{text!r} is not a tag reference")
        base = self._canon.get(m["base"].lower())
        if base is None:
            raise TagError(f"tag {m['base']} does not exist")
        t = self.types[base]
        members = [x for x in (m["members"] or "").split(".") if x]
        member = None
        if t == "MODULE":
            if [x.upper() for x in members] != ["DATA"]:
                raise TagError(f"{base}: use {base}.Data")
            member, t = "DATA", "DINT"
        elif members:
            if t not in STRUCTS or len(members) > 1 or members[0].upper() not in STRUCTS[t]:
                raise TagError(f"{base} has no member {'.'.join(members)}")
            member = members[0].upper()
            t = STRUCTS[self.types[base]][member]
        bit = int(m["bit"]) if m["bit"] is not None else None
        if bit is not None:
            if t not in BITS:
                raise TagError(f"{text}: only INT and DINT values have numbered bits")
            if bit >= BITS[t]:
                raise TagError(f"{text}: bit {bit} out of range (0-{BITS[t] - 1})")
            t = "BOOL"
        return Ref(base, member, bit, t)

    def _get(self, r: Ref):
        v = self.values[r.base]
        return v[r.member] if r.member else v

    def _put(self, r: Ref, value) -> None:
        if r.member:
            self.values[r.base][r.member] = value
        else:
            self.values[r.base] = value

    def read_bit(self, text: str) -> bool:
        r = self.ref(text)
        if r.type != "BOOL":
            raise TagError(f"{text} is a {r.type}, not a BOOL")
        v = self._get(r)
        return bool((int(v) >> r.bit) & 1) if r.bit is not None else bool(v)

    def write_bit(self, text: str, on: bool) -> None:
        r = self.ref(text)
        if r.type != "BOOL":
            raise TagError(f"{text} is a {r.type}, not a BOOL")
        if r.bit is None:
            return self._put(r, bool(on))
        base_type = STRUCTS[self.types[r.base]][r.member] if r.member and self.types[r.base] in STRUCTS else (
            "DINT" if r.member else self.types[r.base])
        v = int(self._get(r)) & ((1 << BITS[base_type]) - 1)
        v = v | (1 << r.bit) if on else v & ~(1 << r.bit)
        self._put(r, wrap(v, base_type)[0])

    def read_word(self, text: str):
        r = self.ref(text)
        if r.type in STRUCTS:
            raise TagError(f"{text} is a {r.type}; use a member like {text}.ACC")
        v = self._get(r)
        if r.type == "BOOL":
            return int(self.read_bit(text))
        return v

    def write_word(self, text: str, value) -> bool:
        """Store a number, converted to the tag's type. Returns True on integer overflow."""
        r = self.ref(text)
        if r.type in STRUCTS:
            raise TagError(f"{text} is a {r.type}; use a member like {text}.PRE")
        if r.type == "BOOL":
            self.write_bit(text, bool(value))
            return False
        if r.type == "REAL":
            self._put(r, float(value))
            return False
        v = int(round(value)) if isinstance(value, float) else int(value)
        v, over = wrap(v, r.type)
        self._put(r, v)
        return over

    def element(self, text: str) -> dict:
        """The member dict of a TIMER or COUNTER tag."""
        r = self.ref(text)
        if r.type not in STRUCTS:
            raise TagError(f"{text} is not a TIMER or COUNTER")
        return self.values[r.base]

    # -- I/O image ---------------------------------------------------------------
    def module_data(self, slot: int, direction: str) -> int:
        return int(self.values[f"Local:{slot}:{direction}"]["DATA"])

    def set_module_data(self, slot: int, direction: str, value: int) -> None:
        self.values[f"Local:{slot}:{direction}"]["DATA"] = wrap(int(value), "DINT")[0]

    def names(self) -> list[str]:
        return [n for n in self.types if self.types[n] != "MODULE" and n not in SYSTEM]
