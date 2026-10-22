"""Two tanks in series: an analog process for two loops or a cascade.

Water enters the upper tank 1 through a proportional inlet valve (or an on/off pump), flows down
into tank 2 through a proportional transfer valve, and leaves tank 2 through an outlet whose
opening the user sets (the disturbance). Flows through the valves fall with the square root of
the level above them, as in a real gravity-fed tank.

Digital (slot words): %I0.0 Start (NO)  %I0.1 Stop (NC)  %I0.2 Tank 1 high (>= 90 %)
  %I0.3 Tank 2 high (>= 90 %)  %I0.4 Tank 2 low (<= 10 %)
  %Q0.0 Feed pump (fixed flow)  %Q0.1 Run lamp  %Q0.2 Alarm lamp
Analog: AI0 tank 1 level, AI1 tank 2 level, AI2 setpoint knob (0-10 V = 0-100 %);
  AO0 inlet valve, AO1 transfer valve (0-10 V = 0-100 %).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

PUMP_FLOW = 3.0            # % of tank 1 per second
INLET_FLOW = 4.0           # %/s with the inlet valve fully open
TRANSFER_FLOW = 5.0        # %/s from tank 1 to tank 2, valve fully open and tank 1 full
OUTLET_FLOW = 4.0          # %/s out of tank 2, outlet fully open and tank 2 full
HIGH, LOW = 90.0, 10.0
TREND_S = 120


@dataclass
class TwoTankModel:
    name = "Two tanks"
    level1: float = 20.0
    level2: float = 20.0
    outlet: float = 50.0
    setpoint_knob: float = 50.0
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    inlet: float = 0.0
    transfer: float = 0.0
    overflowed: float = 0.0
    time_s: float = 0.0
    trend: deque = field(default_factory=lambda: deque(maxlen=TREND_S * 10))  # (t, sp, level1, level2, inlet, transfer)
    events: list[str] = field(default_factory=list)
    _trend_t: float = 0.0

    @property
    def pump(self) -> bool:
        return bool(self.outputs & 1)

    def lamp(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    def input_words(self) -> dict[int, int]:
        w = int(self.start_pressed)
        w |= int(not self.stop_pressed) << 1
        w |= int(self.level1 >= HIGH) << 2
        w |= int(self.level2 >= HIGH) << 3
        w |= int(self.level2 <= LOW) << 4
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def analog_inputs(self) -> dict[int, float]:
        return {0: self.level1 / 10.0, 1: self.level2 / 10.0, 2: self.setpoint_knob / 10.0}

    def set_analog_outputs(self, volts: dict[int, float]) -> None:
        self.inlet = min(max(volts.get(0, 0.0) * 10.0, 0.0), 100.0)
        self.transfer = min(max(volts.get(1, 0.0) * 10.0, 0.0), 100.0)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        self.time_s += dt
        inflow = (PUMP_FLOW if self.pump else 0.0) + INLET_FLOW * self.inlet / 100.0
        between = TRANSFER_FLOW * self.transfer / 100.0 * math.sqrt(max(self.level1, 0.0) / 100.0)
        out = OUTLET_FLOW * self.outlet / 100.0 * math.sqrt(max(self.level2, 0.0) / 100.0)
        self.level1 += (inflow - between) * dt
        self.level2 += (between - out) * dt
        for attr, name in (("level1", "Tank 1"), ("level2", "Tank 2")):
            v = getattr(self, attr)
            if v > 100.0:
                self.overflowed += v - 100.0
                if f"{name} overflowed" not in self.events:
                    self.events.append(f"{name} overflowed")
                v = 100.0
            setattr(self, attr, max(v, 0.0))
        if self.time_s - self._trend_t >= 0.1 - 1e-9:
            self._trend_t = self.time_s
            self.trend.append((self.time_s, self.setpoint_knob, self.level1, self.level2, self.inlet, self.transfer))
