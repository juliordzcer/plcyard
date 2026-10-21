"""S7-1200/1500 memory (TIA Portal style): byte-addressed areas I, Q and M, symbolic PLC tags,
and instances of IEC timers and counters.

Absolute: `%I0.0`, `%Q1.7`, `%M10.3` (bits), `%IB0`, `%MW10` (Int), `%MD20` (DInt). Words are big
endian, as on the real controller: %IW0 is %IB0 (high byte) then %IB1. Symbolic: `Motor` or
`"Motor"`, `MyTimer.Q`, `MyTimer.ET`. `FirstScan` is true on the first scan after RUN.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

AREA_BYTES = 128
TYPES = ("Bool", "Int", "DInt", "Real", "Time", "IEC_TIMER", "IEC_COUNTER")
STRUCTS = {
    "IEC_TIMER": {"PT": "Time", "ET": "Time", "IN": "Bool", "Q": "Bool"},
    "IEC_COUNTER": {"PV": "Int", "CV": "Int", "CU": "Bool", "CD": "Bool", "R": "Bool", "LD": "Bool",
                    "Q": "Bool", "QU": "Bool", "QD": "Bool"},
}
WIDTH = {"B": 1, "W": 2, "D": 4}
RANGE = {"Int": 16, "DInt": 32, "Time": 32}
SYSTEM = {"FirstScan": "Bool"}

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_BIT = re.compile(r"^%?([IQM])(\d+)\.([0-7])$", re.I)
_WORD = re.compile(r"^%?([IQM])([BWD])(\d+)$", re.I)
_SYM = re.compile(rf'^"?({_NAME})"?(?:\.({_NAME}))?$')
_TIME = re.compile(r"^T#(?:(\d+)D_?)?(?:(\d+)H_?)?(?:(\d+)M(?!S)_?)?(?:(\d+)S_?)?(?:(\d+)MS)?$", re.I)


class S7Error(Exception):
    pass


@dataclass(frozen=True)
class Ref:
    area: str | None       # I, Q, M for absolute storage; None for an unaddressed tag
    byte: int
    bit: int | None
    width: int             # bytes for words; 0 for bits
    type: str              # Bool, Int, DInt, Real, Time, IEC_TIMER, IEC_COUNTER
    tag: str | None = None
    member: str | None = None


def parse_time(text: str) -> int | None:
    """T#1m30s, T#500ms, T#2s_500ms → milliseconds; None if it is not a time literal."""
    m = _TIME.match(text.strip())
    if not m or not any(m.groups()):
        return None
    d, h, mi, s, ms = (int(g) if g else 0 for g in m.groups())
    return (((d * 24 + h) * 60 + mi) * 60 + s) * 1000 + ms


def wrap(value: int, type_: str) -> tuple[int, bool]:
    n = RANGE.get(type_)
    if n is None:
        return value, False
    lo, hi = -(1 << (n - 1)), (1 << (n - 1)) - 1
    if lo <= value <= hi:
        return value, False
    return ((value - lo) % (1 << n)) + lo, True


def _absolute(text: str) -> Ref | None:
    m = _BIT.match(text.strip())
    if m:
        return Ref(m[1].upper(), int(m[2]), int(m[3]), 0, "Bool")
    m = _WORD.match(text.strip())
    if m:
        w = WIDTH[m[2].upper()]
        return Ref(m[1].upper(), int(m[3]), None, w, {1: "Int", 2: "Int", 4: "DInt"}[w])
    return None


