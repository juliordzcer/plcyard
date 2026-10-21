"""Generic I/O trainer: 2 input cards of switches, 2 output cards of lamps,
4 BCD thumbwheels on I:5 and a 4-digit BCD display on O:6."""

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

    def configure_from_symbols(self, symbols: dict[str, str]) -> None:
        """Wire switches as the program expects: 'Stop (NC)', 'Open - NO,PB', 'Stop (NC, pushbutton)'."""
        for addr, desc in symbols.items():
            m = re.fullmatch(r"I:(\d+)/(\d+)", addr.strip().upper())
            if not m or int(m[1]) not in INPUT_SLOTS:
                continue
            cfg = self.switch(int(m[1]), int(m[2]))
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
