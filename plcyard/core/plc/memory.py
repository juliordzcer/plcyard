"""PLC memory: byte-addressed I/O and marker areas, named tags of any type, function block instances.

Canonical references (what program files store):
  %I0.0  %Q1.7  %M10.3 bits, %IB0 / %IW0 / %ID0 bytes, words (INT) and double words (DINT) —
  words are big endian: %IW0 is %IB0 (high byte) then %IB1;
  Motor, Delay.DN, Recipe[2].Speed, Count.3 (bit of an integer), FirstScan, Overflow.
Accepted as well (the other notation, converted on the way in):
  Local:1:I.Data.0 (module slot and point), Local:7:I.Ch0Data (analog channel), Delay.Q / Delay.ET /
  Delay.PT (timer members by their IEC names), "Motor" and #Motor (quoted global, block local),
  S:FS and S:V (first scan, overflow).
Analog channels are raw counts 0-27648 = 0-10 V.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from ..profiles.datatypes import NAME, DataTypeError, TypeSystem, get, put, resolve, split

AREA_BYTES = 128
TYPES = ("BOOL", "SINT", "INT", "DINT", "REAL", "TIME", "TIMER", "COUNTER", "CONTROL", "PID")
ATOMIC = {"BOOL": False, "SINT": 0, "INT": 0, "DINT": 0, "REAL": 0.0, "TIME": 0}
STRUCTS = {
    "TIMER": {"PRE": "DINT", "ACC": "DINT", "EN": "BOOL", "TT": "BOOL", "DN": "BOOL"},
    "COUNTER": {"PRE": "DINT", "ACC": "DINT", "CU": "BOOL", "CD": "BOOL", "DN": "BOOL",
                "OV": "BOOL", "UN": "BOOL"},
    "CONTROL": {"LEN": "DINT", "POS": "DINT", "EN": "BOOL", "EU": "BOOL", "DN": "BOOL", "EM": "BOOL",
                "ER": "BOOL", "UL": "BOOL", "IN": "BOOL", "FD": "BOOL"},
    # PID: gain KP, integral time TI and derivative time TD in seconds (dependent form), output CV in %,
    # MO manual mode with output SO, CA reverse acting (E = PV - SP), output limits MINO..MAXO
    "PID": {"SP": "REAL", "PV": "REAL", "CV": "REAL", "KP": "REAL", "TI": "REAL", "TD": "REAL",
            "MAXO": "REAL", "MINO": "REAL", "SO": "REAL", "MO": "BOOL", "CA": "BOOL"},
}
START = {"PID": {"MAXO": 100.0, "KP": 1.0}}
ALIASES = {"TIMER": {"PT": "PRE", "ET": "ACC", "Q": "DN", "IN": "EN"},
           "COUNTER": {"PV": "PRE", "CV": "ACC", "Q": "DN", "QU": "DN"}}
SYSTEM = {"FirstScan": "BOOL", "Overflow": "BOOL"}
SYSTEM_ALIASES = {"s:fs": "FirstScan", "s:v": "Overflow"}
WIDTH = {"B": 1, "W": 2, "D": 4}
RANGE = {"SINT": 8, "INT": 16, "DINT": 32, "TIME": 32}
BITS = {"SINT": 8, "INT": 16, "DINT": 32}
FULL_SCALE = 27648                  # analog counts at 10 V

# the simulated rack: module slot → first byte of its 16 points
INPUT_SLOTS = {1: 0, 3: 2, 5: 4}
OUTPUT_SLOTS = {2: 0, 4: 2, 6: 4}
WORD_SLOTS = (5, 6)                 # whole words (BCD thumbwheels and display), not 16 points
ANALOG_IN = {0: 64, 1: 66}          # channel → %IW byte (module slot 7)
ANALOG_OUT = {0: 64}                # channel → %QW byte (module slot 8)
ANALOG_IN_SLOT, ANALOG_OUT_SLOT = 7, 8

_BIT = re.compile(r"^%?([IQM])(\d+)\.([0-7])$", re.I)
_WORD = re.compile(r"^%?([IQM])([BWD])(\d+)$", re.I)
_MODULE = re.compile(r"^Local:(\d+):([IO])\.(?:Data(?:\.(\d+))?|Ch(\d)Data)$", re.I)
_SYM = re.compile(rf'^#?"?(S:FS|S:V|{NAME})"?(?:\.(?:{NAME}|%X\d+|\d+)|\[.+?\]+)*$', re.I)
_BASE = re.compile(rf'#?"?(S:FS|S:V|{NAME})"?', re.I)
_ARRAY = re.compile(rf"^({NAME})\s*\[\s*(\d+)\s*\]$")
_ARRAY_IEC = re.compile(rf"^Array\s*\[\s*(-?\d+)\s*\.\.\s*(-?\d+)\s*\]\s+of\s+({NAME})$", re.I)
_TIME = re.compile(r"^T#(?:(\d+)D_?)?(?:(\d+)H_?)?(?:(\d+)M(?!S)_?)?(?:(\d+)S_?)?(?:(\d+)MS)?$", re.I)


class PlcMemoryError(Exception):
    pass


@dataclass(frozen=True)
class Ref:
    area: str | None       # I, Q, M for absolute storage; None for a tag
    byte: int
    bit: int | None
    width: int             # bytes for words; 0 for bits
    type: str
    tag: str | None = None
    path: tuple = ()       # members and array offsets below a tag
    word: str = ""         # type of the value that holds a bit (Count.3)


def parse_time(text: str) -> int | None:
    """T#1m30s, T#500ms, T#2s_500ms → milliseconds; None if it is not a time literal."""
    m = _TIME.match(text.strip())
    if not m or not any(m.groups()):
        return None
    d, h, mi, s, ms = (int(g) if g else 0 for g in m.groups())
    return (((d * 24 + h) * 60 + mi) * 60 + s) * 1000 + ms


