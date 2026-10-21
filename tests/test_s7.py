"""S7-1200/1500 profile (TIA Portal style): %I/%Q/%M, PLC tags, IEC timer and counter instances."""

import pytest

from plcyard.core import profiles
from plcyard.core.processor import Processor
from plcyard.core.profiles.s7.memory import S7Error, S7Memory, parse_time
from plcyard.core.program import Program, ProgramFile, Rung
from plcyard.formats import plcy, rsl
from plcyard.sims.io_panel import IoPanelModel


def prog(rungs, tags=None):
    p = Program(profile="s7", tags=tags or {})
    p.files[2] = ProgramFile(2, "LAD", "Main", rungs=[Rung(rsl.parse_rung_text(r)) for r in rungs])
    return p


def rig(rungs, tags=None):
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    problems = plc.download(prog(rungs, tags))
    assert problems == [], [str(x) for x in problems]
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    return plc, panel


def run(plc, ms):
    for _ in range(int(ms // 10)):
        plc.tick(10)


# -- memory --------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,ms", [("T#5s", 5000), ("T#500ms", 500), ("T#1m30s", 90000), ("t#2s_500ms", 2500),
                                     ("T#1h", 3600000), ("5s", None), ("T#", None)])
def test_time_literals(text, ms):
    assert parse_time(text) == ms


def test_absolute_addresses_are_big_endian_bytes():
    m = S7Memory()
    m.write_bit("%M0.0", True)
    m.write_bit("M1.0", True)
    assert m.read_word("%MW0") == 0x0101 and m.read_word("%MB1") == 1
    m.write_word("%MW10", -2)
    assert m.read_word("%MB10") == 0xFF and m.read_word("%MW10") == -2
    m.write_word("%MD20", 100000)
    assert m.read_word("%MD20") == 100000
    assert m.write_word("%MW30", 40000) is True and m.read_word("%MW30") == 40000 - 65536


def test_symbolic_tags_share_storage_with_addresses():
    m = S7Memory({"Motor": {"type": "Bool", "address": "%Q0.0"}, "Speed": {"type": "Real", "address": "%MD4"},
                  "Count": {"type": "Int"}, "Delay": {"type": "IEC_TIMER"}})
    m.write_bit('"Motor"', True)
    assert m.read_bit("%Q0.0")
    m.write_word("Speed", 1.5)
    assert m.read_word("Speed") == 1.5 and m.read_word("%MD4") != 0
    m.write_word("Count", 7)
    assert m.read_word("count") == 7
    assert m.ref("Delay.Q").type == "Bool" and m.ref("Delay.ET").type == "Time"


@pytest.mark.parametrize("decls,msg", [
    ({"A": {"type": "Bool", "address": "%MW0"}}, "needs a bit address"),
    ({"A": {"type": "Int", "address": "%M0.0"}}, "needs a word"),
    ({"A": {"type": "DInt", "address": "%MW0"}}, "double word"),
    ({"A": {"type": "IEC_TIMER", "address": "%MD0"}}, "have no address"),
    ({"A": {"type": "Word"}}, "unknown type"),
    ({"A": {"type": "Bool", "address": "%M999.0"}}, "outside"),
])
def test_bad_tags(decls, msg):
    with pytest.raises(S7Error, match=msg):
        S7Memory(decls)


# -- download and running ---------------------------------------------------------------------------
def test_download_reports_problems():
    problems = Processor().download(prog(["XIC,Ghost OTE,%Q0.0", "TON,Motor,T#5s", "MOVE,1,%IW0"],
                                         {"Motor": {"type": "Bool", "address": "%Q0.1"}}))
    text = " ".join(str(p) for p in problems)
    assert "Ghost does not exist" in text and "Motor is a Bool" in text and "read-only" in text


def test_panel_channels_map_to_bytes():
    plc, panel = rig(["XIC,%I0.0 OTE,%Q0.0", "XIC,%I1.1 OTE,%Q1.2"])
    s7 = profiles.get("s7")
    assert s7.io_name("I", 1, 0) == "%I0.0" and s7.io_name("I", 1, 9) == "%I1.1" and s7.io_name("O", 4, 3) == "%Q2.3"
    panel.set_pressed(1, 0, True)
    panel.set_pressed(1, 9, True)
    run(plc, 20)
    assert panel.lamp(2, 0) and panel.lamp(2, 10)
    assert plc.dt.read_word("%IW0") == 0x0102, "channel 0 is %I0.0, the high byte of %IW0"


def test_thumbwheels_and_display_are_words():
    plc, panel = rig(["MOVE,%IW4,%QW4"])
    panel.thumbwheels = [1, 2, 3, 4]
    run(plc, 20)
    assert panel.outputs.get(6) == 0x1234


