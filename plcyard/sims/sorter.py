"""Sorting conveyor: boxes of three heights pass two light beams that measure them, then three
pushers send each box into the bin for its size.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Box at the measuring point
  %I0.3 Low beam blocked (medium or large box)   %I0.4 High beam blocked (large box)
  %I0.5 %I0.6 %I0.7 Box in front of pusher 1, 2, 3
  %Q0.0 Conveyor   %Q0.1 Pusher 1 (small)   %Q0.2 Pusher 2 (medium)   %Q0.3 Pusher 3 (large)
  %Q0.4 Run lamp
Boxes arrive in the order small, large, medium, medium, small, large, …; a box that reaches the end
of the belt falls off.
"""

from __future__ import annotations

from dataclasses import dataclass, field

LENGTH = 640.0
SPEED = 60.0
GAP = 110.0
MEASURE = 140.0
PUSHERS = (300.0, 410.0, 520.0)
WINDOW = 8.0
SIZES = ("S", "L", "M", "M", "S", "L")
HEIGHT = {"S": 20.0, "M": 34.0, "L": 48.0}


@dataclass
class Box:
    x: float
    size: str


@dataclass
class SorterModel:
    name = "Sorting conveyor"
    boxes: list[Box] = field(default_factory=lambda: [Box(MEASURE - 2 * GAP, "S")])
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    bins: dict = field(default_factory=lambda: {1: [], 2: [], 3: []})
    fallen: int = 0
    events: list[str] = field(default_factory=list)
    _count: int = 1

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def at(self, x: float) -> Box | None:
        return next((b for b in self.boxes if abs(b.x - x) <= WINDOW), None)

    @property
    def wrong(self) -> int:
        want = {1: "S", 2: "M", 3: "L"}
        return sum(1 for k, boxes in self.bins.items() for b in boxes if b.size != want[k])

    def input_words(self) -> dict[int, int]:
        m = self.at(MEASURE)
        w = int(self.start_pressed) | int(not self.stop_pressed) << 1 | int(m is not None) << 2
        w |= int(m is not None and m.size in "ML") << 3 | int(m is not None and m.size == "L") << 4
        for k, x in enumerate(PUSHERS):
            w |= int(self.at(x) is not None) << (5 + k)
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        for k, x in enumerate(PUSHERS, start=1):
            if self.out(k):
                b = self.at(x)
                if b is not None:
                    self.boxes.remove(b)
                    self.bins[k].append(b)
                    if b.size != {1: "S", 2: "M", 3: "L"}[k]:
                        self._event(f"A {dict(S='small', M='medium', L='large')[b.size]} box went into bin {k}")
        if self.out(0):
            for b in self.boxes:
                b.x += SPEED * dt
            for b in [b for b in self.boxes if b.x >= LENGTH]:
                self.boxes.remove(b)
                self.fallen += 1
                self._event("A box fell off the end of the belt")
            first = min((b.x for b in self.boxes), default=LENGTH)
            if first > -40 + GAP:
                self.boxes.insert(0, Box(first - GAP, SIZES[self._count % len(SIZES)]))
                self._count += 1