def wrap(value: int, type_: str) -> tuple[int, bool]:
    """Two's-complement wrap to the type's width; second value says whether it overflowed."""
    n = RANGE.get(type_)
    if n is None:
        return value, False
    lo, hi = -(1 << (n - 1)), (1 << (n - 1)) - 1
    if lo <= value <= hi:
        return value, False
    return ((value - lo) % (1 << n)) + lo, True


def module_to_absolute(text: str) -> str | None:
    """Local:1:I.Data.0 → %I0.0, Local:3:I.Data.9 → %I3.1, Local:2:O.Data → %QW0,
    Local:7:I.Ch0Data → %IW64. None when it is not a module reference."""
    m = _MODULE.match(text.strip())
    if not m:
        return None
    slot, d, point, ch = int(m[1]), m[2].upper(), m[3], m[4]
    area = "I" if d == "I" else "Q"
    if ch is not None:
        table = ANALOG_IN if d == "I" else ANALOG_OUT
        if slot != (ANALOG_IN_SLOT if d == "I" else ANALOG_OUT_SLOT) or int(ch) not in table:
            return None
        return f"%{area}W{table[int(ch)]}"
    base = (INPUT_SLOTS if d == "I" else OUTPUT_SLOTS).get(slot)
    if base is None:
        return None
    if point is None:
        return f"%{area}W{base}"
    p = int(point)
    if p > 15 or slot in WORD_SLOTS:
        return None
    return f"%{area}{base + p // 8}.{p % 8}"


def absolute_to_module(text: str) -> str | None:
    """The other way: %I0.0 → Local:1:I.Data.0 (None for %M and addresses with no module)."""
    m = _BIT.match(text.strip())
    if m and m[1].upper() in "IQ":
        area, byte, bit = m[1].upper(), int(m[2]), int(m[3])
        slots = INPUT_SLOTS if area == "I" else OUTPUT_SLOTS
        for slot, base in slots.items():
            if slot not in WORD_SLOTS and base <= byte < base + 2:
                return f"Local:{slot}:{'I' if area == 'I' else 'O'}.Data.{(byte - base) * 8 + bit}"
        return None
    m = _WORD.match(text.strip())
    if m and m[1].upper() in "IQ" and m[2].upper() == "W":
        area, byte = m[1].upper(), int(m[3])
        d = "I" if area == "I" else "O"
        analog = ANALOG_IN if area == "I" else ANALOG_OUT
        ch = next((c for c, b in analog.items() if b == byte), None)
        if ch is not None:
            return f"Local:{ANALOG_IN_SLOT if area == 'I' else ANALOG_OUT_SLOT}:{d}.Ch{ch}Data"
        slot = next((s for s, b in (INPUT_SLOTS if area == "I" else OUTPUT_SLOTS).items() if b == byte), None)
        return f"Local:{slot}:{d}.Data" if slot is not None else None
    return None


