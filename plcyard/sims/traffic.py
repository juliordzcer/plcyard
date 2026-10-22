"""Intersection with two traffic directions, crosswalk buttons and two cars.

I/O:
  %Q0.0 Red A   %Q0.1 Amber A   %Q0.2 Green A   %Q0.3 Walk (crossing A)
  %Q0.4 Red B   %Q0.5 Amber B   %Q0.6 Green B   %Q0.7 Walk (crossing B)
  %I0.0 Crosswalk button A   %I0.1 Crosswalk button B
  %I0.2 Car waiting at A     %I0.3 Car waiting at B
Car A drives along road A (lights %Q0.0-%Q0.2), car B along road B (%Q0.4-%Q0.6).
A car stops at its stop line unless its light is green; on amber it keeps going if it is
already close to the line. Two cars inside the junction at the same time is a crash.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ROAD_LEN = 600.0
STOP_LINE = 240.0          # front of the car stops here
JUNCTION = (260.0, 340.0)  # span of the crossing area along each road
CAR_LEN = 50.0
SPEED = 120.0              # px/s (car B is slower so the two cars do not stay in lockstep)
COMMIT = 25.0              # on amber, a car this close to the line goes through
RESPAWN_S = 2.0


@dataclass
class Car:
    road: str              # "A" or "B"
    pos: float = 0.0       # front bumper along the road
    parked: bool = False
    wait: float = 0.0      # respawn timer
    speed: float = SPEED
    passes: int = 0        # times the car crossed the whole road

    @property
    def in_junction(self) -> bool:
        return self.pos > JUNCTION[0] and self.pos - CAR_LEN < JUNCTION[1]


@dataclass
class TrafficModel:
    name = "Traffic"
    outputs: int = 0
    buttons: dict[str, bool] = field(default_factory=lambda: {"A": False, "B": False})
    cars: dict[str, Car] = field(default_factory=lambda: {"A": Car("A", 60.0), "B": Car("B", 20.0, speed=SPEED * 0.8)})
    crashed: bool = False
    crashes: int = 0
    events: list[str] = field(default_factory=list)

    def light(self, road: str, colour: str) -> bool:
        base = 0 if road == "A" else 4
        return bool(self.outputs >> (base + {"red": 0, "amber": 1, "green": 2}[colour]) & 1)

    def walk(self, road: str) -> bool:
        return bool(self.outputs >> (3 if road == "A" else 7) & 1)

    def waiting(self, road: str) -> bool:
        c = self.cars[road]
        return not c.parked and STOP_LINE - 2 <= c.pos <= STOP_LINE + 0.5

    # -- IODevice -------------------------------------------------------------
    def input_words(self) -> dict[int, int]:
        w = int(self.buttons["A"]) | int(self.buttons["B"]) << 1
        w |= int(self.waiting("A")) << 2 | int(self.waiting("B")) << 3
        return {1: w}

    def set_output_words(self, words: dict[int, int]) -> None:
        self.outputs = words.get(2, 0) & 0xFFFF

    def step(self, dt_ms: float) -> None:
        if self.crashed:
            return
        dt = dt_ms / 1000.0
        for road, car in self.cars.items():
            if car.parked:
                continue
            if car.wait > 0:
                car.wait -= dt
                continue
            nxt = car.pos + car.speed * dt
            before_line = car.pos <= STOP_LINE
            green = self.light(road, "green")
            amber = self.light(road, "amber")
            may_go = green or (amber and STOP_LINE - car.pos < COMMIT)
            if before_line and nxt > STOP_LINE and not may_go:
                nxt = STOP_LINE
            car.pos = nxt
            if car.pos - CAR_LEN > ROAD_LEN:
                car.pos, car.wait = 0.0, RESPAWN_S
                car.passes += 1
        a, b = self.cars["A"], self.cars["B"]
        if not a.parked and not b.parked and a.in_junction and b.in_junction:
            self.crashed = True
            self.crashes += 1
            self.events.append("Crash in the junction: both directions had right of way")

    def reset(self) -> None:
        parked = {k: c.parked for k, c in self.cars.items()}
        self.__init__()
        for k, p in parked.items():
            self.cars[k].parked = p
