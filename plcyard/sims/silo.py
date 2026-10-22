"""Silo filling line: boxes ride a conveyor, stop under a hopper, fill, move on.

I/O:
  %I0.0 Start (NO pushbutton)   %I0.1 Stop (NC pushbutton)
  %I0.3 Prox sensor (box under the hopper)   %I0.4 Level sensor (box full)
  %I0.5 / %I0.6 / %I0.7 Selector A / B / C
  %Q0.0 Conveyor motor   %Q0.1 Fill solenoid   %Q0.2 Run lamp   %Q0.3 Fill lamp   %Q0.4 Full lamp
Idle input word is 0022h: Stop is NC (closed) and the selector rests on A.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CONVEYOR_LEN = 640.0       # px of belt
BOX_W = 80.0
BOX_GAP = 160.0            # space between boxes
SPEED = 60.0               # px/s with the motor on
SENSOR_X = 400.0           # prox sensor and hopper outlet
FILL_RATE = 25.0           # % per second (4 s to fill)
SPILL_LIMIT = 100.0


@dataclass
class Box:
    x: float               # left edge
    fill: float = 0.0
    spilled: bool = False

    @property
    def right(self) -> float:
        return self.x + BOX_W


@dataclass
class SiloModel:
    name = "Silo"
    start_pressed: bool = False
    stop_pressed: bool = False
    selector: str = "A"
    boxes: list[Box] = field(default_factory=lambda: [Box(SENSOR_X - BOX_W - 120)])
    outputs: int = 0
    spill: float = 0.0             # product on the floor (%)
    shipped: list[float] = field(default_factory=list)   # fill level of each box that left the line
    events: list[str] = field(default_factory=list)

    # -- signals ------------------------------------------------------------
    @property
    def motor(self) -> bool:
        return bool(self.outputs & 1)

    @property
    def solenoid(self) -> bool:
        return bool(self.outputs & 2)

    def lamp(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    def box_under_hopper(self) -> Box | None:
        return next((b for b in self.boxes if b.x <= SENSOR_X <= b.right), None)

    def prox(self) -> bool:
        """The sensor sees a box once its centre has reached the hopper outlet, so a conveyor
        stopped by it leaves the box centred under the filling pipe."""
        b = self.box_under_hopper()
        return b is not None and SENSOR_X - 1.0 <= b.x + BOX_W / 2 <= b.right - 12.0

    def level(self) -> bool:
        b = self.box_under_hopper()
        return bool(b and b.fill >= 100.0)

    # -- IODevice -------------------------------------------------------------
    def input_words(self) -> dict[int, int]:
        w = 0
        w |= int(self.start_pressed) << 0
        w |= int(not self.stop_pressed) << 1          # NC contact
        w |= int(self.prox()) << 3
        w |= int(self.level()) << 4
        w |= {"A": 1 << 5, "B": 1 << 6, "C": 1 << 7}[self.selector]
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        if self.motor:
            for b in self.boxes:
                b.x += SPEED * dt
            self.shipped += [b.fill for b in self.boxes if b.x >= CONVEYOR_LEN]
            self.boxes = [b for b in self.boxes if b.x < CONVEYOR_LEN]
            first = min((b.x for b in self.boxes), default=CONVEYOR_LEN)
            if first > BOX_GAP:                       # feed a new empty box
                self.boxes.insert(0, Box(first - BOX_GAP - BOX_W))
        if self.solenoid:
            b = self.box_under_hopper()
            if b is None:
                self._spill(FILL_RATE * dt, "Product poured with no box under the hopper")
            else:
                b.fill += FILL_RATE * dt
                if b.fill > SPILL_LIMIT:
                    b.spilled = True
                    self._spill(b.fill - SPILL_LIMIT, "Box overfilled")
                    b.fill = SPILL_LIMIT

    def _spill(self, amount: float, why: str) -> None:
        self.spill += amount
        if not self.events or self.events[-1] != why:
            self.events.append(why)

    def reset(self) -> None:
        self.__init__(selector=self.selector)
