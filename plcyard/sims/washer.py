"""Washing machine: lock the door, fill, wash turning left and right, drain, spin, unlock.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Door closed   %I0.3 Door locked
  %I0.4 Water present (level >= 10 %)   %I0.5 Water full (>= 80 %)   %I0.6 Drum stopped
  %Q0.0 Door lock   %Q0.1 Fill valve   %Q0.2 Wash left   %Q0.3 Wash right   %Q0.4 Spin
  %Q0.5 Drain pump   %Q0.6 Done lamp
A good wash: the clothes turn in water at least 10 s each way, the water is drained before the
spin, the spin lasts at least 5 s, and the door unlocks only once the drum has stopped.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FILL = 10.0                 # % per second
DRAIN = 15.0
WASH_RPM, SPIN_RPM = 50.0, 1000.0
ACCEL = 400.0               # rpm per second up or down


@dataclass
class WasherModel:
    name = "Washing machine"
    door_closed: bool = True
    water: float = 0.0
    rpm: float = 0.0                     # signed: + right, - left
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    washed_left_s: float = 0.0
    washed_right_s: float = 0.0
    spun_s: float = 0.0
    flooded: float = 0.0
    cycles: int = 0
    angle: float = 0.0
    events: list[str] = field(default_factory=list)

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    @property
    def locked(self) -> bool:
        return self.out(0) and self.door_closed

    def input_words(self) -> dict[int, int]:
        w = int(self.start_pressed) | int(not self.stop_pressed) << 1 | int(self.door_closed) << 2
        w |= int(self.locked) << 3 | int(self.water >= 10.0) << 4 | int(self.water >= 80.0) << 5
        w |= int(abs(self.rpm) < 1.0) << 6
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        if not self.door_closed and (self.out(1) or abs(self.rpm) > 1.0):
            self._event("Water or the drum running with the door open")
        if not self.out(0) and abs(self.rpm) > 1.0:
            self._event("The door unlocked while the drum was turning")
        if self.out(1):
            self.water += FILL * dt
            if not self.door_closed:
                self.flooded += FILL * dt
        if self.out(5):
            self.water = max(0.0, self.water - DRAIN * dt)
        if self.water > 100.0:
            self.flooded += self.water - 100.0
            self.water = 100.0
            self._event("The machine overflowed")
        left, right, spin = self.out(2), self.out(3), self.out(4)
        if left and right:
            self._event("Motor driven left and right at once")
            target = 0.0
        elif spin:
            target = SPIN_RPM
            if self.water >= 10.0:
                self._event("Spinning with water in the drum")
        elif left:
            target = -WASH_RPM
        elif right:
            target = WASH_RPM
        else:
            target = 0.0
        step = ACCEL * dt
        self.rpm = min(self.rpm + step, target) if target > self.rpm else max(self.rpm - step, target)
        if self.water >= 10.0 and abs(self.rpm) >= WASH_RPM - 1 and not spin:
            if self.rpm < 0:
                self.washed_left_s += dt
            else:
                self.washed_right_s += dt
        if spin and self.rpm >= SPIN_RPM - 1 and self.water < 10.0:
            self.spun_s += dt
        self.angle = (self.angle + self.rpm * 6.0 * dt * 0.05) % 360.0
        if self.out(6) and not self.out(0) and self.spun_s >= 5.0 and self.washed_left_s >= 10.0 \
                and self.washed_right_s >= 10.0:
            self.cycles += 1
            self.washed_left_s = self.washed_right_s = self.spun_s = 0.0
