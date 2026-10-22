"""Bottle line: a conveyor carries empty bottles past a filler, a capper and an inspection station
with a reject pusher. Every fifth bottle gets a bad cap from the capper and must be rejected.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Bottle at the filler   %I0.3 Bottle full
  %I0.4 Bottle at the capper   %I0.5 Bottle at inspection   %I0.6 Bottle at inspection is good
  %Q0.0 Conveyor   %Q0.1 Fill valve   %Q0.2 Capper press   %Q0.3 Reject pusher   %Q0.4 Run lamp
A bottle stops under a station only if the conveyor stops while the station's sensor sees it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LENGTH = 640.0
SPEED = 60.0                # px/s
GAP = 120.0
FILLER, CAPPER, INSPECT = 200.0, 340.0, 480.0
WINDOW = 6.0                # a sensor sees a bottle whose centre is this close
FILL_RATE = 40.0            # % per second
CAP_TIME = 0.5              # seconds of press


@dataclass
class Bottle:
    x: float                # centre
    serial: int
    fill: float = 0.0
    capped: bool = False
    bad_cap: bool = False
    press_s: float = 0.0

    @property
    def good(self) -> bool:
        return 95.0 <= self.fill <= 105.0 and self.capped and not self.bad_cap


@dataclass
class BottleModel:
    name = "Bottle line"
    bottles: list[Bottle] = field(default_factory=lambda: [Bottle(FILLER - 3 * GAP, 1)])
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    shipped_good: int = 0
    shipped_bad: int = 0
    rejected_good: int = 0
    rejected_bad: int = 0
    spilled: float = 0.0
    events: list[str] = field(default_factory=list)
    _next: int = 2

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def at(self, x: float) -> Bottle | None:
        return next((b for b in self.bottles if abs(b.x - x) <= WINDOW), None)

    def input_words(self) -> dict[int, int]:
        f, c, i = self.at(FILLER), self.at(CAPPER), self.at(INSPECT)
        w = int(self.start_pressed) | int(not self.stop_pressed) << 1
        w |= int(f is not None) << 2 | int(f is not None and f.fill >= 95.0) << 3
        w |= int(c is not None) << 4 | int(i is not None) << 5 | int(i is not None and i.good) << 6
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        if self.out(0):
            for b in self.bottles:
                b.x += SPEED * dt
            for b in [b for b in self.bottles if b.x >= LENGTH]:
                self.bottles.remove(b)
                if b.good:
                    self.shipped_good += 1
                else:
                    self.shipped_bad += 1
                    self._event("A bad bottle was shipped")
            first = min((b.x for b in self.bottles), default=LENGTH)
            if first > -40 + GAP:
                self.bottles.insert(0, Bottle(first - GAP, self._next, bad_cap=self._next % 5 == 0))
                self._next += 1
        if self.out(1):
            b = self.at(FILLER)
            if b is None or self.out(0):
                self.spilled += FILL_RATE * dt
                self._event("Filling with no bottle standing under the filler")
            else:
                b.fill += FILL_RATE * dt
                if b.fill > 110.0:
                    self.spilled += b.fill - 110.0
                    b.fill = 110.0
                    self._event("A bottle overflowed")
        if self.out(2):
            b = self.at(CAPPER)
            if b is not None and not self.out(0):
                b.press_s += dt
                if b.press_s >= CAP_TIME:
                    b.capped = True
            elif self.out(0) and b is not None:
                self._event("The capper came down on a moving bottle")
        if self.out(3):
            b = self.at(INSPECT)
            if b is not None:
                self.bottles.remove(b)
                if b.good:
                    self.rejected_good += 1
                    self._event("A good bottle was rejected")
                else:
                    self.rejected_bad += 1
