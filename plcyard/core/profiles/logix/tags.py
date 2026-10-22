"""Logix tag memory (Studio 5000 style): named, typed tags instead of a file data table.

References: `Start`, `Count.ACC`, `Timer1.DN`, `Flags.3` (bit of an integer), arrays `Recipe[2]`,
`Recipe[Step]`, user-defined types `Pump.Speed`, `Line[1].Motor.Run`, module tags
`Local:1:I.Data.0`, system flags `S:FS` (first scan) and `S:V` (overflow). Names are
case-insensitive, as in Studio 5000.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..datatypes import NAME as _NAME, DataTypeError, TypeSystem, get, put, resolve, split

TYPES = ("BOOL", "SINT", "INT", "DINT", "REAL", "TIMER", "COUNTER", "PID")
ATOMIC = {"BOOL": False, "SINT": 0, "INT": 0, "DINT": 0, "REAL": 0.0}
STRUCTS = {
    "TIMER": {"PRE": "DINT", "ACC": "DINT", "EN": "BOOL", "TT": "BOOL", "DN": "BOOL"},
    "COUNTER": {"PRE": "DINT", "ACC": "DINT", "CU": "BOOL", "CD": "BOOL", "DN": "BOOL",
                "OV": "BOOL", "UN": "BOOL"},
    # simplified PID (dependent gains): KP gain, TI/TD in seconds, CV in %, MO manual, SO manual output,
    # CA reverse acting (cooling)
    "PID": {"SP": "REAL", "PV": "REAL", "CV": "REAL", "KP": "REAL", "TI": "REAL", "TD": "REAL",
            "MAXO": "REAL", "MINO": "REAL", "SO": "REAL", "MO": "BOOL", "CA": "BOOL"},
}
START = {"PID": {"MAXO": 100.0, "KP": 1.0}}
MODULES = {  # module tag members: digital 16 points as a DINT, analog channels in volts
    "MODULE": {"DATA": "DINT"},
    "AI": {"CH0DATA": "REAL", "CH1DATA": "REAL"},
    "AO": {"CH0DATA": "REAL"},
}
ANALOG_IN_SLOT, ANALOG_OUT_SLOT = 7, 8
BITS = {"SINT": 8, "INT": 16, "DINT": 32}
INPUT_SLOTS, OUTPUT_SLOTS = (1, 3, 5), (2, 4, 6)
SYSTEM = {"S:FS": "BOOL", "S:V": "BOOL"}

_BASE = re.compile(rf'#?"?(Local:\d+:[IO]|S:FS|S:V|{_NAME})"?', re.I)
_REF = re.compile(rf"^(?:Local:\d+:[IO]|S:FS|S:V|{_NAME})(?:\.\w+|\[[^\]]+\])*$", re.I)   # shape only
_ARRAY = re.compile(rf"^({_NAME})\s*\[\s*(\d+)\s*\]$")


class TagError(Exception):
    pass


@dataclass(frozen=True)
class Ref:
    base: str            # canonical (declared) tag name
    path: tuple          # member names and array offsets below the tag
    bit: int | None
    type: str            # type of what the reference points at
    word: str            # type of the value holding the bit (= type without a bit)


def module_tags() -> dict[str, str]:
    out = {f"Local:{s}:I": "MODULE" for s in INPUT_SLOTS}
    out.update({f"Local:{s}:O": "MODULE" for s in OUTPUT_SLOTS})
    out[f"Local:{ANALOG_IN_SLOT}:I"] = "AI"
    out[f"Local:{ANALOG_OUT_SLOT}:O"] = "AO"
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


def _parse_array(text: str):
    m = _ARRAY.match(text.strip())
    if not m:
        return None
    n = int(m[2])
    return (m[1], 0, n - 1) if n > 0 else None


def type_system(udts: dict[str, dict[str, str]] | None = None) -> TypeSystem:
    """Logix types plus the program's user-defined types ({name: {member: type}})."""
    udts = udts or {}
    for name in udts:
        if not re.fullmatch(_NAME, name):
            raise TagError(f"{name!r} is not a valid data type name")
        if name.upper() in {*ATOMIC, *STRUCTS, *MODULES}:
            raise TagError(f"data type {name}: {name.upper()} is a built-in type")
    lower = [n.lower() for n in udts]
    if len(set(lower)) != len(lower):
        raise TagError("a data type is defined twice")
    base = TypeSystem(ATOMIC, {**STRUCTS, **MODULES, **{n: {} for n in udts}},
                      _parse_array, lambda e, lo, hi: f"{e}[{hi - lo + 1}]", START)
    structs = {n: {m: (base.canon(t) or t) for m, t in ms.items()} for n, ms in udts.items()}
    ts = TypeSystem(ATOMIC, {**STRUCTS, **MODULES, **structs}, _parse_array,
                    lambda e, lo, hi: f"{e}[{hi - lo + 1}]", START)
    try:
        ts.check_structs(structs)
    except DataTypeError as e:
        raise TagError(str(e)) from None
    return ts


