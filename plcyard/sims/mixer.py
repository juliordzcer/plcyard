"""Batch mixer: fill with two ingredients, mix and heat, then drain the batch.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Low level (>= 5 %)   %I0.3 Middle level (>= 50 %)
  %I0.4 High level (>= 90 %)
  %Q0.0 Valve A   %Q0.1 Valve B   %Q0.2 Mixer motor   %Q0.3 Heater   %Q0.4 Drain valve
  %Q0.5 Batch done lamp
Analog: AI0 temperature, 0-10 V = 0-100 °C.

A good batch: ingredient A up to the middle level, ingredient B on top up to the high level,
mixed at least 5 s and at 50-60 °C before it is drained. Every drained batch is graded.
"""

from __future__ import annotations

from dataclasses import dataclass, field

FILL_A = 10.0              # % per second
FILL_B = 8.0
DRAIN = 12.0
HEAT = 3.0                 # °C per second with the heater on and liquid in the tank
COOL = 0.05                # fraction per second towards ambient
AMBIENT = 20.0
LOW, MID, HIGH = 5.0, 50.0, 90.0


@dataclass
class Batch:
    a: float
    b: float
    mixed_s: float
    temperature: float

    @property
    def good(self) -> bool:
        total = self.a + self.b
        return (total >= 85.0 and 0.4 <= self.a / max(total, 1e-9) <= 0.6 and self.mixed_s >= 5.0
                and 50.0 <= self.temperature <= 60.0)


@dataclass
class MixerModel:
    name = "Batch mixer"
    a: float = 0.0                    # % of the tank filled with A
    b: float = 0.0
    temperature: float = AMBIENT
    mixed_s: float = 0.0              # mixing time of the current batch
    max_temperature: float = AMBIENT
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    angle: float = 0.0                # mixer blade, for the drawing
    batches: list[Batch] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    spilled: float = 0.0
    _batch: Batch | None = None       # the batch as it was when the drain opened

    @property
    def level(self) -> float:
        return self.a + self.b

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def input_words(self) -> dict[int, int]:
        w = int(self.start_pressed)
        w |= int(not self.stop_pressed) << 1
        w |= int(self.level >= LOW) << 2
        w |= int(self.level >= MID) << 3
        w |= int(self.level >= HIGH) << 4
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def analog_inputs(self) -> dict[int, float]:
        return {0: min(max(self.temperature, 0.0), 100.0) / 10.0}

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        if self.out(0):
            self.a += FILL_A * dt
        if self.out(1):
            self.b += FILL_B * dt
        if self.level > 100.0:
            extra = self.level - 100.0
            self.spilled += extra
            share = self.a / self.level
            self.a -= extra * share
            self.b -= extra * (1 - share)
            self._event("The mixer overflowed")
        if self.out(2):
            self.angle = (self.angle + 360.0 * dt) % 360.0
            if self.level >= LOW:
                self.mixed_s += dt
            else:
                self._event("Mixer running with the tank empty")
        if self.out(3):
            if self.level >= LOW:
                self.temperature += HEAT * dt
            else:
                self._event("Heater on with no liquid (dry heating)")
                self.temperature += HEAT * 3 * dt
        self.temperature += (AMBIENT - self.temperature) * COOL * dt
        self.max_temperature = max(self.max_temperature, self.temperature)
        if not self.out(4):
            self._batch = None
        if self.out(4) and self.level > 0:
            if self._batch is None:
                self._batch = Batch(self.a, self.b, self.mixed_s, self.temperature)
            drained = min(self.level, DRAIN * dt)
            if self.level - drained <= 0.01:
                self.batches.append(self._batch)
                self._batch = None
                self._event("Batch drained: " + ("good" if self.batches[-1].good else "out of spec"))
                self.a = self.b = 0.0
                self.mixed_s = 0.0
            else:
                share = self.a / self.level
                self.a -= drained * share
                self.b -= drained * (1 - share)
