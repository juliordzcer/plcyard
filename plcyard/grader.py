"""Automatic checking of exercise programs: each written requirement of a lab becomes a check
that runs the student's program against a fresh simulation, faster than real time."""

from __future__ import annotations

import copy
import itertools
from dataclasses import dataclass, field

from .core.processor import Processor
from .core.program import Program
from .sims.io_panel import IoPanelModel
from .sims.silo import SiloModel
from .sims.tank import TankModel
from .sims.traffic import TrafficModel


@dataclass
class Check:
    requirement: str
    passed: bool
    detail: str = ""


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    error: str = ""             # download problems or a fault: nothing could be checked

    @property
    def passed(self) -> bool:
        return not self.error and bool(self.checks) and all(c.passed for c in self.checks)

    @property
    def score(self) -> str:
        return f"{sum(c.passed for c in self.checks)}/{len(self.checks)}"


class _Fault(Exception):
    pass


class Rig:
    def __init__(self, program: Program, simulation: str, symbols: dict[str, str]):
        prog = copy.deepcopy(program)
        prog.symbols = {**prog.symbols, **symbols}
        from .sims import MODELS
        self.sim = MODELS[simulation][1]()
        if isinstance(self.sim, IoPanelModel):
            self.sim.configure_from_symbols(prog.symbols)
        self.plc = Processor()
        self.plc.device = self.sim
        problems = self.plc.download(prog)
        if problems:
            raise _Fault("\n".join(str(p) for p in problems[:5]))
        self.plc.set_mode(Processor.RUN)
        self.ms(10)

    def ms(self, n: float) -> None:
        for _ in range(int(n // 10)):
            self.plc.tick(10)
            if self.plc.mode == Processor.FAULT:
                raise _Fault(f"Major fault {self.plc.fault_code:04X}h: {self.plc.fault}")

    def press(self, bit: int, hold_ms: int = 50) -> None:
        self.sim.set_pressed(1, bit, True)
        self.ms(hold_ms)
        self.sim.set_pressed(1, bit, False)
        self.ms(30)

    def lamps(self, n: int) -> list[bool]:
        return [self.sim.lamp(2, k) for k in range(n)]


NEEDS_RUN = "the motor never started, so this could not be checked"


def _01(new, out):
    r = new()
    wrong = []
    for bits in itertools.product((0, 1), repeat=7):
        for i, v in enumerate(bits):
            r.sim.set_pressed(1, i, bool(v))
        r.ms(10)
        a, b, c, d, e, f, g = bits
        want = [bool(a and b), bool(c or d), not e, f != g]
        got = r.lamps(4)
        wrong += [k for k in range(4) if got[k] != want[k] and k not in wrong]
    for k, name in enumerate(("AND: O:2/0 = I:1/0 and I:1/1", "OR: O:2/1 = I:1/2 or I:1/3",
                              "NOT: O:2/2 = not I:1/4", "XOR: O:2/3 = I:1/5 xor I:1/6")):
        out(name, k not in wrong, "wrong for some switch combinations" if k in wrong else "")


def _02(new, out):
    r = new()
    out("At power-up the motor is off and 'Stopped' is on", not r.sim.lamp(2, 0) and r.sim.lamp(2, 2))
    r.press(0)
    ran = r.sim.lamp(2, 0)
    out("Start runs the motor and it stays on (seal-in)", ran)
    out("'Running' on and 'Stopped' off while running", r.sim.lamp(2, 1) and not r.sim.lamp(2, 2))
    r.sim.set_pressed(1, 0, True)
    r.ms(30)
    held = r.sim.lamp(2, 0)
    r.sim.set_pressed(1, 1, True)
    r.ms(30)
    out("Stop wins over a held Start", held and not r.sim.lamp(2, 0), NEEDS_RUN)
    r.sim.set_pressed(1, 0, False)
    r.sim.set_pressed(1, 1, False)
    r.ms(30)
    r.sim.switch(1, 1).normally_closed = False
    r.ms(20)
    r.press(0)
    out("A broken Stop wire (input 0) prevents starting", ran and not r.sim.lamp(2, 0), NEEDS_RUN)


def _03(new, out):
    r = new()
    r.press(0)
    fwd = r.sim.lamp(2, 0) and not r.sim.lamp(2, 1)
    out("Forward runs the motor forward", fwd)
    r.press(1)
    out("Reverse is ignored while running forward", r.sim.lamp(2, 0) and not r.sim.lamp(2, 1))
    r.press(2)
    r.press(1)
    out("After Stop, Reverse runs the motor in reverse", r.sim.lamp(2, 1) and not r.sim.lamp(2, 0))
    r.sim.set_pressed(1, 0, True)
    r.sim.set_pressed(1, 1, True)
    r.ms(50)
    out("Never both directions at once", fwd and not (r.sim.lamp(2, 0) and r.sim.lamp(2, 1)), NEEDS_RUN)


def _04(new, out):
    r = new()
    seen = []
    for _ in range(4):
        r.press(0, hold_ms=300)
        seen.append(r.sim.lamp(2, 0))
    out("Each press toggles the lamp once, however long it is held", seen == [True, False, True, False],
        f"lamp after 4 presses: {['on' if s else 'off' for s in seen]}")


def _05(new, out):
    r = new()
    r.sim.set_pressed(1, 0, True)
    trace = []
    for _ in range(400):
        r.ms(10)
        trace.append(r.sim.lamp(2, 0))
    runs = [len(list(g)) for _, g in itertools.groupby(trace[5:])]
    inner = runs[1:-1]
    blinks = bool(inner) and all(95 <= n <= 105 for n in inner)
    out("With the switch on, the lamp blinks 1 s on / 1 s off", blinks,
        f"on/off times seen: {[n * 10 for n in inner]} ms" if inner else "the lamp does not blink")
    r.sim.set_pressed(1, 0, False)
    r.ms(20)
    out("With the switch off, the lamp is off", blinks and not r.sim.lamp(2, 0), "the lamp never blinked")


def _06(new, out):
    r = new()
    shown = []
    for _ in range(5):
        r.press(0, hold_ms=200)
        shown.append(r.sim.outputs.get(6, 0))
    out("The display counts 1, 2, 3, 4, 5 in BCD", shown == [int(str(n), 16) for n in range(1, 6)],
        f"display showed {[f'{v:X}' for v in shown]}")
    done = r.sim.lamp(2, 0)
    out("'Batch complete' lamp on at 5", done)
    r.press(1)
    out("Reset clears the count and the lamp", done and not r.sim.lamp(2, 0) and r.sim.outputs.get(6, 0) == 0,
        "nothing was counted")


def _07(new, out):
    bad = []
    for value, expect in ((0, 0), (99, 0), (100, 1), (500, 1), (501, 2), (9999, 2)):
        r = new()
        r.sim.thumbwheels = [int(d) for d in f"{value:04d}"]
        r.ms(20)
        if r.lamps(3) != [k == expect for k in range(3)]:
            bad.append(value)
    out("Exactly one lamp for each range (0-99, 100-500, 501-9999)", not bad,
        f"wrong for thumbwheel values {bad}" if bad else "")


def _start_silo(r):
    r.sim.start_pressed = True
    r.ms(50)
    r.sim.start_pressed = False
    r.ms(20)


def _08(new, out):
    r = new()
    _start_silo(r)
    saw_fill = saw_full = False
    for _ in range(4000):
        r.ms(10)
        saw_fill |= r.sim.lamp(3)
        saw_full |= r.sim.lamp(4)
    out("No product spilled", r.sim.spill == 0 and bool(r.sim.shipped), "no box was shipped")
    out("Boxes leave full (at least 2 in 40 s)", len(r.sim.shipped) >= 2 and all(f >= 100 for f in r.sim.shipped),
        f"{len(r.sim.shipped)} boxes shipped")
    out("'Filling' and 'Full' lamps used", saw_fill and saw_full)
    r.sim.stop_pressed = True
    r.ms(50)
    out("Stop turns the conveyor, valve and 'Run' lamp off",
        bool(r.sim.shipped) and not (r.sim.motor or r.sim.solenoid or r.sim.lamp(2)), "the line never ran")


def _09(new, out):
    r = new()
    r.sim.selector = "B"
    r.ms(20)
    _start_silo(r)
    r.ms(15000)
    under = r.sim.box_under_hopper()
    out("Mode B: a full box waits for Start", bool(under) and under.fill >= 100 and not r.sim.motor)
    if under:
        _start_silo(r)
        r.ms(3000)
        out("Mode B: Start moves the full box on, no spill", under.x > 401 and r.sim.spill == 0)
    r = new()
    r.sim.selector = "C"
    r.ms(20)
    _start_silo(r)
    r.ms(25000)
    out("Mode C: conveyor keeps moving and nothing is filled",
        r.sim.motor and bool(r.sim.shipped) and all(f == 0 for f in r.sim.shipped) and r.sim.spill == 0)
    r = new()
    _start_silo(r)
    r.ms(40000)
    out("Mode A: continuous filling, no spill",
        r.sim.spill == 0 and len(r.sim.shipped) >= 2 and all(f >= 100 for f in r.sim.shipped))


def _10(new, out):
    r = new()
    one_each = safe = True
    green_seen = False
    states = []
    for _ in range(12000):
        r.ms(10)
        s = r.sim
        a = [s.light("A", c) for c in ("red", "amber", "green")]
        b = [s.light("B", c) for c in ("red", "amber", "green")]
        one_each &= sum(a) == 1 and sum(b) == 1
        safe &= not (s.light("A", "green") and not s.light("B", "red"))
        green_seen |= s.light("A", "green")
        states.append(("".join("RAG"[i] for i in range(3) if a[i]), "".join("RAG"[i] for i in range(3) if b[i])))
    out("Exactly one light on in each direction", one_each)
    out("Green on A only while B is red", safe and green_seen, "A never turned green" if safe else "")
    out("No crash and traffic flows both ways",
        not r.sim.crashed and r.sim.cars["A"].passes > 3 and r.sim.cars["B"].passes > 3)
    runs = [(k, len(list(g))) for k, g in itertools.groupby(states)]
    phases = dict(runs[1:7])
    out("Timing: amber 2 s, green 6 s, all-red 1 s",
        phases.get(("A", "R")) in (199, 200, 201) and phases.get(("R", "G")) in (599, 600, 601)
        and phases.get(("R", "R")) in (99, 100, 101))


def _start_tank(r):
    r.sim.start_pressed = True
    r.ms(50)
    r.sim.start_pressed = False
    r.ms(20)


def _11(new, out):
    r = new()
    r.sim.level = 20.0
    _start_tank(r)
    out("Start lights the Run light", r.sim.lamp(1))
    r.ms(500)
    out("Below 40 % the pump runs", r.sim.pump)
    lo, hi, switched = 100.0, 0.0, 0
    last = r.sim.pump
    r.ms(60000)
    for _ in range(9000):
        r.ms(10)
        lo, hi = min(lo, r.sim.level), max(hi, r.sim.level)
        switched += r.sim.pump != last
        last = r.sim.pump
    held = 33 <= lo and hi <= 67 and switched >= 2
    out("The level stays between about 35 % and 65 %", held, f"level went from {lo:.0f} % to {hi:.0f} %")
    out("The pump does not chatter (hysteresis)", held and switched < 30, f"{switched} pump switchings in 90 s")
    r.sim.stop_pressed = True
    r.ms(50)
    r.sim.stop_pressed = False
    r.ms(500)
    out("Stop turns the pump and the Run light off", held and not r.sim.pump and not r.sim.lamp(1), NEEDS_RUN)
    r.sim.level = 95.0
    r.ms(30)
    out("High alarm light follows the high level switch", r.sim.lamp(2))
    r.sim.level = 50.0
    r.ms(30)
    out("High alarm light off below the switch", r.sim.lamp(2) is False and held, "the alarm stays on")


def _12(new, out):
    r = new()
    r.sim.level, r.sim.setpoint_knob = 20.0, 60.0
    peak, inside_from = 0.0, None
    for k in range(9000):
        r.ms(10)
        peak = max(peak, r.sim.level)
        inside = abs(r.sim.level - 60.0) <= 2.0
        inside_from = (inside_from if inside_from is not None else k / 100) if inside else None
    reached = inside_from is not None and inside_from <= 60.0
    out("Level within ±2 % of the setpoint in 60 s", reached,
        f"level {r.sim.level:.1f} % after 90 s" if inside_from is None else f"settled after {inside_from:.0f} s")
    out("Overshoot no more than 5 %", reached and peak - 60.0 <= 5.0, f"peak {peak:.1f} %")
    r.sim.outlet = 85.0
    worst = 0.0
    for k in range(6000):
        r.ms(10)
        if k > 6000 - 500:
            worst = max(worst, abs(r.sim.level - 60.0))
    out("Back within ±2 % 60 s after the outlet opens wider", reached and worst <= 2.0,
        f"still {worst:.1f} % away")
    r.sim.setpoint_knob = 40.0
    r.ms(60000)
    out("Follows a new setpoint (40 %)", abs(r.sim.level - 40.0) <= 2.0, f"level {r.sim.level:.1f} %")
    out("The tank never overflows", r.sim.overflowed == 0 and reached)


CHECKS = {"01": _01, "02": _02, "03": _03, "04": _04, "05": _05,
          "06": _06, "07": _07, "08": _08, "09": _09, "10": _10, "11": _11, "12": _12, "13": _12}


def grade(lab, program: Program) -> Report:
    """Run every requirement of `lab` against `program`. Never raises for a wrong program."""
    report = Report()
    check = CHECKS.get(lab.id)
    if check is None:
        report.error = "This exercise has no automatic checks."
        return report

    def new():
        return Rig(program, lab.simulation, lab.symbols)

    def out(requirement, passed, detail=""):
        report.checks.append(Check(requirement, bool(passed), "" if passed else detail))

    try:
        check(new, out)
    except _Fault as e:
        report.error = str(e)
    return report
