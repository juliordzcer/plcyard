"""Pump station: a sump fills with an inflow you set; two pumps empty it. They should take turns
(equal running hours), the second one helps when the level keeps rising, and a failed pump is
replaced by the other.

Digital (slot words):
  %I0.0 Reset alarm (NO)   %I0.1 Stop (NC)   %I0.2 Low level (>= 15 %)   %I0.3 Start level (>= 50 %)
  %I0.4 High level (>= 75 %)   %I0.5 Overflow alarm level (>= 95 %)
  %I0.6 Pump 1 fault   %I0.7 Pump 2 fault (TRUE when the pump's protection tripped)
  %Q0.0 Pump 1   %Q0.1 Pump 2   %Q0.2 Alarm lamp
Analog: AI0 level, 0-10 V = 0-100 %.
"""

from __future__ import annotations

from dataclasses import dataclass, field

PUMP = 3.0                  # % per second each
LOW, START, HIGH, ALARM = 15.0, 50.0, 75.0, 95.0


@dataclass
class PumpStationModel:
    name = "Pump station"
    level: float = 30.0
    inflow: float = 40.0                 # % of the slider: 0-100 % = 0-5 %/s
    fault: list = field(default_factory=lambda: [False, False])
    reset_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    run_s: list = field(default_factory=lambda: [0.0, 0.0])
    starts: list = field(default_factory=lambda: [0, 0])
    overflowed: float = 0.0
    events: list[str] = field(default_factory=list)
    _was_on: list = field(default_factory=lambda: [False, False])

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def running(self, k: int) -> bool:
        return self.out(k) and not self.fault[k]

    def input_words(self) -> dict[int, int]:
        w = int(self.reset_pressed) | int(not self.stop_pressed) << 1
        w |= int(self.level >= LOW) << 2 | int(self.level >= START) << 3 | int(self.level >= HIGH) << 4
        w |= int(self.level >= ALARM) << 5 | int(self.fault[0]) << 6 | int(self.fault[1]) << 7
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def analog_inputs(self) -> dict[int, float]:
        return {0: self.level / 10.0}

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        out = 0.0
        for k in range(2):
            on = self.running(k)
            if on:
                out += PUMP
                self.run_s[k] += dt
                if self.level < 2.0:
                    self._event(f"Pump {k + 1} ran dry")
            if on and not self._was_on[k]:
                self.starts[k] += 1
            self._was_on[k] = on
        self.level += (5.0 * self.inflow / 100.0 - out) * dt
        if self.level > 100.0:
            self.overflowed += self.level - 100.0
            self.level = 100.0
            self._event("The sump overflowed")
        self.level = max(self.level, 0.0)
