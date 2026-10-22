"""The eleven newer machines for the web version, described as data: the controls on the page, the
devices with their addresses (from each model's wiring), and what the drawing needs. No Qt."""

from __future__ import annotations

from .core.plc import PLC
from .sims import bottles as B
from .sims import elevator as E
from .sims import mixer as X
from .sims import pump_station as S
from .sims import sorter as O
from .sims import two_tanks as W
from .ui import notation


def _hold(attr, label, nc=False):
    return {"t": "hold", "act": attr, "label": label, "nc": nc}


def _check(attr, label):
    return {"t": "check", "act": attr, "label": label}


def _slider(attr, label, lo=0, hi=100, unit="%"):
    return {"t": "slider", "act": attr, "label": label, "min": lo, "max": hi, "unit": unit}


START_STOP = [_hold("start_pressed", "Start"), _hold("stop_pressed", "Stop", nc=True)]
PCT = lambda v: f"{v * 10:.0f} %"          # 0-10 V = 0-100 %

# kind → controls, digital inputs (label, point), digital outputs, analog inputs (label, channel, volts →
# text), analog outputs (label, channel, model → text)
SPEC = {
    "two_tanks": (START_STOP + [_slider("setpoint_knob", "Setpoint knob"), _slider("outlet", "Outlet of tank 2 (disturbance)")],
                  [("Start (NO)", 0), ("Stop (NC)", 1), ("Tank 1 high (≥ 90 %)", 2), ("Tank 2 high (≥ 90 %)", 3),
                   ("Tank 2 low (≤ 10 %)", 4)],
                  [("Feed pump", 0), ("Run lamp", 1), ("Alarm lamp", 2)],
                  [("Tank 1 level", 0, PCT), ("Tank 2 level", 1, PCT), ("Setpoint knob", 2, PCT)],
                  [("Inlet valve", 0, lambda m: f"{m.inlet:.0f} %"), ("Transfer valve", 1, lambda m: f"{m.transfer:.0f} %")]),
    "garage": ([_hold("open_pressed", "Open"), _hold("close_pressed", "Close"), _hold("stop_pressed", "Stop", nc=True),
                _check("car", "Car in the doorway")],
               [("Open button (NO)", 0), ("Close button (NO)", 1), ("Stop button (NC)", 2), ("Open limit", 3),
                ("Closed limit", 4), ("Photo-eye beam clear", 5)],
               [("Motor up", 0), ("Motor down", 1), ("Warning light", 2), ("Courtesy light", 3)], [], []),
    "mixer": (START_STOP,
              [("Start (NO)", 0), ("Stop (NC)", 1), ("Low level (≥ 5 %)", 2), ("Middle level (≥ 50 %)", 3),
               ("High level (≥ 90 %)", 4)],
              [("Valve A", 0), ("Valve B", 1), ("Mixer motor", 2), ("Heater", 3), ("Drain valve", 4), ("Batch done lamp", 5)],
              [("Temperature 0-10 V = 0-100 °C", 0, lambda v: f"{v * 10:.1f} °C")], []),
    "elevator": ([_hold(f"hall_{k}", f"Call {k + 1}") for k in range(3)] + [_hold(f"car_{k}", f"Car {k + 1}") for k in range(3)]
                 + [_check("blocked", "Someone in the doorway")],
                 [("Hall call floor 1", 0), ("Hall call floor 2", 1), ("Hall call floor 3", 2), ("Car button floor 1", 3),
                  ("Car button floor 2", 4), ("Car button floor 3", 5), ("Car at floor 1", 6), ("Car at floor 2", 7),
                  ("Car at floor 3", 8), ("Door open limit", 9), ("Door closed limit", 10), ("Door safety edge clear", 11),
                  ("Top overtravel OK", 12), ("Bottom overtravel OK", 13)],
                 [("Motor up", 0), ("Motor down", 1), ("Door open", 2), ("Door close", 3), ("Lamp floor 1", 4),
                  ("Lamp floor 2", 5), ("Lamp floor 3", 6)], [], []),
    "bottles": (START_STOP,
                [("Start (NO)", 0), ("Stop (NC)", 1), ("Bottle at the filler", 2), ("Bottle full", 3),
                 ("Bottle at the capper", 4), ("Bottle at inspection", 5), ("Bottle at inspection is good", 6)],
                [("Conveyor", 0), ("Fill valve", 1), ("Capper press", 2), ("Reject pusher", 3), ("Run lamp", 4)], [], []),
    "sorter": (START_STOP,
               [("Start (NO)", 0), ("Stop (NC)", 1), ("Box at the measuring point", 2), ("Low beam blocked", 3),
                ("High beam blocked", 4), ("Box at pusher 1", 5), ("Box at pusher 2", 6), ("Box at pusher 3", 7)],
               [("Conveyor", 0), ("Pusher 1 (small)", 1), ("Pusher 2 (medium)", 2), ("Pusher 3 (large)", 3), ("Run lamp", 4)],
               [], []),
    "pick_place": (START_STOP,
                   [("Start (NO)", 0), ("Stop (NC)", 1), ("Arm at pick side", 2), ("Arm at place side", 3), ("Arm up", 4),
                    ("Arm down", 5), ("Part waiting", 6), ("Vacuum OK (part held)", 7)],
                   [("Horizontal: extend", 0), ("Vertical: down", 1), ("Vacuum", 2), ("Cycle lamp", 3)], [], []),
    "parking": ([{"t": "button", "act": "car_arrives", "label": "Car arrives"},
                 {"t": "button", "act": "car_leaves", "label": "Car leaves"},
                 _check("traffic", "Traffic (cars come and go by themselves)")],
                [("Car waiting at the entry", 0), ("Car passed the entry barrier", 1), ("Car waiting at the exit", 2),
                 ("Car passed the exit barrier", 3), ("Entry barrier up", 4), ("Exit barrier up", 5)],
                [("Raise entry barrier", 0), ("Raise exit barrier", 1), ("FULL sign", 2)], [], []),
    "pumps": ([_hold("reset_pressed", "Reset alarm"), _hold("stop_pressed", "Stop", nc=True), _slider("inflow", "Inflow"),
               _check("fault_0", "Pump 1 fails"), _check("fault_1", "Pump 2 fails")],
              [("Reset alarm (NO)", 0), ("Stop (NC)", 1), ("Low level (≥ 15 %)", 2), ("Start level (≥ 50 %)", 3),
               ("High level (≥ 75 %)", 4), ("Overflow alarm level (≥ 95 %)", 5), ("Pump 1 fault", 6), ("Pump 2 fault", 7)],
              [("Pump 1", 0), ("Pump 2", 1), ("Alarm lamp", 2)], [("Level 0-10 V = 0-100 %", 0, PCT)], []),
    "hvac": ([_hold("on_pressed", "On"), _hold("off_pressed", "Off", nc=True), _check("window", "Window open"),
              _slider("setpoint_knob", "Setpoint knob", 0, 50, "°C"), _slider("outside", "Outside", -10, 40, "°C")],
             [("System on (NO)", 0), ("System off (NC)", 1), ("Window open", 2), ("Airflow (fan running)", 3)],
             [("Fan", 0), ("Heating lamp", 1), ("Cooling lamp", 2)],
             [("Room 0-10 V = 0-50 °C", 0, lambda v: f"{v * 5:.1f} °C"), ("Setpoint 0-10 V = 0-50 °C", 1, lambda v: f"{v * 5:.1f} °C")],
             [("Heater", 0, lambda m: f"{m.heater:.0f} %"), ("Cooler", 1, lambda m: f"{m.cooler:.0f} %")]),
    "washer": (START_STOP + [_check("door_closed", "Door closed")],
               [("Start (NO)", 0), ("Stop (NC)", 1), ("Door closed", 2), ("Door locked", 3), ("Water present (≥ 10 %)", 4),
                ("Water full (≥ 80 %)", 5), ("Drum stopped", 6)],
               [("Door lock", 0), ("Fill valve", 1), ("Wash left", 2), ("Wash right", 3), ("Spin", 4), ("Drain pump", 5),
                ("Done lamp", 6)], [], []),
}