def _absolute(text: str) -> Ref | None:
    text = module_to_absolute(text) or text
    m = _BIT.match(text.strip())
    if m:
        return Ref(m[1].upper(), int(m[2]), int(m[3]), 0, "BOOL")
    m = _WORD.match(text.strip())
    if m:
        w = WIDTH[m[2].upper()]
        return Ref(m[1].upper(), int(m[3]), None, w, {1: "SINT", 2: "INT", 4: "DINT"}[w])
    return None


def _parse_array(text: str):
    t = text.strip()
    m = _ARRAY.match(t)
    if m:
        n = int(m[2])
        return (m[1], 0, n - 1) if n > 0 else None
    m = _ARRAY_IEC.match(t)
    if m and int(m[1]) <= int(m[2]):
        return m[3], int(m[1]), int(m[2])
    return None


def _format_array(elem: str, lo: int, hi: int) -> str:
    return f"{elem}[{hi + 1}]" if lo == 0 else f"Array[{lo}..{hi}] of {elem}"


def type_system(structs: dict[str, dict[str, str]] | None = None, kinds: dict[str, str] | None = None) -> TypeSystem:
    """Built-in types plus data types and function block interfaces ({name: {member: type}});
    `kinds` names what each one is in messages ("data type", "function block", "function")."""
    structs = structs or {}
    kinds = kinds or {}
    for name in structs:
        if not re.fullmatch(NAME, name):
            raise PlcMemoryError(f"{name!r} is not a valid {kinds.get(name, 'data type')} name")
        if name.upper() in {*ATOMIC, *STRUCTS}:
            raise PlcMemoryError(f"{kinds.get(name, 'data type')} {name}: {name.upper()} is a built-in type")
    lower = [n.lower() for n in structs]
    if len(set(lower)) != len(lower):
        raise PlcMemoryError("two data types or blocks have the same name")
    base = TypeSystem(ATOMIC, {**STRUCTS, **{n: {} for n in structs}}, _parse_array, _format_array, START, ALIASES)
    canon = {n: {m: (base.canon(t) or t) for m, t in ms.items()} for n, ms in structs.items()}
    ts = TypeSystem(ATOMIC, {**STRUCTS, **canon}, _parse_array, _format_array, START, ALIASES)
    try:
        ts.check_structs(canon)
    except DataTypeError as e:
        raise PlcMemoryError(str(e)) from None
    return ts


