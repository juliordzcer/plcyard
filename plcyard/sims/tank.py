"""Tank level process: an analog loop to control with on/off or PID.

Water enters through a pump (on/off) or a proportional inlet valve (0-10 V) and leaves through an
outlet whose opening the user sets (the disturbance). The level is measured 0-100 % and sent as
0-10 V; a setpoint knob sends 0-10 V on a second analog input.

Digital I/O (slot words, like the other simulations):
  %I0.0 Start (NO pushbutton)   %I0.1 Stop (NC pushbutton)
  %I0.2 High level switch (level >= 90 %)   %I0.3 Low level switch (level <= 10 %)
  %Q0.0 Pump (fixed flow)   %Q0.1 Run lamp   %Q0.2 High alarm lamp
Analog: AI0 level (0-10 V = 0-100 %), AI1 setpoint knob (0-10 V), AO0 inlet valve (0-10 V = 0-100 %).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

AREA = 1.0                 # level % per (flow unit · s): flows are in % of tank per second
PUMP_FLOW = 4.0            # %/s with the pump on
VALVE_FLOW = 3.0           # %/s with the inlet valve fully open
OUTLET_FLOW = 4.0          # %/s with the outlet fully open at 100 % level (falls as √level)
DEAD_TIME_S = 1.0          # pipe delay between valve and tank
HIGH, LOW = 90.0, 10.0
TREND_S = 120              # seconds kept for the trend


@dataclass
class TankModel:
    name = "Tank"
    level: float = 20.0                # %
    outlet: float = 50.0               # % opening, set by the user
    setpoint_knob: float = 50.0        # % of the knob (0-10 V)
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    valve: float = 0.0                 # inlet valve command, %
    overflowed: float = 0.0            # water lost over the top (%·s)
    time_s: float = 0.0
    _pipe: deque = field(default_factory=deque)   # (time it reaches the tank, flow)
    _arrived: float = 0.0                         # inflow now reaching the tank
    trend: deque = field(default_factory=lambda: deque(maxlen=TREND_S * 10))   # (t, sp, pv, cv) every 100 ms
    _trend_t: float = 0.0

    # -- signals --------------------------------------------------------------------
    @property
    def pump(self) -> bool:
        return bool(self.outputs & 1)

    def lamp(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    def input_words(self) -> dict[int, int]:
        w = int(self.start_pressed)
        w |= int(not self.stop_pressed) << 1             # NC contact
        w |= int(self.level >= HIGH) << 2
        w |= int(self.level <= LOW) << 3
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def analog_inputs(self) -> dict[int, float]:
        """Channel → volts."""
        return {0: self.level / 10.0, 1: self.setpoint_knob / 10.0}

    def set_analog_outputs(self, volts: dict[int, float]) -> None:
        self.valve = min(max(volts.get(0, 0.0) * 10.0, 0.0), 100.0)

    # -- physics ------------------------------------------------------------------------
    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        self.time_s += dt
        inflow_now = (PUMP_FLOW if self.pump else 0.0) + VALVE_FLOW * self.valve / 100.0
        self._pipe.append((self.time_s + DEAD_TIME_S, inflow_now))
        while self._pipe and self._pipe[0][0] <= self.time_s:
            self._arrived = self._pipe.popleft()[1]
        outflow = OUTLET_FLOW * (self.outlet / 100.0) * math.sqrt(max(self.level, 0.0) / 100.0)
        self.level += (self._arrived - outflow) * dt / AREA
        if self.level > 100.0:
            self.overflowed += (self.level - 100.0)
            self.level = 100.0
        self.level = max(self.level, 0.0)
        if self.time_s - self._trend_t >= 0.1 - 1e-9:
            self._trend_t = self.time_s
            self.trend.append((self.time_s, self.setpoint_knob, self.level, self.valve if not self.pump else 100.0))
