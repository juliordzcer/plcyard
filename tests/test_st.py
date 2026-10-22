"""Structured text."""

import pytest

from plcyard.core import st
from plcyard.core.processor import Processor
from plcyard.core.program import Program, ProgramFile
from plcyard.formats import plcy, rsl
from plcyard.sims.io_panel import IoPanelModel
from plcyard.sims.tank import TankModel


def prog(source, tags=None):
    p = Program(tags=tags or {})
    p.files[2] = ProgramFile(2, "LAD", "Main", language="ST", source=source)
    return p


def rig(source, tags=None, device=None):
    plc = Processor()
    plc.device = device or IoPanelModel()
    problems = plc.download(prog(source, tags))
    assert problems == [], [str(x) for x in problems]
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    return plc, plc.device


def run(plc, ms):
    for _ in range(int(ms // 10)):
        plc.tick(10)


# -- parsing --------------------------------------------------------------------------------------
@pytest.mark.parametrize("src,line,msg", [
    ("x := 1", 1, "missing ;"),
    ("x := 1;\nIF x THEN y := 2;\n", 3, "expected END_IF"),
    ("x := ;", 1, "expected a value"),
    ("CASE x OF a: y := 1; END_CASE;", 1, "whole number"),
    ("x := T#5q;", 1, "not a time"),
    ("x := LIMIT(1, 2);", 1, "LIMIT takes 3"),
    ("x := 1 $ 2;", 1, "unexpected character"),
    ("Delay.TON(IN 5);", 1, "IN := value"),
])
def test_syntax_errors_point_at_the_line(src, line, msg):
    with pytest.raises(st.StError) as e:
        st.parse(src)
    assert e.value.line == line and msg in e.value.message


def test_time_literals():
    assert st.parse_time("T#1m30s") == 90000 and st.parse_time("TIME#2s_500ms") == 2500
    assert st.parse_time("T#1.5s") == 1500


# -- download checks ------------------------------------------------------------------------------
def test_unknown_variables_and_wrong_blocks_are_reported_with_lines():
    src = "Motor := Start;\nGhost := 1;\nMotor.TON(IN := TRUE);\nDelay := 5;\n"
    problems = Processor().download(prog(src, {"Motor": {"type": "BOOL"}, "Start": {"type": "BOOL"},
                                                        "Delay": {"type": "TIMER"}}))
    text = [str(p) for p in problems]
    assert any("line 2" in t and "Ghost does not exist" in t for t in text)
    assert any("line 3" in t and "Motor is a BOOL; TON needs a TIMER" in t for t in text)
    assert any("line 4" in t and "Delay is a TIMER" in t for t in text)


# -- running -----------------------------------------------------------------------------------------
TAGS = {"Motor": {"type": "BOOL"}, "Delay": {"type": "TIMER"}, "Count": {"type": "DINT"},
              "Parts": {"type": "COUNTER"}, "i": {"type": "DINT"}, "Step": {"type": "DINT"},
              "Out": {"type": "DINT"}, "R": {"type": "REAL"}}


def test_seal_in_and_timer_call():
    src = """
    // seal-in on module I/O
    Motor := (Local:1:I.Data.0 OR Motor) AND NOT Local:1:I.Data.1;
    Delay.TON(IN := Motor, PRE := 500);
    Local:2:O.Data.0 := Delay.DN;
    """
    plc, panel = rig(src, TAGS)
    panel.set_pressed(1, 0, True)
    run(plc, 30)
    panel.set_pressed(1, 0, False)
    run(plc, 300)
    assert plc.dt.read_bit("Motor") and not panel.lamp(2, 0)
    run(plc, 300)
    assert panel.lamp(2, 0)
    panel.set_pressed(1, 1, True)
    run(plc, 30)
    assert not plc.dt.read_bit("Motor") and not panel.lamp(2, 0)


def test_control_flow():
    src = """
    Count := 0;
    FOR i := 1 TO 10 DO
        IF i = 7 THEN EXIT; END_IF;
        Count := Count + i;
    END_FOR;
    CASE Count OF
        0: Out := -1;
        1, 2: Out := 2;
        20..30: Out := 25;
    ELSE Out := 99;
    END_CASE;
    WHILE Step < 5 DO Step := Step + 2; END_WHILE;
    REPEAT R := R + 0.5; UNTIL R >= 2.0 END_REPEAT;
    """
    plc, _ = rig(src, TAGS)
    dt = plc.dt
    assert dt.read_word("Count") == 21 and dt.read_word("Out") == 25
    assert dt.read_word("Step") == 6 and dt.read_word("R") >= 2.0


def test_expressions_and_functions():
    src = """
    Out := 7 / 2 + 7 MOD 3 * 10 - -1;
    R := LIMIT(0.0, ABS(-12.5) * 2.0, 20.0) + INT_TO_REAL(3) / 2.0 + SQRT(16.0);
    Motor := (Out > 10) XOR FALSE AND NOT (R < 0.0);
    Count := 16#FF + 2#101 + MAX(3, 9) + SEL(TRUE, 100, 200);
    """
    plc, _ = rig(src, TAGS)
    dt = plc.dt
    assert dt.read_word("Out") == 3 + 10 + 1
    assert dt.read_word("R") == pytest.approx(20.0 + 1.5 + 4.0)
    assert dt.read_bit("Motor")
    assert dt.read_word("Count") == 255 + 5 + 9 + 200


def test_counter_call_and_first_scan():
    src = """
    IF S:FS THEN Out := 100; END_IF;
    Parts.CTU(CU := Local:1:I.Data.0, PRE := 3, RES := Local:1:I.Data.1);
    Local:2:O.Data.0 := Parts.DN;
    """
    plc, panel = rig(src, TAGS)
    assert plc.dt.read_word("Out") == 100
    for _ in range(3):
        panel.set_pressed(1, 0, True)
        run(plc, 20)
        panel.set_pressed(1, 0, False)
        run(plc, 20)
    assert plc.dt.element("Parts")["ACC"] == 3 and panel.lamp(2, 0)
    panel.set_pressed(1, 1, True)
    run(plc, 20)
    assert plc.dt.element("Parts")["ACC"] == 0


def test_runaway_loop_trips_the_watchdog():
    plc = Processor()
    plc.device = IoPanelModel()
    assert plc.download(prog("WHILE TRUE DO Count := Count + 1; END_WHILE;", TAGS)) == []
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    assert plc.mode == Processor.FAULT and "watchdog" in plc.fault


def test_division_by_zero_is_a_fault():
    plc = Processor()
    assert plc.download(prog("Out := 5 / Count;", TAGS)) == []
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    assert plc.mode == Processor.FAULT and "division by zero" in plc.fault


def test_absolute_addresses_quoted_names_and_iec_timer_names():
    src = """
    "Motor" := (%I0.0 OR "Motor") AND %I0.1;      // Stop is NC: TRUE when not pressed
    "Delay".TON(IN := "Motor", PT := T#300ms, Q => %Q0.1);
    %Q0.0 := "Motor";
    %MW10 := %MW10 + 1;
    """
    tags = {"Motor": {"type": "Bool", "address": "%M0.0"}, "Delay": {"type": "TIMER"}}
    panel = IoPanelModel()
    panel.switch(1, 1).normally_closed = True
    plc, _ = rig(src, tags, panel)
    panel.set_pressed(1, 0, True)
    run(plc, 20)
    panel.set_pressed(1, 0, False)
    run(plc, 200)
    assert panel.lamp(2, 0) and not panel.lamp(2, 1)
    run(plc, 200)
    assert panel.lamp(2, 1)
    assert plc.dt.read_word("%MW10") > 10


def test_pid_call_controls_the_tank():
    src = """
    "Level" := INT_TO_REAL(%IW64) / 27648.0 * 100.0;
    "Sp" := INT_TO_REAL(%IW66) / 27648.0 * 100.0;
    "LevelPID".PID(SP := "Sp", PV := "Level", CV => "Out");
    %QW64 := REAL_TO_INT("Out" / 100.0 * 27648.0);
    """
    tags = {"Level": {"type": "Real"}, "Sp": {"type": "Real"}, "Out": {"type": "Real"},
            "LevelPID": {"type": "PID", "value": {"KP": 4, "KI": 0.27}}}
    plc, tank = rig(src, tags, TankModel(level=20.0, setpoint_knob=60.0))
    run(plc, 60000)
    assert abs(tank.level - 60.0) < 2.0


def test_project_round_trip(tmp_path):
    p = prog("%Q0.0 := %I0.0;\n")
    plcy.save(p, tmp_path / "x.plcy")
    back = plcy.load(tmp_path / "x.plcy")
    assert back.main.language == "ST" and back.main.source == "%Q0.0 := %I0.0;\n"
    assert Processor().download(back) == []
