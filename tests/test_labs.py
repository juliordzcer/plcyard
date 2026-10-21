"""Every exercise is solvable: its reference solution meets each written requirement."""

import itertools
from pathlib import Path

import pytest

from plcyard import labs
from plcyard.core.processor import Processor
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel
from plcyard.sims.silo import SiloModel
from plcyard.sims.traffic import TrafficModel

SOL = Path(__file__).resolve().parent.parent / "labs" / "solutions"
LABS = {lab.id: lab for lab in labs.load_all()}


def rig(lab_id: str):
    lab = LABS[lab_id]
    prog = rsl.load(SOL / f"{lab_id}.rsl")
    prog.symbols = dict(lab.symbols)
    sim = {"io": IoPanelModel, "silo": SiloModel, "traffic": TrafficModel}[lab.simulation]()
    if isinstance(sim, IoPanelModel):
        sim.configure_from_symbols(prog.symbols)
    plc = Processor()
    plc.device = sim
    assert plc.download(prog) == []
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    return plc, sim


def ms(plc, n):
    for _ in range(int(n // 10)):
        plc.tick(10)


def press(plc, sim, bit, hold_ms=50):
    sim.set_pressed(1, bit, True)
    ms(plc, hold_ms)
    sim.set_pressed(1, bit, False)
    ms(plc, 30)


def test_all_labs_have_header_and_solution():
    assert len(LABS) == 10
    for lab in LABS.values():
        assert lab.title and lab.simulation in ("io", "silo", "traffic")
        assert (SOL / f"{lab.id}.rsl").exists()
        assert Processor().download(lab.starter()) == []


def test_01_gates_truth_table():
    plc, sim = rig("01")
    for bits in itertools.product((0, 1), repeat=7):
        for i, v in enumerate(bits):
            sim.set_pressed(1, i, bool(v))
        ms(plc, 10)
        a, b, c, d, e, f, g = bits
        assert [sim.lamp(2, k) for k in range(4)] == [bool(a and b), bool(c or d), not e, f != g]


def test_02_start_stop():
    plc, sim = rig("02")
    assert not sim.lamp(2, 0) and sim.lamp(2, 2)
    press(plc, sim, 0)
    assert sim.lamp(2, 0) and sim.lamp(2, 1) and not sim.lamp(2, 2)
    sim.set_pressed(1, 0, True)
    sim.set_pressed(1, 1, True)
    ms(plc, 30)
    assert not sim.lamp(2, 0), "stop wins over a held start"
    sim.set_pressed(1, 0, False)
    sim.set_pressed(1, 1, False)
    ms(plc, 30)
    assert not sim.lamp(2, 0)
    sim.switch(1, 1).normally_closed = False          # broken stop wire: input reads 0
    ms(plc, 20)
    press(plc, sim, 0)
    assert not sim.lamp(2, 0)


def test_03_reversing_interlock():
    plc, sim = rig("03")
    press(plc, sim, 0)
    assert sim.lamp(2, 0) and not sim.lamp(2, 1)
    press(plc, sim, 1)
    assert sim.lamp(2, 0) and not sim.lamp(2, 1), "must stop before reversing"
    press(plc, sim, 2)
    press(plc, sim, 1)
    assert sim.lamp(2, 1) and not sim.lamp(2, 0)
    sim.set_pressed(1, 0, True)
    sim.set_pressed(1, 1, True)
    ms(plc, 50)
    assert not (sim.lamp(2, 0) and sim.lamp(2, 1))


def test_04_single_button_toggle():
    plc, sim = rig("04")
    seen = []
    for _ in range(4):
        press(plc, sim, 0, hold_ms=300)
        seen.append(sim.lamp(2, 0))
    assert seen == [True, False, True, False]


def test_05_blinker():
    plc, sim = rig("05")
    sim.set_pressed(1, 0, True)
    trace = []
    for _ in range(400):
        plc.tick(10)
        trace.append(sim.lamp(2, 0))
    runs = [len(list(g)) for _, g in itertools.groupby(trace[5:])]
    assert all(95 <= r <= 105 for r in runs[1:-1]), runs
    sim.set_pressed(1, 0, False)
    ms(plc, 20)
    assert not sim.lamp(2, 0)


def test_06_batch_counter():
    plc, sim = rig("06")
    for n in range(1, 6):
        press(plc, sim, 0, hold_ms=200)
        assert sim.outputs.get(6, 0) == int(str(n), 16)
    assert sim.lamp(2, 0)
    press(plc, sim, 1)
    assert not sim.lamp(2, 0) and sim.outputs.get(6, 0) == 0


@pytest.mark.parametrize("value,expect", [(0, 0), (99, 0), (100, 1), (500, 1), (501, 2), (9999, 2)])
def test_07_ranges(value, expect):
    plc, sim = rig("07")
    sim.thumbwheels = [int(d) for d in f"{value:04d}"]
    ms(plc, 20)
    assert [sim.lamp(2, k) for k in range(3)] == [k == expect for k in range(3)]


def start_silo(plc, sim):
    sim.start_pressed = True
    ms(plc, 50)
    sim.start_pressed = False
    ms(plc, 20)


def test_08_silo_continuous():
    plc, sim = rig("08")
    start_silo(plc, sim)
    saw_fill = saw_full = False
    for _ in range(4000):
        plc.tick(10)
        saw_fill |= sim.lamp(3)
        saw_full |= sim.lamp(4)
    assert sim.spill == 0 and saw_fill and saw_full
    assert len(sim.shipped) >= 2 and all(f >= 100 for f in sim.shipped)
    sim.stop_pressed = True
    ms(plc, 50)
    assert not (sim.motor or sim.solenoid or sim.lamp(2))


def test_09_silo_modes():
    # B: full box waits for one touch of Start
    plc, sim = rig("09")
    sim.selector = "B"
    ms(plc, 20)
    start_silo(plc, sim)
    ms(plc, 15000)
    under = sim.box_under_hopper()
    assert under and under.fill >= 100 and not sim.motor, "waits for the operator"
    start_silo(plc, sim)
    ms(plc, 3000)
    assert under.x > 400 + 1 and sim.spill == 0
    # C: no filling, conveyor keeps moving
    plc, sim = rig("09")
    sim.selector = "C"
    ms(plc, 20)
    start_silo(plc, sim)
    ms(plc, 15000)
    ms(plc, 10000)
    assert sim.motor and sim.shipped and all(f == 0 for f in sim.shipped) and sim.spill == 0
    # A: continuous
    plc, sim = rig("09")
    start_silo(plc, sim)
    ms(plc, 40000)
    assert sim.spill == 0 and len(sim.shipped) >= 2 and all(f >= 100 for f in sim.shipped)


def test_10_traffic_sequence_and_no_crash():
    plc, sim = rig("10")
    states = []
    for _ in range(12000):
        plc.tick(10)
        a = [sim.light("A", c) for c in ("red", "amber", "green")]
        b = [sim.light("B", c) for c in ("red", "amber", "green")]
        assert sum(a) == 1 and sum(b) == 1
        assert not (sim.light("A", "green") and not sim.light("B", "red"))
        states.append(("".join("RAG"[i] for i in range(3) if a[i]), "".join("RAG"[i] for i in range(3) if b[i])))
    assert not sim.crashed
    assert sim.cars["A"].passes > 3 and sim.cars["B"].passes > 3
    runs = [(k, len(list(g))) for k, g in itertools.groupby(states)]
    phases = dict(runs[1:7])
    assert phases[("A", "R")] in (199, 200, 201) and phases[("R", "G")] in (599, 600, 601)
    assert phases[("R", "R")] in (99, 100, 101)
