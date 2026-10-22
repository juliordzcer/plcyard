"""Two tanks, garage door and batch mixer: their physics and the examples that drive them."""

from plcyard import formats, labs
from plcyard.core.processor import Processor
from plcyard.sims.garage import GarageModel
from plcyard.sims.mixer import MixerModel
from plcyard.sims.two_tanks import TwoTankModel


def rig(name, model):
    plc = Processor()
    plc.device = model
    assert plc.download(formats.load(labs.SAMPLES / name)) == []
    plc.set_mode(Processor.RUN)
    return plc


def run(plc, seconds):
    for _ in range(int(seconds * 100)):
        plc.tick(10)


def test_two_tanks_physics_and_alarms():
    m = TwoTankModel(level1=50.0, level2=50.0, outlet=0.0)
    m.set_analog_outputs({0: 0.0, 1: 10.0})
    for _ in range(500):
        m.step(10)
    assert m.level1 < 50.0 < m.level2, "water runs from tank 1 into tank 2"
    m.level2, m.outlet = 99.0, 0.0
    for _ in range(500):
        m.step(10)
    assert m.overflowed > 0 and "Tank 2 overflowed" in m.events
    assert m.input_words()[1] & 0b1000, "tank 2 high switch"


def test_cascade_example_holds_tank_2():
    m = TwoTankModel(level1=10.0, level2=10.0, setpoint_knob=40.0)
    plc = rig("two-tanks-cascade.plcy", m)
    run(plc, 240)
    assert abs(m.level2 - 40.0) < 3.0, (m.level1, m.level2)
    assert not m.events


def test_garage_door_example_opens_closes_and_reverses_for_a_car():
    m = GarageModel()
    plc = rig("garage-door.plcy", m)
    m.open_pressed = True
    run(plc, 0.1)
    m.open_pressed = False
    run(plc, 3)
    assert 0 < m.position < 100 and m.up
    run(plc, 9)
    assert m.position == 100.0 and not m.up and not m.events
    m.close_pressed = True
    run(plc, 0.1)
    m.close_pressed = False
    run(plc, 5)
    m.car = True                                   # a car rolls into the doorway while closing
    run(plc, 6)
    assert m.hits == 0 and m.position == 100.0, "the beam sent the door back up"
    m.car = False
    m.close_pressed = True
    run(plc, 0.1)
    m.close_pressed = False
    run(plc, 12)
    assert m.position == 0.0 and not m.events and m.lamp(3), "closed; the courtesy light is still on"


def test_garage_reports_crash_and_end_stop():
    m = GarageModel(position=50.0, car=True)
    m.set_output_words({2: 0b10})
    for _ in range(300):
        m.step(10)
    assert m.hits == 1 and "The door hit the car" in m.events
    m = GarageModel(position=100.0)
    m.set_output_words({2: 0b01})
    m.step(10)
    assert "Motor kept pushing at the open end stop" in m.events


def test_mixer_example_makes_good_batches():
    m = MixerModel()
    plc = rig("batch-mixer-st.plcy", m)
    m.start_pressed = True
    run(plc, 0.1)
    m.start_pressed = False
    run(plc, 90)
    assert len(m.batches) >= 2 and all(b.good for b in m.batches), m.batches
    assert m.spilled == 0 and not any("dry" in e or "overflowed" in e for e in m.events)


def test_mixer_grades_a_bad_batch():
    m = MixerModel(a=90.0)
    m.set_output_words({2: 1 << 4})
    for _ in range(1000):
        m.step(10)
    assert m.batches and not m.batches[0].good, "only A, cold, not mixed"
