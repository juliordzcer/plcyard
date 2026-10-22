"""Pick and place: a two-axis pneumatic arm moves parts from an infeed to a tray with a vacuum
gripper.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Arm at pick side (horizontal retracted)
  %I0.3 Arm at place side (horizontal extended)   %I0.4 Arm up   %I0.5 Arm down
  %I0.6 Part waiting at the pick point   %I0.7 Vacuum OK (a part is held)
  %Q0.0 Horizontal cylinder: extend   %Q0.1 Vertical cylinder: down   %Q0.2 Vacuum
  %Q0.3 Cycle lamp
Each cylinder takes 1 s from end to end. Moving sideways while the arm is down knocks things over.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TRAVEL_S = 1.0


@dataclass
class PickPlaceModel:
    name = "Pick and place"
    x: float = 0.0             # 0 pick side, 100 place side
    z: float = 0.0             # 0 up, 100 down
    held: bool = False
    part_waiting: bool = True
    placed: int = 0
    dropped: int = 0
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    events: list[str] = field(default_factory=list)
    _refill_s: float = 0.0

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def input_words(self) -> dict[int, int]:
        w = int(self.start_pressed) | int(not self.stop_pressed) << 1
        w |= int(self.x <= 0.0) << 2 | int(self.x >= 100.0) << 3 | int(self.z <= 0.0) << 4 | int(self.z >= 100.0) << 5
        w |= int(self.part_waiting) << 6 | int(self.held) << 7
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        rate = 100.0 / TRAVEL_S * dt
        target_x = 100.0 if self.out(0) else 0.0
        if self.x != target_x and self.z > 5.0:
            self._event("The arm moved sideways while down")
        if target_x > self.x:
            self.x = min(self.x + rate, 100.0)
        elif target_x < self.x:
            self.x = max(self.x - rate, 0.0)
        self.z = min(self.z + rate, 100.0) if self.out(1) else max(self.z - rate, 0.0)
        if self.out(2):
            if not self.held and self.z >= 100.0 and self.x <= 0.0 and self.part_waiting:
                self.held, self.part_waiting = True, False
                self._refill_s = 0.0
        elif self.held:
            self.held = False
            if self.x >= 100.0 and self.z >= 100.0:
                self.placed += 1
            else:
                self.dropped += 1
                self._event("A part was dropped outside the tray")
        if not self.part_waiting:
            self._refill_s += dt
            if self._refill_s >= 1.0:
                self.part_waiting = True