class Memory:
    def __init__(self, decls: dict[str, dict] | None = None, structs: dict[str, dict[str, str]] | None = None,
                 kinds: dict[str, str] | None = None):
        self.ts = type_system(structs, kinds)
        self._structs, self._kinds = dict(structs or {}), dict(kinds or {})
        self.areas = {a: bytearray(AREA_BYTES) for a in "IQM"}
        self.decls: dict[str, dict] = {}
        self.values: dict[str, object] = {}       # tags without an address, and instances
        self._canon: dict[str, str] = {}
        self._refs: dict[str, Ref] = {}           # resolved references without a computed index
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
            raise PlcMemoryError(f"tag {name}: {e}") from None

    def _addr_ref(self, name: str, d: dict) -> Ref:
        a = _absolute(d["address"])
        t = d["type"]
        if a is None:
            raise PlcMemoryError(f"tag {name}: {d['address']!r} is not an address like %M0.0 or %MW10")
        if t == "BOOL" and a.bit is None:
            raise PlcMemoryError(f"tag {name}: a BOOL needs a bit address like %M0.0")
        if t == "SINT" and a.width != 1 or t == "INT" and a.width != 2 or t in ("DINT", "REAL", "TIME") and a.width != 4:
            want = {"SINT": "a byte (%MB)", "INT": "a word (%MW)"}.get(t, "a double word (%MD)")
            raise PlcMemoryError(f"tag {name}: a {t} needs {want}")
        if a.byte + max(a.width, 1) > AREA_BYTES:
            raise PlcMemoryError(f"tag {name}: {d['address']} is outside the {AREA_BYTES}-byte area")
        return Ref(a.area, a.byte, a.bit, a.width, t, name)

    def declare(self, decls: dict[str, dict]) -> None:
        for name, raw in decls.items():
            d = dict(raw)
            d["type"] = self.ts.canon(str(d.get("type", "")))
            if not re.fullmatch(NAME, name):
                raise PlcMemoryError(f"{name!r} is not a valid tag name (letters, digits and _; no leading digit)")
            if d["type"] is None:
                extra = [n for n, k in self._kinds.items() if k != "function"]
                raise PlcMemoryError(f"tag {name}: unknown type {raw.get('type')!r} (use {', '.join([*TYPES, *extra])}, "
                                   "or an array like DINT[10])")
            if name.lower() in self._canon:
                raise PlcMemoryError(f"tag {name} is declared twice")
            arr = self.ts.array(d["type"])
            if arr and arr.size > 10_000:
                raise PlcMemoryError(f"tag {name}: arrays hold at most 10000 elements")
            if not self.ts.is_scalar(d["type"]) and d.get("address"):
                raise PlcMemoryError(f"tag {name}: {d['type']} values have no address")
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
        hit = self._refs.get(text)
        if hit is not None:
            return hit
        r = self._resolve(text, static)
        if not static and "[" not in text or not static and re.fullmatch(r"[^\[]*(\[\d+\][^\[]*)*", text):
            self._refs[text] = r
        return r

    def _resolve(self, text: str, static: bool) -> Ref:
        a = _absolute(text)
        if a is not None:
            if a.byte + max(a.width, 1) > AREA_BYTES:
                raise PlcMemoryError(f"{text}: outside the {AREA_BYTES}-byte {a.area} area")
            return a
        if _MODULE.match(text.strip()):
            raise PlcMemoryError(f"{text}: there is no such module point")
        parts = split(text, _BASE) if _SYM.match(text.strip()) else None
        if parts is None:
            raise PlcMemoryError(f"{text!r} is not an address or a tag")
        base_text, steps = parts
        name = self._canon.get(base_text.lower()) or SYSTEM_ALIASES.get(base_text.lower())
        if name is None:
            raise PlcMemoryError(f"tag {base_text} does not exist")
        d = self.decls[name]
        t = d["type"]
        if not steps and d.get("address"):
            return self._addr_ref(name, d)
        if d.get("address"):
            if steps[0][0] == "b" and t in BITS and len(steps) == 1:
                r = self._addr_ref(name, d)
                if steps[0][1] >= BITS[t]:
                    raise PlcMemoryError(f"{text}: bit {steps[0][1]} out of range (0-{BITS[t] - 1})")
                bit = steps[0][1]                      # big endian: bit 0 is in the last byte
                return Ref(r.area, r.byte + r.width - 1 - bit // 8, bit % 8, 0, "BOOL", name)
            raise PlcMemoryError(f"{name} is a {t}; it has no member {steps[0][1]}")

        def index(arg: str):
            if re.fullmatch(r"-?\d+", arg):
                return int(arg)
            if arg == "*":                               # computed in structured text
                return None
            r = self.ref(arg, static)
            if r.type not in BITS:
                raise PlcMemoryError(f"{text}: the index {arg} must be a SINT, INT or DINT")
            return None if static else int(self._load(r))

        path, bit, word = resolve(self.ts, t, steps, index, text, BITS, PlcMemoryError)
        return Ref(None, 0, bit, 0, "BOOL" if bit is not None else word, name, path, word)

    # -- raw access -------------------------------------------------------------------
    def _load(self, r: Ref):
        if r.area is None:
            v = get(self.values[r.tag], r.path)
            return bool((int(v) >> r.bit) & 1) if r.bit is not None else v
        buf = self.areas[r.area]
        if r.bit is not None:
            return bool((buf[r.byte] >> r.bit) & 1)
        raw = bytes(buf[r.byte:r.byte + r.width])
        if r.type == "REAL":
            return struct.unpack(">f", raw)[0]
        return int.from_bytes(raw, "big", signed=True)

    def _store(self, r: Ref, value) -> bool:
        over = False
        if r.type == "BOOL":
            value = bool(value)
        elif r.type == "REAL":
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
        elif r.type == "REAL":
            buf[r.byte:r.byte + 4] = struct.pack(">f", value)
        else:
            buf[r.byte:r.byte + r.width] = (value & ((1 << (8 * r.width)) - 1)).to_bytes(r.width, "big")
        return over

    def is_scalar(self, t: str) -> bool:
        return self.ts.is_scalar(t)

    # -- the interface instructions and the UI use ---------------------------------
    def read_bit(self, text: str) -> bool:
        r = self.ref(text)
        if r.type != "BOOL":
            raise PlcMemoryError(f"{text} is a {r.type}, not a BOOL")
        return bool(self._load(r))

    def write_bit(self, text: str, on: bool) -> None:
        r = self.ref(text)
        if r.type != "BOOL":
            raise PlcMemoryError(f"{text} is a {r.type}, not a BOOL")
        self._store(r, on)

    def read_word(self, text: str):
        r = self.ref(text)
        if not self.is_scalar(r.type):
            raise PlcMemoryError(f"{text} is a {r.type}; use a member or an element")
        v = self._load(r)
        return int(v) if r.type == "BOOL" else v

    def write_word(self, text: str, value) -> bool:
        """Store a number converted to the destination type; True on integer overflow."""
        r = self.ref(text)
        if not self.is_scalar(r.type):
            raise PlcMemoryError(f"{text} is a {r.type}; use a member or an element")
        return self._store(r, value)

    def element(self, text: str) -> dict:
        """The member dict of a TIMER, COUNTER, CONTROL or PID."""
        r = self.ref(text)
        if r.type not in STRUCTS:
            raise PlcMemoryError(f"{text} is not a TIMER, COUNTER, CONTROL or PID")
        return get(self.values[r.tag], r.path)

    def struct(self, text: str) -> dict:
        """The member dict of any structure (a data type, a block instance, an element)."""
        r = self.ref(text)
        if not self.ts.is_struct(r.type):
            raise PlcMemoryError(f"{text} is not a structure")
        return get(self.values[r.tag], r.path)

    def array(self, text: str) -> tuple[list, int, str]:
        """(list, offset of the referenced element, element type) for an array element like N7[3]."""
        parts = split(text, _BASE)
        if not parts or not parts[1] or parts[1][-1][0] != "i":
            raise PlcMemoryError(f"{text} is not an array element like Data[0]")
        r = self.ref(text)
        if r.area is not None or r.bit is not None:
            raise PlcMemoryError(f"{text} is not an array element like Data[0]")
        parent = get(self.values[r.tag], r.path[:-1])
        return parent, r.path[-1], r.type

    def type_of(self, text: str) -> str:
        return self.ref(text).type

    def names(self) -> list[str]:
        return [n for n in self.decls if n not in SYSTEM and not n.startswith("__")]

    def walk(self, name: str):
        """(reference, type, value) for a tag and everything inside it."""
        if self.decls[name].get("address"):
            return iter([(name, self.decls[name]["type"], self.read_word(name))])
        return self.ts.walk(self.values[name], self.decls[name]["type"], name)

    # -- I/O image: big-endian words ------------------------------------------------------
    def word(self, area: str, byte: int) -> int:
        return int.from_bytes(self.areas[area][byte:byte + 2], "big")

    def set_word(self, area: str, byte: int, value: int) -> None:
        self.areas[area][byte:byte + 2] = (value & 0xFFFF).to_bytes(2, "big")
