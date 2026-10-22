"""Room climate: temperature with a heater and a cooler (analog), a fan they need, an outside
temperature and a window that can be opened.

Digital (slot words):
  %I0.0 System on (NO)   %I0.1 System off (NC)   %I0.2 Window open   %I0.3 Airflow (fan running)
  %Q0.0 Fan   %Q0.1 Heating lamp   %Q0.2 Cooling lamp
Analog: AI0 room temperature 0-10 V = 0-50 °C, AI1 setpoint knob 0-10 V = 0-50 °C,
  AO0 heater 0-10 V = 0-100 %, AO1 cooler 0-10 V = 0-100 %.
Heating or cooling without the fan overheats the coil; heating and cooling together wastes energy.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

HEAT = 0.25                 # °C/s at full heater
COOL = 0.25
LOSS = 0.01                 # fraction per second towards outside (closed window)
WINDOW_LOSS = 0.06


@dataclass
class HvacModel:
    name = "Room climate"
    temperature: float = 16.0
    outside: float = 8.0
    setpoint_knob: float = 21.0          # °C
    window: bool = False
    on_pressed: bool = False
    off_pressed: bool = False
    outputs: int = 0
    heater: float = 0.0
    cooler: float = 0.0
    energy: float = 0.0                  # %·s of heating plus cooling
    fighting_s: float = 0.0              # seconds heating and cooling at once
    time_s: float = 0.0
    trend: deque = field(default_factory=lambda: deque(maxlen=1200))   # (t, sp, temp, heater, cooler)
    events: list[str] = field(default_factory=list)
    _trend_t: float = 0.0

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def input_words(self) -> dict[int, int]:
        w = int(self.on_pressed) | int(not self.off_pressed) << 1 | int(self.window) << 2 | int(self.out(0)) << 3
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def analog_inputs(self) -> dict[int, float]:
        return {0: min(max(self.temperature, 0.0), 50.0) / 5.0, 1: self.setpoint_knob / 5.0}

    def set_analog_outputs(self, volts: dict[int, float]) -> None:
        self.heater = min(max(volts.get(0, 0.0) * 10.0, 0.0), 100.0)
        self.cooler = min(max(volts.get(1, 0.0) * 10.0, 0.0), 100.0)

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        self.time_s += dt
        fan = self.out(0)
        heat, cool = self.heater / 100.0, self.cooler / 100.0
        if (heat > 0.05 or cool > 0.05) and not fan:
            self._event("Heater or cooler on without the fan")
            heat, cool = 0.0, 0.0
        if heat > 0.05 and cool > 0.05:
            self.fighting_s += dt
            if self.fighting_s > 2.0:
                self._event("Heating and cooling at the same time")
        loss = WINDOW_LOSS if self.window else LOSS
        self.temperature += (HEAT * heat - COOL * cool + (self.outside - self.temperature) * loss) * dt
        self.energy += (self.heater + self.cooler) * dt
        if self.time_s - self._trend_t >= 0.1 - 1e-9:
            self._trend_t = self.time_s
            self.trend.append((self.time_s, self.setpoint_knob * 2, self.temperature * 2, self.heater, self.cooler))