class S7Memory:
    def __init__(self, decls: dict[str, dict] | None = None):
        self.areas = {a: bytearray(AREA_BYTES) for a in "IQM"}
        self.decls: dict[str, dict] = {}
        self.values: dict[str, object] = {}       # unaddressed tags and instances
        self._canon: dict[str, str] = {}
        for name, t in SYSTEM.items():
            self._declare(name, {"type": t})
        self.declare(decls or {})

    # -- declarations ------------------------------------------------------------
    def _declare(self, name: str, d: dict) -> None:
        t = d["type"]
        self._canon[name.lower()] = name
        self.decls[name] = d
        if t in STRUCTS:
            self.values[name] = {m: (False if mt == "Bool" else 0) for m, mt in STRUCTS[t].items()}
        elif not d.get("address"):
            v = d.get("value", 0)
            self.values[name] = bool(v) if t == "Bool" else (float(v) if t == "Real" else int(v))
        elif "value" in d:
            self._store(self._addr_ref(name, d), d["value"])

    def _addr_ref(self, name: str, d: dict) -> Ref:
        a = _absolute(d["address"])
        t = d["type"]
        if a is None:
            raise S7Error(f"tag {name}: {d['address']!r} is not an address like %M0.0 or %MW10")
        if t == "Bool" and a.bit is None:
            raise S7Error(f"tag {name}: a Bool needs a bit address like %M0.0")
        if t == "Int" and a.width != 2 or t in ("DInt", "Real", "Time") and a.width != 4:
            raise S7Error(f"tag {name}: a {t} needs {'a word (%MW)' if t == 'Int' else 'a double word (%MD)'}")
        if a.byte + max(a.width, 1) > AREA_BYTES:
            raise S7Error(f"tag {name}: {d['address']} is outside the {AREA_BYTES}-byte area")
        return Ref(a.area, a.byte, a.bit, a.width, t, name)

    def declare(self, decls: dict[str, dict]) -> None:
        for name, raw in decls.items():
            d = dict(raw)
            d["type"] = next((t for t in TYPES if t.lower() == str(d.get("type", "")).lower()), None)
            if not re.fullmatch(_NAME, name):
                raise S7Error(f"{name!r} is not a valid tag name (letters, digits and _; no leading digit)")
            if d["type"] is None:
                raise S7Error(f"tag {name}: unknown type {raw.get('type')!r} (use {', '.join(TYPES)})")
            if name.lower() in self._canon:
                raise S7Error(f"tag {name} is declared twice")
            if d["type"] in STRUCTS and d.get("address"):
                raise S7Error(f"tag {name}: {d['type']} instances have no address")
            if d.get("address"):
                self._addr_ref(name, d)
            self._declare(name, d)

    def clear(self, decls: dict[str, dict], keep_io: bool = True) -> None:
        io = (bytearray(self.areas["I"]), bytearray(self.areas["Q"]))
        self.__init__(decls)
        if keep_io:
            self.areas["I"][:], self.areas["Q"][:] = io

    # -- references ----------------------------------------------------------------
    def ref(self, text: str) -> Ref:
        a = _absolute(text)
        if a is not None:
            if a.byte + max(a.width, 1) > AREA_BYTES:
                raise S7Error(f"{text}: outside the {AREA_BYTES}-byte {a.area} area")
            return a
        m = _SYM.match(text.strip())
        if not m:
            raise S7Error(f"{text!r} is not an address or a tag")
        name = self._canon.get(m[1].lower())
        if name is None:
            raise S7Error(f"tag {m[1]} does not exist")
        d = self.decls[name]
        t = d["type"]
        if m[2]:
            if t not in STRUCTS:
                raise S7Error(f"{name} is a {t}; it has no member {m[2]}")
            member = next((k for k in STRUCTS[t] if k.lower() == m[2].lower()), None)
            if member is None:
                raise S7Error(f"{name} has no member {m[2]} (has {', '.join(STRUCTS[t])})")
            return Ref(None, 0, None, 0, STRUCTS[t][member], name, member)
        if d.get("address"):
            return self._addr_ref(name, d)
        return Ref(None, 0, None, 0, t, name)

    # -- raw access -------------------------------------------------------------------
    def _load(self, r: Ref):
        if r.area is None:
            v = self.values[r.tag]
            return v[r.member] if r.member else v
        buf = self.areas[r.area]
        if r.bit is not None:
            return bool((buf[r.byte] >> r.bit) & 1)
        raw = bytes(buf[r.byte:r.byte + r.width])
        if r.type == "Real":
            return struct.unpack(">f", raw)[0]
        return int.from_bytes(raw, "big", signed=r.width > 1)

    def _store(self, r: Ref, value) -> bool:
        over = False
        if r.type == "Bool":
            value = bool(value)
        elif r.type == "Real":
            value = float(value)
        else:
            value, over = wrap(int(round(value)) if isinstance(value, float) else int(value), r.type)
        if r.area is None:
            if r.member:
                self.values[r.tag][r.member] = value
            else:
                self.values[r.tag] = value
            return over
        buf = self.areas[r.area]
        if r.bit is not None:
            buf[r.byte] = (buf[r.byte] | (1 << r.bit)) if value else (buf[r.byte] & ~(1 << r.bit))
        elif r.type == "Real":
            buf[r.byte:r.byte + 4] = struct.pack(">f", value)
        else:
            if r.width == 1:
                value &= 0xFF
            buf[r.byte:r.byte + r.width] = (value & ((1 << (8 * r.width)) - 1)).to_bytes(r.width, "big")
        return over

    # -- the interface instructions and the UI use ---------------------------------
    def read_bit(self, text: str) -> bool:
        r = self.ref(text)
        if r.type != "Bool":
            raise S7Error(f"{text} is a {r.type}, not a Bool")
        return bool(self._load(r))

    def write_bit(self, text: str, on: bool) -> None:
        r = self.ref(text)
        if r.type != "Bool":
            raise S7Error(f"{text} is a {r.type}, not a Bool")
        self._store(r, on)

    def read_word(self, text: str):
        r = self.ref(text)
        if r.type in STRUCTS:
            raise S7Error(f"{text} is an {r.type}; use a member like {text}.Q")
        v = self._load(r)
        return int(v) if r.type == "Bool" else v

    def write_word(self, text: str, value) -> bool:
        """Store a number converted to the destination type; True on integer overflow."""
        r = self.ref(text)
        if r.type in STRUCTS:
            raise S7Error(f"{text} is an {r.type}")
        return self._store(r, value)

    def element(self, text: str) -> dict:
        r = self.ref(text)
        if r.type not in STRUCTS or r.member:
            raise S7Error(f"{text} is not an IEC_TIMER or IEC_COUNTER instance")
        return self.values[r.tag]

    def type_of(self, text: str) -> str:
        return self.ref(text).type

    def names(self) -> list[str]:
        return [n for n in self.decls if n not in SYSTEM]

    # -- I/O image: big-endian words, slot word = two bytes ----------------------------
    def word(self, area: str, byte: int) -> int:
        return int.from_bytes(self.areas[area][byte:byte + 2], "big")

    def set_word(self, area: str, byte: int, value: int) -> None:
        self.areas[area][byte:byte + 2] = (value & 0xFFFF).to_bytes(2, "big")
