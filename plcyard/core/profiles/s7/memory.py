"""S7-1200/1500 memory (TIA Portal style): byte-addressed areas I, Q and M, symbolic PLC tags,
and instances of IEC timers and counters.

Absolute: `%I0.0`, `%Q1.7`, `%M10.3` (bits), `%IB0`, `%MW10` (Int), `%MD20` (DInt). Words are big
endian, as on the real controller: %IW0 is %IB0 (high byte) then %IB1. Symbolic: `Motor` or
`"Motor"`, `MyTimer.Q`, `MyTimer.ET`, `Count.%X3`. Data blocks are tags of a PLC data type or of a
function block (its instance DB): `"Recipe".Speed`, `"Line"[2].Run`, arrays `Array[1..5] of Int`.
`FirstScan` is true on the first scan after RUN.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from ..datatypes import NAME, DataTypeError, TypeSystem, get, put, resolve, split

AREA_BYTES = 128
TYPES = ("Bool", "Int", "DInt", "Real", "Time", "IEC_TIMER", "IEC_COUNTER", "PID_Compact")
ATOMIC = {"Bool": False, "Byte": 0, "Int": 0, "DInt": 0, "Real": 0.0, "Time": 0}
STRUCTS = {
    "IEC_TIMER": {"PT": "Time", "ET": "Time", "IN": "Bool", "Q": "Bool"},
    "IEC_COUNTER": {"PV": "Int", "CV": "Int", "CU": "Bool", "CD": "Bool", "R": "Bool", "LD": "Bool",
                    "Q": "Bool", "QU": "Bool", "QD": "Bool"},
    # simplified PID_Compact: Gain, Ti/Td in seconds, output limits in %, manual mode, inverted action
    "PID_Compact": {"Gain": "Real", "Ti": "Real", "Td": "Real", "OutputUpperLimit": "Real",
                    "OutputLowerLimit": "Real", "ManualEnable": "Bool", "ManualValue": "Real",
                    "InvertControl": "Bool", "Setpoint": "Real", "Input": "Real", "Output": "Real"},
}
STRUCT_START = {"PID_Compact": {"Gain": 1.0, "OutputUpperLimit": 100.0}}
ANALOG_IN = {0: 64, 1: 66}          # channel → %IW byte
ANALOG_OUT = {0: 64}                # channel → %QW byte
FULL_SCALE = 27648                  # 10 V
WIDTH = {"B": 1, "W": 2, "D": 4}
RANGE = {"Byte": 8, "Int": 16, "DInt": 32, "Time": 32}
BITS = {"Byte": 8, "Int": 16, "DInt": 32}
SYSTEM = {"FirstScan": "Bool"}

_NAME = NAME
_BIT = re.compile(r"^%?([IQM])(\d+)\.([0-7])$", re.I)
_WORD = re.compile(r"^%?([IQM])([BWD])(\d+)$", re.I)
_SYM = re.compile(rf'^#?"?({_NAME})"?(?:\.(?:{_NAME}|%X\d+|\d+)|\[[^\]]+\])*$')
_BASE = re.compile(rf'#?"?({_NAME})"?')
_ARRAY = re.compile(rf"^Array\s*\[\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\]\s+of\s+({_NAME})$", re.I)
_TIME = re.compile(r"^T#(?:(\d+)D_?)?(?:(\d+)H_?)?(?:(\d+)M(?!S)_?)?(?:(\d+)S_?)?(?:(\d+)MS)?$", re.I)


class S7Error(Exception):
    pass


@dataclass(frozen=True)
class Ref:
    area: str | None       # I, Q, M for absolute storage; None for an unaddressed tag
    byte: int
    bit: int | None
    width: int             # bytes for words; 0 for bits
    type: str              # Bool, Int, DInt, Real, Time, a structure or an array
    tag: str | None = None
    path: tuple = ()       # members and array offsets below an unaddressed tag
    word: str = ""         # type of the value holding a bit of a symbolic Int (Count.%X3)


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
    if type_ == "Byte":
        return value & 0xFF, not 0 <= value <= 0xFF
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


def _parse_array(text: str):
    m = _ARRAY.match(text.strip())
    if not m or int(m[1]) > int(m[2]):
        return None
    return m[3], int(m[1]), int(m[2])


def type_system(structs: dict[str, dict[str, str]] | None = None, kinds: dict[str, str] | None = None) -> TypeSystem:
    """S7 types plus PLC data types and function block interfaces ({name: {member: type}});
    `kinds` names what each one is in messages ("PLC data type", "function block")."""
    structs = structs or {}
    kinds = kinds or {}
    for name in structs:
        if not re.fullmatch(_NAME, name):
            raise S7Error(f"{name!r} is not a valid {kinds.get(name, 'data type')} name")
        if name.lower() in {t.lower() for t in [*ATOMIC, *STRUCTS]}:
            raise S7Error(f"{kinds.get(name, 'data type')} {name}: {name} is a built-in type")
    lower = [n.lower() for n in structs]
    if len(set(lower)) != len(lower):
        raise S7Error("two data types or blocks have the same name")
    fmt = lambda e, lo, hi: f"Array[{lo}..{hi}] of {e}"
    base = TypeSystem(ATOMIC, {**STRUCTS, **{n: {} for n in structs}}, _parse_array, fmt, STRUCT_START)
    canon = {n: {m: (base.canon(t) or t) for m, t in ms.items()} for n, ms in structs.items()}
    ts = TypeSystem(ATOMIC, {**STRUCTS, **canon}, _parse_array, fmt, STRUCT_START)
    try:
        ts.check_structs(canon)
    except DataTypeError as e:
        raise S7Error(str(e)) from None
    return ts


class S7Memory:
    def __init__(self, decls: dict[str, dict] | None = None, structs: dict[str, dict[str, str]] | None = None,
                 kinds: dict[str, str] | None = None):
        self.ts = type_system(structs, kinds)
        self._structs, self._kinds = dict(structs or {}), dict(kinds or {})
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
        if d.get("address"):
            if "value" in d:
                self._store(self._addr_ref(name, d), d["value"])
            return
        try:
            self.values[name] = self.ts.coerce(t, d["value"]) if "value" in d else self.ts.default(t)
        except (DataTypeError, ValueError, TypeError) as e:
            raise S7Error(f"tag {name}: {e}") from None

    def _addr_ref(self, name: str, d: dict) -> Ref:
        a = _absolute(d["address"])
        t = d["type"]
        if a is None:
            raise S7Error(f"tag {name}: {d['address']!r} is not an address like %M0.0 or %MW10")
        if t == "Bool" and a.bit is None:
            raise S7Error(f"tag {name}: a Bool needs a bit address like %M0.0")
        if t == "Byte" and a.width != 1 or t == "Int" and a.width != 2 or t in ("DInt", "Real", "Time") and a.width != 4:
            want = {"Byte": "a byte (%MB)", "Int": "a word (%MW)"}.get(t, "a double word (%MD)")
            raise S7Error(f"tag {name}: a {t} needs {want}")
        if a.byte + max(a.width, 1) > AREA_BYTES:
            raise S7Error(f"tag {name}: {d['address']} is outside the {AREA_BYTES}-byte area")
        return Ref(a.area, a.byte, a.bit, a.width, t, name)

    def declare(self, decls: dict[str, dict]) -> None:
        for name, raw in decls.items():
            d = dict(raw)
            d["type"] = self.ts.canon(str(d.get("type", "")))
            if not re.fullmatch(_NAME, name):
                raise S7Error(f"{name!r} is not a valid tag name (letters, digits and _; no leading digit)")
            if d["type"] is None:
                extra = [n for n, k in self._kinds.items() if k != "function"]
                raise S7Error(f"tag {name}: unknown type {raw.get('type')!r} (use {', '.join([*TYPES, *extra])}, "
                              "or an array like Array[0..9] of Int)")
            if name.lower() in self._canon:
                raise S7Error(f"tag {name} is declared twice")
            arr = self.ts.array(d["type"])
            if arr and arr.size > 10_000:
                raise S7Error(f"tag {name}: arrays hold at most 10000 elements")
            if not self.ts.is_scalar(d["type"]) and d.get("address"):
                raise S7Error(f"tag {name}: {d['type']} values have no address (they live in a data block)")
            if d.get("address"):
                self._addr_ref(name, d)
            self._declare(name, d)

    def clear(self, decls: dict[str, dict], keep_io: bool = True) -> None:
        io = (bytearray(self.areas["I"]), bytearray(self.areas["Q"]))
        self.__init__(decls, self._structs, self._kinds)
        if keep_io:
            self.areas["I"][:], self.areas["Q"][:] = io

    # -- references ----------------------------------------------------------------
    def ref(self, text: str, static: bool = False) -> Ref:
        a = _absolute(text)
        if a is not None:
            if a.byte + max(a.width, 1) > AREA_BYTES:
                raise S7Error(f"{text}: outside the {AREA_BYTES}-byte {a.area} area")
            return a
        parts = split(text, _BASE) if _SYM.match(text.strip()) else None
        if parts is None:
            raise S7Error(f"{text!r} is not an address or a tag")
        base_text, steps = parts
        name = self._canon.get(base_text.lower())
        if name is None:
            raise S7Error(f"tag {base_text} does not exist")
        d = self.decls[name]
        t = d["type"]
        if not steps and d.get("address"):
            return self._addr_ref(name, d)
        if d.get("address"):
            if steps[0][0] == "b" and t in BITS and len(steps) == 1:
                r = self._addr_ref(name, d)
                if steps[0][1] >= BITS[t]:
                    raise S7Error(f"{text}: bit {steps[0][1]} out of range (0-{BITS[t] - 1})")
                bit = steps[0][1]                      # big endian: bit 0 is in the last byte
                return Ref(r.area, r.byte + r.width - 1 - bit // 8, bit % 8, 0, "Bool", name)
            raise S7Error(f"{name} is a {t}; it has no member {steps[0][1]}")

        def index(arg: str):
            if re.fullmatch(r"-?\d+", arg):
                return int(arg)
            if arg == "*":                               # computed in structured text
                return None
            r = self.ref(arg, static)
            if r.type not in ("Int", "DInt", "Byte"):
                raise S7Error(f"{text}: the index {arg} must be an Int or DInt")
            return None if static else int(self._load(r))

        path, bit, word = resolve(self.ts, t, steps, index, text, BITS, S7Error)
        return Ref(None, 0, bit, 0, "Bool" if bit is not None else word, name, path, word)

    # -- raw access -------------------------------------------------------------------
    def _load(self, r: Ref):
        if r.area is None:
            v = get(self.values[r.tag], r.path)
            return bool((int(v) >> r.bit) & 1) if r.bit is not None else v
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
            if r.bit is not None:
                old = int(get(self.values[r.tag], r.path)) & ((1 << BITS[r.word]) - 1)
                value = wrap(old | (1 << r.bit) if value else old & ~(1 << r.bit), r.word)[0]
            if r.path:
                put(self.values[r.tag], r.path, value)
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

    def is_scalar(self, t: str) -> bool:
        return self.ts.is_scalar(t)

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
        if not self.is_scalar(r.type):
            raise S7Error(f"{text} is a {r.type}; use a member or an element")
        v = self._load(r)
        return int(v) if r.type == "Bool" else v

    def write_word(self, text: str, value) -> bool:
        """Store a number converted to the destination type; True on integer overflow."""
        r = self.ref(text)
        if not self.is_scalar(r.type):
            raise S7Error(f"{text} is a {r.type}; use a member or an element")
        return self._store(r, value)

    def element(self, text: str) -> dict:
        r = self.ref(text)
        if r.type not in STRUCTS:
            raise S7Error(f"{text} is not an IEC_TIMER, IEC_COUNTER or PID_Compact instance")
        return get(self.values[r.tag], r.path)

    def struct(self, text: str) -> dict:
        """The member dict of any structure (a data block, an FB instance, an element)."""
        r = self.ref(text)
        if not self.ts.is_struct(r.type):
            raise S7Error(f"{text} is not a structure")
        return get(self.values[r.tag], r.path)

    def type_of(self, text: str) -> str:
        return self.ref(text).type

    def names(self) -> list[str]:
        return [n for n in self.decls if n not in SYSTEM and not n.startswith("__")]

    def walk(self, name: str):
        """(reference, type, value) for a tag and everything inside it."""
        if self.decls[name].get("address"):
            return iter([(name, self.decls[name]["type"], self.read_word(name))])
        return self.ts.walk(self.values[name], self.decls[name]["type"], name)

    # -- I/O image: big-endian words, slot word = two bytes ----------------------------
    def word(self, area: str, byte: int) -> int:
        return int.from_bytes(self.areas[area][byte:byte + 2], "big")

    def set_word(self, area: str, byte: int, value: int) -> None:
        self.areas[area][byte:byte + 2] = (value & 0xFFFF).to_bytes(2, "big")
