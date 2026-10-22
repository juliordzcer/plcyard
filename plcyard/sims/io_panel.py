"""Generic I/O trainer: 2 input cards of switches, 2 output cards of lamps,
4 BCD thumbwheels on %IW4 and a 4-digit BCD display on %QW4."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_NC = re.compile(r"\bN\.?C\.?(?![A-Z])", re.I)
_PB = re.compile(r"\bPB\b|push ?button|pulsador|bot[oó]n", re.I)

INPUT_SLOTS = (1, 3)
OUTPUT_SLOTS = (2, 4)
THUMBWHEEL_SLOT, DISPLAY_SLOT = 5, 6


@dataclass
class SwitchConfig:
    normally_closed: bool = False
    momentary: bool = False


@dataclass
class IoPanelModel:
    pressed: dict[tuple[int, int], bool] = field(default_factory=dict)        # (slot, bit) -> actuated
    config: dict[tuple[int, int], SwitchConfig] = field(default_factory=dict)
    thumbwheels: list[int] = field(default_factory=lambda: [0, 0, 0, 0])      # most significant first
    outputs: dict[int, int] = field(default_factory=dict)

    name = "I/O"

    def switch(self, slot: int, bit: int) -> SwitchConfig:
        return self.config.setdefault((slot, bit), SwitchConfig())

    def configure_from_symbols(self, symbols: dict[str, str], io_name=None) -> None:
        """Wire switches as the program expects: 'Stop (NC)', 'Open - NO,PB', 'Stop (NC, pushbutton)'.
        `io_name(direction, slot, bit)` names an input point (%I0.0 by default)."""
        if io_name is None:
            from ..core.plc import PLC
            io_name = PLC.io_name
        points = {io_name("I", s, b).upper(): (s, b) for s in INPUT_SLOTS for b in range(16)}
        for addr, desc in symbols.items():
            point = points.get(addr.strip().upper())
            if point is None:
                continue
            cfg = self.switch(*point)
            cfg.normally_closed = bool(_NC.search(desc))
            cfg.momentary = bool(_PB.search(desc))

    def set_pressed(self, slot: int, bit: int, on: bool) -> None:
        self.pressed[(slot, bit)] = on

    def signal(self, slot: int, bit: int) -> bool:
        return self.pressed.get((slot, bit), False) != self.switch(slot, bit).normally_closed

    # -- IODevice ---------------------------------------------------------
    def input_words(self) -> dict[int, int]:
        words = {}
        for slot in INPUT_SLOTS:
            w = 0
            for bit in range(16):
                if self.signal(slot, bit):
                    w |= 1 << bit
            words[slot] = w
        bcd = 0
        for d in self.thumbwheels:
            bcd = (bcd << 4) | (d % 10)
        words[THUMBWHEEL_SLOT] = bcd
        return words

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = dict(words)

    def step(self, dt_ms: float) -> None:
        pass

    def lamp(self, slot: int, bit: int) -> bool:
        return bool((self.outputs.get(slot, 0) >> bit) & 1)