def act(m, kind: str, name: str, value) -> None:
    """A control of the page, checked against the machine's controls."""
    ctl = next((c for c in SPEC[kind][0] if c["act"] == name), None)
    if ctl is None:
        return
    if ctl["t"] == "button":
        getattr(m, name)()
    elif ctl["t"] == "slider":
        setattr(m, name, min(max(float(value), ctl["min"]), ctl["max"]))
    elif kind == "elevator" and name.startswith(("hall_", "car_")):
        k = int(name[-1])
        m.press_hall(k, bool(value)) if name.startswith("hall_") else m.car.__setitem__(k, bool(value))
    elif kind == "pumps" and name.startswith("fault_"):
        m.fault[int(name[-1])] = bool(value)
    else:
        setattr(m, name, bool(value))


def _value(m, kind, c):
    if c["t"] == "slider":
        return getattr(m, c["act"])
    if c["t"] == "check":
        return m.fault[int(c["act"][-1])] if kind == "pumps" and c["act"].startswith("fault_") else bool(getattr(m, c["act"]))
    if kind == "elevator" and c["act"].startswith(("hall_", "car_")):
        return (m.hall if c["act"].startswith("hall_") else m.car)[int(c["act"][-1])]
    return bool(getattr(m, c["act"], False))


def view(m, kind: str) -> dict:
    controls, ins, outs, ains, aouts = SPEC[kind]
    word, q = m.input_words().get(1, 0), m.outputs
    volts = m.analog_inputs() if hasattr(m, "analog_inputs") else {}
    i = lambda bit: notation.show(PLC.io_name("I", 1, bit))
    o = lambda bit: notation.show(PLC.io_name("Q", 2, bit))
    devices = {"inputs": [[label, i(b), bool(word >> b & 1)] for label, b in ins] +
                         [[label, notation.show(PLC.analog_name("I", ch)), fmt(volts.get(ch, 0.0))] for label, ch, fmt in ains],
               "outputs": [[label, o(b), bool(q >> b & 1)] for label, b in outs] +
                          [[label, notation.show(PLC.analog_name("Q", ch)), fmt(m)] for label, ch, fmt in aouts]}
    if kind == "parking":
        devices["outputs"].append(["Free spaces display (BCD)", notation.show(PLC.io_name("Q", 6)),
                                   str(m.display) if m.display >= 0 else "--"])
    return {"kind": kind, "events": list(m.events)[-4:], "devices": devices,
            "controls": [{**c, "value": _value(m, kind, c)} for c in controls], "draw": DRAW[kind](m)}


