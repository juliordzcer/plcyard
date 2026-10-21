"""SLC-500 style address parsing.

Supported forms::

    I:1/0  I:1.0/3  O:2  S:1/13  S2:1/13      I/O and status (I=file 1, O=file 0, S=file 2)
    B3:0/5  B3/37  N7:12  N7:0/3              word, bit-in-word, bit-in-file
    T4:1.ACC  T4:1/DN  C5:0.PRE  R6:0/EN      structured sub-elements
    N7:[C5:0.ACC]  #N7:0                     indirect element, file reference
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_FILE = {"O": 0, "I": 1, "S": 2, "B": 3, "T": 4, "C": 5, "R": 6, "N": 7, "F": 8}
FILE_TYPES = {"O", "I", "S", "B", "T", "C", "R", "N", "F"}

# Structured element layouts: name -> (word offset, bit or None)
TIMER_SUBS = {"EN": (0, 15), "TT": (0, 14), "DN": (0, 13), "PRE": (1, None), "ACC": (2, None)}
COUNTER_SUBS = {"CU": (0, 15), "CD": (0, 14), "DN": (0, 13), "OV": (0, 12), "UN": (0, 11),
                "UA": (0, 10), "PRE": (1, None), "ACC": (2, None)}
CONTROL_SUBS = {"EN": (0, 15), "EU": (0, 14), "DN": (0, 13), "EM": (0, 12), "ER": (0, 11),
                "UL": (0, 10), "IN": (0, 9), "FD": (0, 8), "LEN": (1, None), "POS": (2, None)}
SUBS = {"T": TIMER_SUBS, "C": COUNTER_SUBS, "R": CONTROL_SUBS}
ELEMENT_WORDS = {"T": 3, "C": 3, "R": 3}


class AddressError(ValueError):
    pass


@dataclass(frozen=True)
class Address:
    type: str                         # one of FILE_TYPES
    file: int
    element: int | "Address" | None   # None for bit-in-file form (B3/37)
    word: int = 0                     # I:1.0/3 -> word 0 within the slot
    sub: str | None = None            # ACC, PRE, DN ...
    bit: int | None = None
    is_file_ref: bool = False         # leading '#'

    @property
    def is_bit(self) -> bool:
        if self.bit is not None:
            return True
        if self.sub is not None:
            return SUBS[self.type][self.sub][1] is not None
        return False

    @property
    def is_indirect(self) -> bool:
        return isinstance(self.element, Address)

    def __str__(self) -> str:
        return format_address(self)


_RX = re.compile(
    r"""^(?P<hash>\#)?
        (?P<type>[OISBTCRNF])(?P<file>\d+)?
        (?: :(?P<elem>\d+|\[[^\]]+\]) (?:\.(?P<word>\d+))? (?:\.(?P<sub>[A-Z]{2,3}))? )?
        (?: /(?P<bit>\d+|[A-Z]{2}) )?$""",
    re.X,
)


def parse_address(text: str) -> Address:
    s = text.strip().upper()
    m = _RX.match(s)
    if not m:
        raise AddressError(f"not an address: {text!r}")
    t = m["type"]
    file_no = int(m["file"]) if m["file"] else DEFAULT_FILE[t]
    if t in ("O", "I", "S") and m["file"] and int(m["file"]) != DEFAULT_FILE[t]:
        raise AddressError(f"{t} is always file {DEFAULT_FILE[t]}: {text!r}")
    if t not in ("O", "I", "S") and not m["file"]:
        raise AddressError(f"missing file number: {text!r}")
    elem_txt, word, sub, bit = m["elem"], m["word"], m["sub"], m["bit"]
    element: int | Address | None
    if elem_txt is None:
        if bit is None or not bit.isdigit() or t not in ("B", "N"):
            if not m["hash"]:
                raise AddressError(f"missing element: {text!r}")
        element = None
    elif elem_txt.startswith("["):
        element = parse_address(elem_txt[1:-1])
        if element.is_bit:
            raise AddressError(f"index must be a word: {text!r}")
    else:
        element = int(elem_txt)

    if bit is not None and not bit.isdigit():  # T4:0/DN form
        if sub is not None:
            raise AddressError(f"bad address: {text!r}")
        sub, bit = bit, None
    if sub is not None:
        if t not in SUBS or sub not in SUBS[t]:
            raise AddressError(f"{sub} is not part of a {t} element: {text!r}")
    elif t in SUBS and elem_txt is not None and bit is None and not m["hash"]:
        pass  # whole element (e.g. RES T4:0)
    bit_no = int(bit) if bit is not None else None
    if bit_no is not None:
        limit = 16 if element is not None else 16 * 4096
        if bit_no >= limit:
            raise AddressError(f"bit out of range: {text!r}")
    if word is not None and t not in ("I", "O"):
        raise AddressError(f"word suffix only valid on I/O: {text!r}")
    return Address(t, file_no, element, int(word or 0), sub, bit_no, bool(m["hash"]))


def format_address(a: Address) -> str:
    head = ("#" if a.is_file_ref else "") + a.type
    if a.type not in ("O", "I", "S"):
        head += str(a.file)
    if a.element is None:
        return head + (f"/{a.bit}" if a.bit is not None else "")
    elem = f"[{format_address(a.element)}]" if isinstance(a.element, Address) else str(a.element)
    out = f"{head}:{elem}"
    if a.word:
        out += f".{a.word}"
    if a.sub is not None:
        sep = "/" if SUBS[a.type][a.sub][1] is not None else "."
        out += f"{sep}{a.sub}"
    if a.bit is not None:
        out += f"/{a.bit}"
    return out


_HEX = re.compile(r"^-?[0-9A-F]+H$", re.I)


def parse_literal(text: str) -> int | float | None:
    """Return the numeric value of a literal operand, or None if it is not one."""
    s = text.strip()
    if _HEX.match(s):
        v = int(s[:-1], 16)
        return v - 0x10000 if v > 0x7FFF else v
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return None
