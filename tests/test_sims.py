"""Silo and traffic simulations driven by real ladder programs."""

from plcyard.core.processor import Processor
from plcyard.formats import rsl
from plcyard.sims.silo import SiloModel
from plcyard.sims.traffic import TrafficModel


def program(*rungs: str) -> str:
    lines = ["FILE,LAD 2"]
    for n, r in enumerate(rungs):
        lines += [f"SOR,{n} {r} EOR,{n}", "RCM,"]
    lines += [f"SOR,{len(rungs)} END,{len(rungs)}", "RCM,"]
    return "\r\n".join(lines) + "\r\n"


def run(model, *rungs):
    plc = Processor()
    plc.device = model
    assert plc.download(rsl.loads(program(*rungs))) == []
    plc.set_mode(Processor.RUN)
    return plc


def seconds(plc, s):
    for _ in range(int(s * 100)):
        plc.tick(10)


# Continuous mode: run latch, conveyor runs unless a box is under the hopper and not full.
SILO_CONTINUOUS = [
    "XIC,I:1/1 BST,1 XIC,I:1/0 NXB,1 XIC,O:2/2 BND,1 OTE,O:2/2",
    "XIC,O:2/2 BST,1 XIO,I:1/3 NXB,1 XIC,O:2/4 BND,1 OTE,O:2/0",
    "BST,1 XIC,I:1/4 NXB,1 XIC,O:2/4 BND,1 XIC,I:1/3 OTE,O:2/4",
    "XIC,O:2/2 XIC,I:1/3 XIO,O:2/4 BST,1 OTE,O:2/1 NXB,1 OTE,O:2/3 BND,1",
]


def test_silo_idle_inputs():
    assert SiloModel().input_words()[1] == 0x22


def test_silo_continuous_fills_every_box_without_spilling():
    m = SiloModel()
    plc = run(m, *SILO_CONTINUOUS)
    m.start_pressed = True
    seconds(plc, 0.1)
    m.start_pressed = False
    seconds(plc, 40)
    assert m.spill == 0 and not m.events
    passed = [b for b in m.boxes if b.x > 400]
    assert passed and all(b.fill >= 100 for b in passed)


def test_silo_stop_button_halts_everything():
    m = SiloModel()
    plc = run(m, *SILO_CONTINUOUS)
    m.start_pressed = True
    seconds(plc, 0.1)
    m.start_pressed = False
    seconds(plc, 2)
    m.stop_pressed = True
    seconds(plc, 0.1)
    m.stop_pressed = False
    xs = [b.x for b in m.boxes]
    seconds(plc, 3)
    assert not m.motor and not m.solenoid and [b.x for b in m.boxes] == xs


def test_silo_solenoid_without_box_spills():
    m = SiloModel()
    plc = run(m, "OTE,O:2/1")
    seconds(plc, 1)
    assert m.spill > 0 and "no box" in m.events[0]


def test_silo_overfill_is_reported():
    m = SiloModel()
    m.boxes[0].x = 360
    plc = run(m, "OTE,O:2/1")
    seconds(plc, 6)
    assert m.boxes[0].spilled and "overfilled" in m.events[-1].lower()


TRAFFIC_SAFE = [   # A green 4 s, amber 2 s, all red 1 s, B green 4 s, amber 2 s, all red 1 s
    "XIO,T4:5/DN TON,T4:0,40", "XIC,T4:0/DN TON,T4:1,20", "XIC,T4:1/DN TON,T4:2,10",
    "XIC,T4:2/DN TON,T4:3,40", "XIC,T4:3/DN TON,T4:4,20", "XIC,T4:4/DN TON,T4:5,10",
    "XIO,T4:0/DN OTE,O:2/2", "XIC,T4:0/DN XIO,T4:1/DN OTE,O:2/1", "XIC,T4:1/DN OTE,O:2/0",
    "XIC,T4:2/DN XIO,T4:3/DN OTE,O:2/6", "XIC,T4:3/DN XIO,T4:4/DN OTE,O:2/5",
    "BST,1 XIO,T4:2/DN NXB,1 XIC,T4:4/DN BND,1 OTE,O:2/4",
]


def test_traffic_safe_sequence_never_crashes():
    m = TrafficModel()
    plc = run(m, *TRAFFIC_SAFE)
    seconds(plc, 60)
    assert not m.crashed


def test_traffic_both_green_crashes():
    m = TrafficModel()
    plc = run(m, "OTE,O:2/2", "OTE,O:2/6")
    seconds(plc, 10)
    assert m.crashed and m.crashes == 1


def test_traffic_car_waits_at_red_and_sensor_reports_it():
    m = TrafficModel()
    m.cars["B"].parked = True
    plc = run(m, "OTE,O:2/0", "XIC,I:1/2 OTE,O:2/7")
    seconds(plc, 5)
    assert m.cars["A"].pos == 240.0 and m.waiting("A") and m.walk("B")


def test_traffic_parked_cars_do_not_crash():
    m = TrafficModel()
    m.cars["B"].parked = True
    plc = run(m, "OTE,O:2/2", "OTE,O:2/6")
    seconds(plc, 10)
    assert not m.crashed