def _outs(m, n: int) -> list[bool]:
    return [bool(m.outputs >> b & 1) for b in range(n)]


DRAW = {
    "two_tanks": lambda m: {"level1": m.level1, "level2": m.level2, "inlet": m.inlet, "transfer": m.transfer,
                            "outlet": m.outlet, "pump": m.pump, "setpoint": m.setpoint_knob, "high": W.HIGH, "low": W.LOW,
                            "lamps": [m.lamp(1), m.lamp(2)],
                            "trend": [[round(t, 1), sp, round(a, 2), round(b, 2)] for t, sp, a, b, _, _ in list(m.trend)[::5]]},
    "garage": lambda m: {"position": m.position, "up": m.up, "down": m.down, "car": m.car, "warning": m.lamp(2),
                         "light": m.lamp(3), "hits": m.hits, "cycles": m.cycles},
    "mixer": lambda m: {"a": m.a, "b": m.b, "temperature": m.temperature, "outs": _outs(m, 6), "angle": m.angle,
                        "mixed": m.mixed_s, "levels": [X.LOW, X.MID, X.HIGH], "batches": len(m.batches),
                        "good": sum(1 for b in m.batches if b.good)},
    "elevator": lambda m: {"position": m.position, "floor": E.FLOOR, "door": m.door, "outs": _outs(m, 7),
                           "hall": list(m.hall), "car": list(m.car), "waiting": sorted(m.waiting), "blocked": m.blocked,
                           "served": m.served},
    "bottles": lambda m: {"bottles": [{"x": b.x, "fill": b.fill, "capped": b.capped, "bad": b.bad_cap} for b in m.bottles],
                          "length": B.LENGTH, "stations": [B.FILLER, B.CAPPER, B.INSPECT], "outs": _outs(m, 5),
                          "good": m.shipped_good, "bad": m.shipped_bad, "rejected": m.rejected_good + m.rejected_bad},
    "sorter": lambda m: {"boxes": [{"x": b.x, "size": b.size} for b in m.boxes], "length": O.LENGTH, "measure": O.MEASURE,
                         "pushers": list(O.PUSHERS), "heights": O.HEIGHT, "outs": _outs(m, 5),
                         "bins": [len(m.bins[k]) for k in (1, 2, 3)], "wrong": m.wrong, "fallen": m.fallen},
    "pick_place": lambda m: {"x": m.x, "z": m.z, "held": m.held, "waiting": m.part_waiting, "outs": _outs(m, 4),
                             "placed": m.placed, "dropped": m.dropped},
    "parking": lambda m: {"parked": m.parked, "capacity": 10, "entry_queue": m.entry_queue, "exit_queue": m.exit_queue,
                          "entry": m.entry_barrier, "exit": m.exit_barrier, "display": m.display, "full": m.lamp(2),
                          "entered": m.entered, "left": m.left},
    "pumps": lambda m: {"level": m.level, "levels": [S.LOW, S.START, S.HIGH, S.ALARM],
                        "running": [m.running(0), m.running(1)], "fault": list(m.fault), "alarm": m.lamp(2),
                        "hours": [round(x, 1) for x in m.run_s], "starts": list(m.starts)},
    "hvac": lambda m: {"temperature": m.temperature, "outside": m.outside, "setpoint": m.setpoint_knob, "window": m.window,
                       "fan": m.out(0), "heater": m.heater, "cooler": m.cooler, "lamps": [m.out(1), m.out(2)],
                       "trend": [[round(t, 1), sp, round(pv, 2), round(h, 1), round(c, 1)] for t, sp, pv, h, c in list(m.trend)[::5]]},
    "washer": lambda m: {"water": m.water, "rpm": m.rpm, "angle": m.angle, "door_closed": m.door_closed,
                         "locked": m.locked, "outs": _outs(m, 7), "left": round(m.washed_left_s, 1),
                         "right": round(m.washed_right_s, 1), "spun": round(m.spun_s, 1), "cycles": m.cycles},
}
