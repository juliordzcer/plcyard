"""Processor data table. Every file is an array of signed 16-bit words, except F (floats).

Timers, counters and controls are 3 words each, as in the SLC-500, so bit and
word access work the same everywhere and the data table view can show raw words.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .address import ELEMENT_WORDS, SUBS, Address, parse_address


class DataTableError(Exception):
    """Addressing fault at run time (out of range, missing file)."""


DEFAULT_SIZES = {0: 8, 1: 8, 2: 64, 3: 256, 4: 256, 5: 256, 6: 256, 7: 256, 8: 256}
FILE_TYPE_OF = {0: "O", 1: "I", 2: "S", 3: "B", 4: "T", 5: "C", 6: "R", 7: "N", 8: "F"}


def to_int16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


@dataclass
class DataFile:
    type: str
    number: int
    elements: int
    words: list = field(default_factory=list)

    def __post_init__(self):
        if not self.words:
            n = self.elements * ELEMENT_WORDS.get(self.type, 1)
            self.words = [0.0] * n if self.type == "F" else [0] * n

    @property
    def width(self) -> int:
        return ELEMENT_WORDS.get(self.type, 1)


class DataTable:
    def __init__(self, sizes: dict[int, int] | None = None):
        self.files: dict[int, DataFile] = {}
        for num, n in (sizes or DEFAULT_SIZES).items():
            self.files[num] = DataFile(FILE_TYPE_OF[num], num, n)
        self._cache: dict[str, Address] = {}

    # -- helpers --------------------------------------------------------
    def addr(self, a: str | Address) -> Address:
        if isinstance(a, Address):
            return a
        hit = self._cache.get(a)
        if hit is None:
            hit = self._cache[a] = parse_address(a)
        return hit

    def file(self, number: int) -> DataFile:
        f = self.files.get(number)
        if f is None:
            raise DataTableError(f"file {number} does not exist")
        return f

    def _element(self, a: Address) -> int:
        if isinstance(a.element, Address):
            return self.read_word(a.element)
        return a.element

    def _locate(self, a: Address) -> tuple[DataFile, int, int | None]:
        """Return (file, word index, bit or None) for any non-file-ref address."""
        f = self.file(a.file)
        if a.element is None:  # B3/37
            return f, a.bit // 16, a.bit % 16
        el = self._element(a)
        if el < 0 or el >= f.elements:
            raise DataTableError(f"{a} is out of range (file has {f.elements} elements)")
        idx = el * f.width + a.word
        bit = a.bit
        if a.sub is not None:
            off, sbit = SUBS[a.type][a.sub]
            idx += off
            if sbit is not None:
                bit = sbit
        if idx >= len(f.words):
            raise DataTableError(f"{a} is out of range")
        return f, idx, bit

    # -- access ---------------------------------------------------------
    def read_bit(self, a: str | Address) -> bool:
        f, idx, bit = self._locate(self.addr(a))
        if bit is None:
            return f.words[idx] != 0
        return bool((int(f.words[idx]) >> bit) & 1)

    def write_bit(self, a: str | Address, on: bool) -> None:
        f, idx, bit = self._locate(self.addr(a))
        if bit is None:
            raise DataTableError(f"{a} is not a bit address")
        w = int(f.words[idx]) & 0xFFFF
        w = (w | (1 << bit)) if on else (w & ~(1 << bit))
        f.words[idx] = to_int16(w)

    def read_word(self, a: str | Address) -> int | float:
        f, idx, bit = self._locate(self.addr(a))
        if bit is not None:
            return (int(f.words[idx]) >> bit) & 1
        return f.words[idx]

    def write_word(self, a: str | Address, value: int | float) -> None:
        f, idx, bit = self._locate(self.addr(a))
        if bit is not None:
            self.write_bit(a, bool(value))
        elif f.type == "F":
            f.words[idx] = float(value)
        else:
            f.words[idx] = to_int16(int(value))

    # -- slot words for the I/O scan -------------------------------------
    def read_slot(self, file_no: int, slot: int) -> int:
        return self.files[file_no].words[slot] & 0xFFFF

    def write_slot(self, file_no: int, slot: int, value: int) -> None:
        self.files[file_no].words[slot] = to_int16(value)

    def clear(self, keep_io: bool = False) -> None:
        for f in self.files.values():
            if keep_io and f.type in ("I", "O"):
                continue
            f.words = [0.0 if f.type == "F" else 0] * len(f.words)
