"""Structured tag values shared by the tag-based controllers: user structures (Logix UDTs, S7 PLC
data types, S7 FB instances) and one-dimensional arrays.

A structure value is a dict keyed by canonical member name, an array a list. A reference like
`Line[2].Motor.Speed.3` splits into a base tag and steps: ("m", "Motor"), ("i", "2"), ("b", 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_NAME = re.compile(NAME)
MAX_ELEMENTS = 10_000


@dataclass(frozen=True)
class ArrayType:
    elem: str
    lo: int
    hi: int

    @property
    def size(self) -> int:
        return self.hi - self.lo + 1


class DataTypeError(Exception):
    pass


class TypeSystem:
    """Types a controller knows: atomic (name → default value), structures (name → {member: type})
    and arrays, whose syntax the controller gives as (parse, format)."""

    def __init__(self, atomic: dict[str, object], structs: dict[str, dict[str, str]],
                 parse_array: Callable[[str], tuple[str, int, int] | None],
                 format_array: Callable[[str, int, int], str],
                 start: dict[str, dict] | None = None):
        self.atomic = atomic
        self.structs = structs
        self.start = start or {}
        self._parse_array, self._format_array = parse_array, format_array
        self._canon = {t.lower(): t for t in [*atomic, *structs]}
        self._members = {t: {m.lower(): m for m in ms} for t, ms in structs.items()}

    def canon(self, text: str) -> str | None:
        """The declared spelling of a type, or None when it is unknown."""
        text = text.strip()
        arr = self._parse_array(text)
        if arr is not None:
            elem = self.canon(arr[0])
            if elem is None or self._parse_array(elem) is not None:
                return None
            return self._format_array(elem, arr[1], arr[2])
        return self._canon.get(text.lower())

    def array(self, t: str) -> ArrayType | None:
        arr = self._parse_array(t)
        return ArrayType(*arr) if arr else None

    def is_struct(self, t: str) -> bool:
        return t in self.structs

    def is_scalar(self, t: str) -> bool:
        return t in self.atomic

    def member(self, t: str, name: str) -> tuple[str, str] | None:
        canon = self._members.get(t, {}).get(name.lower())
        return (canon, self.structs[t][canon]) if canon else None

    def default(self, t: str):
        arr = self.array(t)
        if arr:
            return [self.default(arr.elem) for _ in range(arr.size)]
        if t in self.structs:
            out = {m: self.default(mt) for m, mt in self.structs[t].items()}
            out.update(self.start.get(t, {}))
            return out
        return self.atomic[t]

    def coerce(self, t: str, value):
        """A start value converted to type t (dicts for structures, lists for arrays)."""
        arr = self.array(t)
        if arr:
            out = self.default(t)
            items = value if isinstance(value, list) else []
            if len(items) > arr.size:
                raise DataTypeError(f"{len(items)} start values for {arr.size} elements")
            for k, v in enumerate(items):
                out[k] = self.coerce(arr.elem, v)
            return out
        if t in self.structs:
            out = self.default(t)
            if not isinstance(value, dict):
                return out
            for m, v in value.items():
                mm = self.member(t, m)
                if mm is None:
                    raise DataTypeError(f"{t} has no member {m}")
                out[mm[0]] = self.coerce(mm[1], v)
            return out
        d = self.atomic[t]
        if isinstance(d, bool):
            return bool(value)
        if isinstance(d, float):
            return float(value)
        return int(value)

    def check_structs(self, structs: dict[str, dict[str, str]], kind: str = "data type") -> None:
        """Member types exist and no structure contains itself."""
        for name, members in structs.items():
            for m, mt in members.items():
                if not _NAME.fullmatch(m):
                    raise DataTypeError(f"{kind} {name}: {m!r} is not a valid member name")
                if self.canon(mt) is None:
                    raise DataTypeError(f"{kind} {name}: member {m} has unknown type {mt!r}")

        def contains(t: str, seen: tuple) -> None:
            arr = self.array(t)
            t = arr.elem if arr else t
            if t in seen:
                raise DataTypeError(f"{kind} {seen[0]} contains itself")
            for mt in structs.get(t, {}).values():
                contains(self.canon(mt), seen + (t,))
        for name in structs:
            for mt in structs[name].values():
                contains(self.canon(mt), (name,))

    def walk(self, value, t: str, prefix: str):
        """Every (reference, type, value) below a value, the value itself first."""
        yield prefix, t, value
        arr = self.array(t)
        if arr:
            for k, v in enumerate(value):
                yield from self.walk(v, arr.elem, f"{prefix}[{arr.lo + k}]")
        elif t in self.structs:
            for m, mt in self.structs[t].items():
                yield from self.walk(value[m], mt, f"{prefix}.{m}")


def split(text: str, base: re.Pattern) -> tuple[str, list[tuple[str, object]]] | None:
    """Base name and steps of a reference; None when it does not parse. Index text is kept raw
    (a number or a tag) for the memory to resolve."""
    text = text.strip()
    m = base.match(text)
    if not m:
        return None
    pos, steps = m.end(), []
    while pos < len(text):
        c = text[pos]
        if c == ".":
            mm = re.compile(rf"\d+|%X\d+|{NAME}").match(text, pos + 1)
            if not mm:
                return None
            part = mm.group()
            steps.append(("b", int(part.lstrip("%Xx"))) if part[0].isdigit() or part[0] == "%" else ("m", part))
            pos = mm.end()
        elif c == "[":
            depth, k = 1, pos + 1
            while k < len(text) and depth:
                depth += {"[": 1, "]": -1}.get(text[k], 0)
                k += 1
            if depth:
                return None
            inner = text[pos + 1:k - 1].strip()
            if not inner:
                return None
            steps.append(("i", inner))
            pos = k
        else:
            return None
    return m.group(1) if m.groups() else m.group(), steps


def resolve(types: TypeSystem, t: str, steps: list, index: Callable[[str], int], text: str,
            bits: dict[str, int], err: type[Exception]) -> tuple[tuple, int | None, str]:
    """Follow steps from a value of type t: (path keys, bit, type reached before the bit)."""
    path: list = []
    bit = None
    for k, (kind, arg) in enumerate(steps):
        if bit is not None:
            raise err(f"{text}: nothing can follow a bit number")
        if kind == "i":
            arr = types.array(t)
            if arr is None:
                raise err(f"{text}: {t} is not an array")
            i = index(arg)                      # None: a tag index, checked when it runs
            if i is None:
                i = arr.lo
            elif not arr.lo <= i <= arr.hi:
                raise err(f"{text}: index {i} out of range ({arr.lo}..{arr.hi})")
            path.append(i - arr.lo)
            t = arr.elem
        elif kind == "m":
            mm = types.member(t, arg)
            if mm is None:
                if t in types.structs:
                    raise err(f"{text}: {t} has no member {arg} (has {', '.join(types.structs[t])})")
                raise err(f"{text}: a {t} has no members")
            path.append(mm[0])
            t = mm[1]
        else:
            if t not in bits:
                names = list(bits)
                raise err(f"{text}: only {', '.join(names[:-1])} and {names[-1]} values have numbered bits")
            if arg >= bits[t]:
                raise err(f"{text}: bit {arg} out of range (0-{bits[t] - 1})")
            bit = arg
    return tuple(path), bit, t


def get(value, path: tuple):
    for key in path:
        value = value[key]
    return value


def put(container, path: tuple, value) -> None:
    for key in path[:-1]:
        container = container[key]
    container[path[-1]] = value