def test_ton_box_passes_q_to_a_coil():
    plc, panel = rig(["XIC,%I0.0 TON,Delay,T#1s OTE,%Q0.0"], {"Delay": {"type": "IEC_TIMER"}})
    panel.set_pressed(1, 0, True)
    run(plc, 600)
    d = plc.dt.element("Delay")
    assert 580 <= d["ET"] <= 600 and not panel.lamp(2, 0)
    run(plc, 500)
    assert d["Q"] and d["ET"] == 1000 and panel.lamp(2, 0)
    panel.set_pressed(1, 0, False)
    run(plc, 20)
    assert d["ET"] == 0 and not panel.lamp(2, 0)


def test_tof_and_tp():
    plc, panel = rig(["XIC,%I0.0 TOF,Off,T#300ms OTE,%Q0.0", "XIC,%I0.1 TP,Pulse,T#200ms OTE,%Q0.1"],
                     {"Off": {"type": "IEC_TIMER"}, "Pulse": {"type": "IEC_TIMER"}})
    panel.set_pressed(1, 0, True)
    run(plc, 20)
    panel.set_pressed(1, 0, False)
    run(plc, 200)
    assert panel.lamp(2, 0), "still on while the off delay runs"
    run(plc, 150)
    assert not panel.lamp(2, 0)
    panel.set_pressed(1, 1, True)
    run(plc, 20)
    panel.set_pressed(1, 1, False)                  # a short press still gives the full pulse
    run(plc, 100)
    assert panel.lamp(2, 1)
    run(plc, 120)
    assert not panel.lamp(2, 1)


def test_ctu_with_reset_and_first_scan():
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    plc.download(prog(["XIC,%I0.0 CTU,Parts,3,%I0.1 OTE,%Q0.0"], {"Parts": {"type": "IEC_COUNTER"}}))
    panel.set_pressed(1, 0, True)
    plc.set_mode(Processor.RUN)
    run(plc, 30)
    parts = plc.dt.element("Parts")
    assert parts["CV"] == 0, "no count on the first scan"
    for _ in range(3):
        panel.set_pressed(1, 0, False)
        run(plc, 20)
        panel.set_pressed(1, 0, True)
        run(plc, 20)
    assert parts["CV"] == 3 and panel.lamp(2, 0)
    panel.set_pressed(1, 1, True)
    run(plc, 20)
    assert parts["CV"] == 0 and not panel.lamp(2, 0)


def test_edge_contact_and_set_reset():
    plc, panel = rig(["P,%I0.0,%M10.0 ADD,Count,1,Count", "XIC,%I0.1 OTL,%Q0.0", "XIC,%I0.2 OTU,%Q0.0"],
                     {"Count": {"type": "Int"}})
    panel.set_pressed(1, 0, True)
    run(plc, 100)
    assert plc.dt.read_word("Count") == 1
    panel.set_pressed(1, 1, True)
    run(plc, 20)
    panel.set_pressed(1, 1, False)
    run(plc, 20)
    assert panel.lamp(2, 0)
    panel.set_pressed(1, 2, True)
    run(plc, 20)
    assert not panel.lamp(2, 0)


def test_math_eno_and_scaling():
    plc, _ = rig(["DIV,7,0,%MW0 OTE,%M20.0", "ADD,32767,1,%MW2 OTE,%M20.1", "MUL,6,7,%MW4 OTE,%M20.2",
                  "NORM_X,0,%MW8,27648,Norm SCALE_X,0.0,Norm,100.0,Pct", "CMP>=,%MW4,42 IN_RANGE,0,%MW4,50 OTE,%M20.3"],
                 {"Norm": {"type": "Real"}, "Pct": {"type": "Real"}})
    dt = plc.dt
    assert not dt.read_bit("%M20.0") and dt.read_word("%MW0") == 0, "divide by zero: ENO 0, OUT unchanged"
    assert not dt.read_bit("%M20.1"), "overflow: ENO 0"
    assert dt.read_bit("%M20.2") and dt.read_word("%MW4") == 42
    assert dt.read_bit("%M20.3")
    dt.write_word("%MW8", 13824)
    run(plc, 20)
    assert abs(dt.read_word("Pct") - 50.0) < 0.01


def test_first_scan():
    plc, _ = rig(["XIC,FirstScan OTL,%M0.0", "XIC,FirstScan ADD,%MW2,1,%MW2"])
    run(plc, 100)
    assert plc.dt.read_bit("%M0.0") and plc.dt.read_word("%MW2") == 1


def test_project_round_trip(tmp_path):
    p = prog(["XIC,Start OTE,Motor"], {"Start": {"type": "Bool", "address": "%I0.0"},
                                       "Motor": {"type": "Bool", "address": "%Q0.0"}})
    plcy.save(p, tmp_path / "x.plcy")
    back = plcy.load(tmp_path / "x.plcy")
    assert back.profile == "s7" and back.tags == p.tags
    assert Processor().download(back) == []


def test_editor_normalises_addresses_and_quotes():
    s7 = profiles.get("s7")
    assert s7.normalize("i0.0") == "%I0.0" and s7.normalize('"Motor"') == "Motor" and s7.normalize("Motor") == "Motor"
    assert s7.validate("TON", ["Delay", "5s"], prog([], {"Delay": {"type": "IEC_TIMER"}}))[0].endswith(
        "write it like T#5s or T#500ms")
