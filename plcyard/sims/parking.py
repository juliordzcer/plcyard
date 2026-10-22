"""Parking garage: entry and exit barriers with car detectors, a car counter and a FULL sign.
Ten spaces.

Digital (slot words):
  %I0.0 Car waiting at the entry   %I0.1 Car passed the entry barrier (beam)
  %I0.2 Car waiting at the exit   %I0.3 Car passed the exit barrier (beam)
  %I0.4 Entry barrier up   %I0.5 Exit barrier up
  %Q0.0 Raise entry barrier   %Q0.1 Raise exit barrier   %Q0.2 FULL sign
  %QW4 Free spaces on the display (BCD)
Cars arrive from the "Car arrives" and "Car leaves" buttons, or every few seconds with "Traffic".
A barrier rises in 1 s and stays up while its output is on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CAPACITY = 10
BARRIER_S = 1.0
PASS_S = 1.5                # time a car spends under the barrier


@dataclass
class ParkingModel:
    name = "Parking garage"
    parked: int = 3
    entry_queue: int = 0
    exit_queue: int = 0
    entry_barrier: float = 0.0          # 0 down, 100 up
    exit_barrier: float = 0.0
    traffic: bool = False
    outputs: int = 0
    display: int = 0
    events: list[str] = field(default_factory=list)
    entered: int = 0
    left: int = 0
    _entry_pass: float = -1.0           # seconds into passing, or -1
    _exit_pass: float = -1.0
    _clock: float = 0.0

    def out(self, bit: int) -> bool:
        return bool(self.outputs >> bit & 1)

    lamp = out

    def car_arrives(self) -> None:
        self.entry_queue += 1

    def car_leaves(self) -> None:
        if self.parked - (1 if self.exit_queue else 0) > 0:
            self.exit_queue += 1

    def input_words(self) -> dict[int, int]:
        w = int(self.entry_queue > 0 and self._entry_pass < 0)
        w |= int(self._entry_pass >= 0) << 1
        w |= int(self.exit_queue > 0 and self._exit_pass < 0) << 2 | int(self._exit_pass >= 0) << 3
        w |= int(self.entry_barrier >= 100.0) << 4 | int(self.exit_barrier >= 100.0) << 5
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF
        raw = words.get(6, 0) & 0xFFFF
        digits = f"{raw:04X}"
        self.display = int(digits) if digits.isdigit() else -1

    def _event(self, text: str) -> None:
        if not self.events or self.events[-1] != text:
            self.events.append(text)

    def step(self, dt_ms: float) -> None:
        dt = dt_ms / 1000.0
        rate = 100.0 / BARRIER_S * dt
        for attr, bit, pass_attr in (("entry_barrier", 0, "_entry_pass"), ("exit_barrier", 1, "_exit_pass")):
            pos = getattr(self, attr)
            if self.out(bit):
                pos = min(100.0, pos + rate)
            else:
                if getattr(self, pass_attr) >= 0 and pos > 0:
                    self._event("A barrier came down on a car")
                pos = max(0.0, pos - rate)
            setattr(self, attr, pos)
        # cars drive through a raised barrier
        if self._entry_pass < 0 and self.entry_queue and self.entry_barrier >= 100.0:
            self._entry_pass = 0.0
        if self._entry_pass >= 0:
            self._entry_pass += dt
            if self._entry_pass >= PASS_S:
                self._entry_pass = -1.0
                self.entry_queue -= 1
                self.parked += 1
                self.entered += 1
                if self.parked > CAPACITY:
                    self._event("A car came in with the garage full")
        if self._exit_pass < 0 and self.exit_queue and self.exit_barrier >= 100.0:
            self._exit_pass = 0.0
        if self._exit_pass >= 0:
            self._exit_pass += dt
            if self._exit_pass >= PASS_S:
                self._exit_pass = -1.0
                self.exit_queue -= 1
                self.parked -= 1
                self.left += 1
        if self.traffic:
            self._clock += dt
            if self._clock >= 4.0:
                self._clock = 0.0
                self.car_arrives() if (self.entered + self.left) % 3 != 2 else self.car_leaves()
