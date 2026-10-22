"""Garage door: a motor that opens and closes a sectional door, end-of-travel switches, a safety
photo-eye across the doorway and a flashing warning light.

Digital (slot words):
  %I0.0 Open button (NO)   %I0.1 Close button (NO)   %I0.2 Stop button (NC)
  %I0.3 Open limit (door fully up)   %I0.4 Closed limit (door fully down)
  %I0.5 Photo-eye beam clear (TRUE when nothing is in the doorway: fails safe)
  %Q0.0 Motor up   %Q0.1 Motor down   %Q0.2 Warning light   %Q0.3 Courtesy light
The door travels 0-100 % in 10 s. A car parked in the doorway is hit if the door reaches 30 %
while closing on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SPEED = 10.0               # % per second
CAR_TOP = 30.0             # the door touches the car below this opening


@dataclass
class GarageModel:
    name = "Garage door"
    position: float = 0.0             # 0 closed, 100 open
    car: bool = False                 # something in the doorway
    open_pressed: bool = False
    close_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    events: list[str] = field(default_factory=list)
    hits: int = 0
    cycles: int = 0                   # full openings
    _was_open: bool = False

    @property
    def up(self) -> bool:
        return bool(self.outputs & 1)

    @property
    def down(self) -> bool:
        return bool(self.outputs & 2)

    def lamp(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    def input_words(self) -> dict[int, int]:
        w = int(self.open_pressed)
        w |= int(self.close_pressed) << 1
        w |= int(not self.stop_pressed) << 2
        w |= int(self.position >= 100.0) << 3
        w |= int(self.position <= 0.0) << 4
        w |= int(not self.car) << 5
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        if self.up and self.down:
            self._event("Motor driven up and down at once")
            return
        if self.up:
            if self.position >= 100.0:
                self._event("Motor kept pushing at the open end stop")
            self.position = min(100.0, self.position + SPEED * dt)
        elif self.down:
            if self.position <= 0.0:
                self._event("Motor kept pushing at the closed end stop")
            new = max(0.0, self.position - SPEED * dt)
            if self.car and self.position > CAR_TOP >= new:
                self.hits += 1
                self._event("The door hit the car")
                new = CAR_TOP
            self.position = new
        if self.position >= 100.0 and not self._was_open:
            self.cycles += 1
        self._was_open = self.position >= 100.0