class TagTable:
    def __init__(self, decls: dict[str, dict] | None = None, udts: dict[str, dict[str, str]] | None = None):
        self.ts = type_system(udts)
        self.udts = dict(udts or {})
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
        try:
            self.values[name] = self.ts.default(type_) if value is None else self.ts.coerce(type_, value)
        except (DataTypeError, ValueError, TypeError) as e:
            raise TagError(f"tag {name}: {e}") from None

    def declare(self, decls: dict[str, dict]) -> None:
        """Program tags: {name: {"type": "DINT", "value": 0}}. Raises TagError for a bad declaration."""
        for name, d in decls.items():
            raw = str(d.get("type", ""))
            t = self.ts.canon(raw)
            if not re.fullmatch(_NAME, name):
                raise TagError(f"{name!r} is not a valid tag name (letters, digits and _; no leading digit)")
            if t is None or t in MODULES:
                arr = _ARRAY.match(raw.strip())
                if arr and int(arr[2]) == 0:
                    raise TagError(f"tag {name}: an array needs at least one element")
                raise TagError(f"tag {name}: unknown type {raw!r} (use {', '.join([*TYPES, *self.udts])}, "
                               "or an array like DINT[10])")
            arr = self.ts.array(t)
            if arr and arr.size > 10_000:
                raise TagError(f"tag {name}: arrays hold at most 10000 elements")
            if name.lower() in self._canon:
                raise TagError(f"tag {name} is declared twice")
            self._add(name, t, d.get("value"))

    def clear(self, decls: dict[str, dict], keep_io: bool = True) -> None:
        io = {n: dict(v) for n, v in self.values.items() if self.types[n] in MODULES}
        self.__init__(decls, self.udts)
        if keep_io:
            self.values.update(io)

    # -- references ------------------------------------------------------------
    def ref(self, text: str, static: bool = False) -> Ref:
        """What a reference points at. static: tag indexes (Recipe[Step]) are only checked to be
        integer tags, not read."""
        parts = split(text, _BASE)
        if parts is None:
            raise TagError(f"{text!r} is not a tag reference")
        base_text, steps = parts
        base = self._canon.get(base_text.lower())
        if base is None:
            raise TagError(f"tag {base_text} does not exist")
        t = self.types[base]
        if t in MODULES and not (steps and steps[0][0] == "m" and self.ts.member(t, steps[0][1])):
            pretty = {"DATA": "Data", "CH0DATA": "Ch0Data", "CH1DATA": "Ch1Data"}
            raise TagError(f"{base}: use " + " or ".join(f"{base}.{pretty[m]}" for m in MODULES[t]))

        def index(arg: str):
            if re.fullmatch(r"\d+", arg):
                return int(arg)
            if arg == "*":                               # computed in structured text
                return None
            r = self.ref(arg, static)
            if r.type not in BITS:
                raise TagError(f"{text}: the index {arg} must be a SINT, INT or DINT")
            return None if static else int(self._get(r))

        try:
            path, bit, word = resolve(self.ts, t, steps, index, text, BITS, TagError)
        except TagError as e:
            if steps and steps[0][0] == "m" and self.ts.is_scalar(t):
                raise TagError(f"{base} has no member {steps[0][1]}") from None
            raise e from None
        return Ref(base, path, bit, "BOOL" if bit is not None else word, word)

    def _get(self, r: Ref):
        return get(self.values[r.base], r.path)

    def _put(self, r: Ref, value) -> None:
        if r.path:
            put(self.values[r.base], r.path, value)
        else:
            self.values[r.base] = value

    def is_scalar(self, t: str) -> bool:
        return self.ts.is_scalar(t)

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
        v = int(self._get(r)) & ((1 << BITS[r.word]) - 1)
        v = v | (1 << r.bit) if on else v & ~(1 << r.bit)
        self._put(r, wrap(v, r.word)[0])

    def read_word(self, text: str):
        r = self.ref(text)
        if not self.is_scalar(r.type):
            raise TagError(f"{text} is a {r.type}; use a member or an element")
        if r.type == "BOOL":
            return int(self.read_bit(text))
        return self._get(r)

    def write_word(self, text: str, value) -> bool:
        """Store a number, converted to the tag's type. Returns True on integer overflow."""
        r = self.ref(text)
        if not self.is_scalar(r.type):
            raise TagError(f"{text} is a {r.type}; use a member or an element")
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
        """The member dict of a TIMER, COUNTER or PID (a tag, a member or an array element)."""
        r = self.ref(text)
        if r.type not in STRUCTS:
            raise TagError(f"{text} is not a TIMER, COUNTER or PID")
        return self._get(r)

    def struct(self, text: str) -> dict:
        """The member dict of any structure."""
        r = self.ref(text)
        if not self.ts.is_struct(r.type):
            raise TagError(f"{text} is not a structure")
        return self._get(r)

    def type_of(self, text: str) -> str:
        return self.ref(text).type

    def walk(self, name: str):
        """(reference, type, value) for a tag and everything inside it."""
        return self.ts.walk(self.values[name], self.types[name], name)

    # -- I/O image ---------------------------------------------------------------
    def module_data(self, slot: int, direction: str) -> int:
        return int(self.values[f"Local:{slot}:{direction}"]["DATA"])

    def set_module_data(self, slot: int, direction: str, value: int) -> None:
        self.values[f"Local:{slot}:{direction}"]["DATA"] = wrap(int(value), "DINT")[0]

    def analog(self, slot: int, direction: str, channel: int) -> float:
        return float(self.values[f"Local:{slot}:{direction}"][f"CH{channel}DATA"])

    def set_analog(self, slot: int, direction: str, channel: int, volts: float) -> None:
        self.values[f"Local:{slot}:{direction}"][f"CH{channel}DATA"] = float(volts)

    def names(self) -> list[str]:
        return [n for n in self.types if self.types[n] not in MODULES and n not in SYSTEM]
