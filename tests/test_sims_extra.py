"""Elevator, bottle line, sorter, pick and place, parking garage, pump station, room climate and
washing machine: each example program does its job on its simulation, with no events."""

from plcyard import formats, labs
from plcyard.core.processor import Processor
from plcyard.sims import MODELS


def rig(name, kind, **state):
    model = MODELS[kind][1]()
    for k, v in state.items():
        setattr(model, k, v)
    plc = Processor()
    plc.device = model
    problems = plc.download(formats.load(labs.SAMPLES / name))
    assert problems == [], [str(p) for p in problems]
    plc.set_mode(Processor.RUN)
    return plc, model


def run(plc, seconds):
    for _ in range(int(seconds * 100)):
        plc.tick(10)


def tap(plc, model, attr):
    setattr(model, attr, True)
    run(plc, 0.1)
    setattr(model, attr, False)


def test_elevator_serves_calls_and_reopens_for_a_passenger():
    plc, m = rig("elevator-st.plcy", "elevator")
    run(plc, 0.2)
    m.press_hall(2, True)
    run(plc, 0.1)
    m.press_hall(2, False)
    m.car[1] = True
    run(plc, 0.1)
    m.car[1] = False
    run(plc, 20)
    assert m.served == 1 and m.floor_at() == 2, "went up to floor 3"
    m.press_hall(0, True)
    run(plc, 0.1)
    m.press_hall(0, False)
    run(plc, 4.5)
    m.blocked = True                                # someone steps in while the door closes
    run(plc, 2)
    m.blocked = False
    run(plc, 25)
    assert m.served == 2 and m.floor_at() == 0 and m.door <= 0.0
    assert not m.events, m.events


def test_bottle_line_ships_good_bottles_and_rejects_bad_caps():
    plc, m = rig("bottle-line-st.plcy", "bottles")
    tap(plc, m, "start_pressed")
    run(plc, 90)
    assert m.shipped_good >= 10 and m.shipped_bad == 0 and m.rejected_good == 0 and m.rejected_bad >= 2
    assert m.spilled == 0 and not m.events, m.events


def test_sorter_puts_every_box_in_its_bin():
    plc, m = rig("sorting-conveyor-st.plcy", "sorter")
    tap(plc, m, "start_pressed")
    run(plc, 60)
    assert all(len(m.bins[k]) >= 5 for k in (1, 2, 3)) and m.wrong == 0 and m.fallen == 0, (m.bins, m.events)


def test_pick_and_place_cycles_without_dropping():
    plc, m = rig("pick-and-place-st.plcy", "pick_place")
    tap(plc, m, "start_pressed")
    run(plc, 60)
    assert m.placed >= 6 and m.dropped == 0 and not m.events, (m.placed, m.events)


def test_parking_counts_and_turns_cars_away_when_full():
    plc, m = rig("parking-garage-st.plcy", "parking")
    for _ in range(9):
        m.car_arrives()
    run(plc, 40)
    assert m.parked == 10 and m.entry_queue == 2 and m.lamp(2), "full: two cars wait outside"
    assert m.display == 0
    m.car_leaves()
    run(plc, 10)
    assert m.parked == 10 and m.left == 1 and m.entry_queue == 1, "one out, one of the waiting cars in"
    assert not m.events, m.events


def test_pump_station_alternates_and_covers_a_failed_pump():
    plc, m = rig("pump-station-st.plcy", "pumps", inflow=45.0)
    run(plc, 300)
    assert m.starts[0] >= 2 and m.starts[1] >= 2 and abs(m.starts[0] - m.starts[1]) <= 1, (m.starts, m.run_s)
    assert m.overflowed == 0
    m.fault[0] = True
    run(plc, 200)
    assert m.overflowed == 0 and m.lamp(2), "pump 2 alone keeps up; the alarm shows the fault"
    m.fault[0] = False
    tap(plc, m, "reset_pressed")
    run(plc, 1)
    assert not m.lamp(2)
    assert not m.events, m.events


def test_room_climate_heats_and_cools_to_the_setpoint():
    plc, m = rig("room-climate-st.plcy", "hvac", temperature=16.0, setpoint_knob=21.0, outside=8.0)
    tap(plc, m, "on_pressed")
    run(plc, 240)
    assert abs(m.temperature - 21.0) < 0.6, m.temperature
    m.outside, m.setpoint_knob = 32.0, 19.0
    run(plc, 300)
    assert abs(m.temperature - 19.0) < 0.6 and m.cooler > 0, m.temperature
    assert not m.events, m.events


def test_washing_machine_runs_a_full_cycle():
    plc, m = rig("washing-machine-st.plcy", "washer")
    tap(plc, m, "start_pressed")
    run(plc, 70)
    assert m.cycles == 1 and not m.out(0) and m.water == 0.0, (m.cycles, m.washed_left_s, m.washed_right_s, m.spun_s)
    assert not m.events, m.events
