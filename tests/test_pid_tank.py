"""PID core, tank level simulation and the analog loop on every controller."""

import pytest

from plcyard.core import pid
from plcyard.core.processor import Processor
from plcyard.core.program import Program, ProgramFile, Rung
from plcyard.formats import rsl
from plcyard.sims.tank import HIGH, LOW, TankModel


# -- PID core ---------------------------------------------------------------------------------
class FirstOrder:
    """PV approaches CV with a 5 s time constant: a plant with no integral action of its own."""

    def __init__(self):
        self.pv = 0.0

    def step(self, cv, dt):
        self.pv += (cv - self.pv) * dt / 5.0


def loop(seconds, sp=50.0, **gains):
    plant, state = FirstOrder(), {}
    for _ in range(int(seconds * 10)):
        cv = pid.step(state, sp, plant.pv, 0.1, **gains)
        plant.step(cv, 0.1)
    return plant.pv, state


def test_proportional_only_leaves_an_offset():
    pv, _ = loop(60, kc=2.0, ti=0.0, td=0.0)
    assert 30 < pv < 40, "P-only settles at Kc/(1+Kc) of the setpoint"


def test_integral_removes_the_offset():
    pv, _ = loop(60, kc=2.0, ti=5.0, td=0.0)
    assert abs(pv - 50) < 0.5


def test_output_limits_and_anti_windup():
    state = {}
    for _ in range(1000):                      # PV stuck far below SP: output saturates
        cv = pid.step(state, 100.0, 0.0, 0.1, kc=1.0, ti=1.0, td=0.0)
    assert cv == 100.0 and state["I"] <= 100.0, "integral stops growing at the limit"
    cv = pid.step(state, 0.0, 50.0, 0.1, kc=1.0, ti=1.0, td=0.0)
    assert cv < 100.0, "comes off the limit at once when the error reverses"


def test_manual_is_bumpless():
    state = {}
    pid.step(state, 50, 40, 0.1, kc=2.0, ti=10.0, td=0.0, manual=True, manual_value=30.0)
    cv = pid.step(state, 50, 40, 0.1, kc=2.0, ti=10.0, td=0.0)
    assert abs(cv - 30.0) < 1.0, "back in automatic, CV starts from the manual value"


def test_reverse_acting():
    state = {}
    assert pid.step(state, 50, 60, 0.1, kc=1.0, ti=0.0, td=0.0, reverse=True) == 10.0


def test_derivative_on_pv_has_no_setpoint_kick():
    state = {}
    pid.step(state, 50, 50, 0.1, kc=1.0, ti=0.0, td=1.0)
    cv = pid.step(state, 80, 50, 0.1, kc=1.0, ti=0.0, td=1.0)
    assert cv == 30.0, "a setpoint step moves only P"


# -- tank ----------------------------------------------------------------------------------------
def test_tank_dead_time_switches_and_overflow():
    t = TankModel(level=50.0, outlet=0.0)
    t.set_output_words({2: 1})                 # pump on
    for _ in range(90):
        t.step(10)
    assert abs(t.level - 50.0) < 1e-9, "nothing arrives before the 1 s pipe delay"
    for _ in range(2000):
        t.step(10)
    assert t.level == 100.0 and t.overflowed > 0
    assert t.input_words()[1] & 0b0100 and not t.input_words()[1] & 0b1000
    t2 = TankModel(level=5.0)
    assert t2.input_words()[1] & 0b1000 and t2.input_words()[1] & 0b0010, "low switch on; Stop is NC"
    assert t2.analog_inputs() == {0: 0.5, 1: 5.0}


def test_tank_drains_through_the_outlet():
    t = TankModel(level=80.0, outlet=100.0)
    for _ in range(3000):
        t.step(10)
    assert t.level < 30.0


# -- the analog loop on each controller ---------------------------------------------------------------
def settle(plc, tank, seconds):
    for _ in range(int(seconds * 100)):
        plc.tick(10)
    return tank.level


def program(rungs, tags=None):
    p = Program(tags=tags or {})
    p.files[2] = ProgramFile(2, "LAD", "Main", rungs=[Rung(rsl.parse_rung_text(r)) for r in rungs])
    return p


def run(prog, sp=60.0):
    plc, tank = Processor(), TankModel(level=20.0, setpoint_knob=sp)
    plc.device = tank
    problems = plc.download(prog)
    assert problems == [], [str(x) for x in problems]
    plc.set_mode(Processor.RUN)
    return plc, tank


def test_pid_holds_the_level_through_a_disturbance():
    plc, tank = run(program([
        "DIV,%IW64,276.48,PV", "DIV,%IW66,276.48,LevelPID.SP",
        "PID,LevelPID,PV,Out", "MUL,Out,276.48,%QW64"],
        {"PV": {"type": "REAL"}, "Out": {"type": "REAL"},
         "LevelPID": {"type": "PID", "value": {"KP": 4, "TI": 15}}}))
    assert abs(settle(plc, tank, 60) - 60) < 2
    tank.outlet = 90.0
    assert abs(settle(plc, tank, 60) - 60) < 2
    assert plc.dt.element("LevelPID")["SP"] == pytest.approx(60.0, abs=0.01)


def test_pid_with_setpoint_operand_and_normalize_scale():
    plc, tank = run(program([
        "NORM_X,0,%IW64,27648,Norm SCALE_X,0.0,Norm,100.0,Level",
        "NORM_X,0,%IW66,27648,NormSp SCALE_X,0.0,NormSp,100.0,Setpoint",
        "PID,LevelPID,Level,Out,Setpoint",
        "NORM_X,0.0,Out,100.0,NormOut SCALE_X,0,NormOut,27648,%QW64"],
        {"Norm": {"type": "REAL"}, "Level": {"type": "REAL"}, "NormSp": {"type": "REAL"},
         "Setpoint": {"type": "REAL"}, "Out": {"type": "REAL"}, "NormOut": {"type": "REAL"},
         "LevelPID": {"type": "PID", "value": {"KP": 4, "TI": 15}}}), sp=40.0)
    assert abs(settle(plc, tank, 80) - 40) < 2
    assert plc.dt.read_word("%IW66") == round(0.4 * 27648)


def test_on_off_control_with_hysteresis():
    plc, tank = run(program([
        "LES,%IW64,11059 OTL,%M0.0",                 # below 40 % (11059 of 27648): pump on
        "GRT,%IW64,16589 OTU,%M0.0",                 # above 60 %: pump off
        "XIC,%M0.0 OTE,%Q0.0"]))
    lo, hi = 100.0, 0.0
    settle(plc, tank, 60)
    for _ in range(6000):
        plc.tick(10)
        lo, hi = min(lo, tank.level), max(hi, tank.level)
    assert 30 < lo < 42 and 58 < hi < 70, (lo, hi)


def test_analog_output_drives_the_valve():
    plc, tank = run(program(["MOV,13824,%QW64"]))
    settle(plc, tank, 1)
    assert tank.valve == pytest.approx(50.0, abs=0.1)


def test_module_names_reach_the_same_channels():
    plc, tank = run(program(["MOV,Local:7:I.Ch0Data,Raw", "MOV,27648,Local:8:O.Ch0Data"], {"Raw": {"type": "INT"}}))
    settle(plc, tank, 1)
    assert plc.dt.read_word("Raw") == plc.dt.read_word("%IW64") and tank.valve == pytest.approx(100.0, abs=0.1)
