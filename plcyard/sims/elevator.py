"""Elevator for three floors: hall and car buttons, floor sensors, a door with limits and a safety
edge, overtravel limits at both ends of the shaft.

Digital (slot words):
  %I0.0-%I0.2 Hall call floors 1-3   %I0.3-%I0.5 Car buttons floors 1-3
  %I0.6 %I0.7 %I1.0 Car at floor 1, 2, 3   %I1.1 Door open limit   %I1.2 Door closed limit
  %I1.3 Door safety edge clear (TRUE unless someone is in the doorway)
  %I1.4 Top overtravel OK   %I1.5 Bottom overtravel OK (TRUE unless the car passed the end)
  %Q0.0 Motor up   %Q0.1 Motor down   %Q0.2 Door open   %Q0.3 Door close
  %Q0.4-%Q0.6 Position lamps floors 1-3
The car travels a floor in 3 s, the door opens or closes in 2 s. A call is served when the door
opens at its floor.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FLOOR = 100.0               # position units per floor (floor 1 at 0)
SPEED = FLOOR / 3.0
DOOR_SPEED = 50.0           # % per second
AT = 2.0                    # floor sensor window


@dataclass
class ElevatorModel:
    name = "Elevator"
    position: float = 0.0
    door: float = 0.0                         # 0 closed, 100 open
    hall: list = field(default_factory=lambda: [False] * 3)
    car: list = field(default_factory=lambda: [False] * 3)
    waiting: set = field(default_factory=set)  # floors with a passenger waiting (from a hall call)
    blocked: bool = False                     # someone in the doorway
    outputs: int = 0
    served: int = 0
    events: list[str] = field(default_factory=list)

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def floor_at(self) -> int | None:
        for k in range(3):
            if abs(self.position - k * FLOOR) <= AT:
                return k
        return None

    def press_hall(self, floor: int, on: bool) -> None:
        self.hall[floor] = on
        if on:
            self.waiting.add(floor)

    def input_words(self) -> dict[int, int]:
        f = self.floor_at()
        w = sum(int(self.hall[k]) << k for k in range(3)) | sum(int(self.car[k]) << (3 + k) for k in range(3))
        w |= int(f == 0) << 6 | int(f == 1) << 7 | int(f == 2) << 8
        w |= int(self.door >= 100.0) << 9 | int(self.door <= 0.0) << 10 | int(not self.blocked) << 11
        w |= int(self.position <= 2 * FLOOR + 10) << 12 | int(self.position >= -10) << 13
        # slot words map points 0-15 to %I0.0-%I1.7: points 8-13 are %I1.0-%I1.5
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        up, down, opening, closing = self.out(0), self.out(1), self.out(2), self.out(3)
        if up and down:
            self._event("Motor driven up and down at once")
        elif up or down:
            if self.door > 0.0:
                self._event("The car moved with the door open")
            self.position += (SPEED if up else -SPEED) * dt
            if self.position > 2 * FLOOR + 10 or self.position < -10:
                self._event("Overtravel: the car ran past the end of the shaft")
                self.position = min(max(self.position, -15.0), 2 * FLOOR + 15.0)
        if opening and closing:
            self._event("Door driven open and closed at once")
        elif opening:
            if (up or down) and self.floor_at() is None:
                self._event("Door opened between floors")
            self.door = min(100.0, self.door + DOOR_SPEED * dt)
        elif closing:
            if self.blocked and self.door > 0:
                self._event("The door closed on a passenger")
            self.door = max(0.0, self.door - DOOR_SPEED * dt)
        f = self.floor_at()
        if f is not None and self.door >= 100.0 and f in self.waiting:
            self.waiting.discard(f)
            self.served += 1
