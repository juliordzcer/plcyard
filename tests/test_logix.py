"""Logix profile (Studio 5000 style): tags, ms timers, DINT math, module I/O."""

import pytest

from plcyard.core import profiles
from plcyard.core.processor import Processor
from plcyard.core.profiles.logix.tags import TagError, TagTable, wrap
from plcyard.core.program import Program, ProgramFile, Rung
from plcyard.formats import plcy, rsl
from plcyard.sims.io_panel import IoPanelModel

IN, OUT = "Local:1:I.Data", "Local:2:O.Data"


def prog(rungs, tags=None):
    p = Program(profile="logix", tags=tags or {})
    p.files[2] = ProgramFile(2, "LAD", rungs=[Rung(rsl.parse_rung_text(r)) for r in rungs])
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


# -- tags ---------------------------------------------------------------------------------------
def test_tag_references():
    t = TagTable({"Start": {"type": "BOOL"}, "Count": {"type": "DINT", "value": 5},
                  "Delay": {"type": "TIMER"}, "Level": {"type": "REAL"}})
    assert t.read_word("count") == 5, "names are case-insensitive"
    t.write_bit("Count.1", True)
    assert t.read_word("Count") == 7 and t.read_bit("Count.0")
    assert t.ref("Delay.DN").type == "BOOL" and t.ref("Delay.ACC").type == "DINT"
    t.write_bit(f"{OUT}.3", True)
    assert t.module_data(2, "O") == 8
    assert t.write_word("Count", 2**31) is True and t.read_word("Count") == -2**31
    t.write_word("Level", 2)
    assert t.read_word("Level") == 2.0 and isinstance(t.read_word("Level"), float)


@pytest.mark.parametrize("ref,msg", [
    ("Nope", "does not exist"), ("Delay.XX", "has no member"), ("Level.3", "only SINT, INT and DINT"),
    ("Count.32", "out of range"), ("Local:1:I.Bits", "use Local:1:I.Data"), ("3abc", "not a tag reference"),
])
def test_bad_references(ref, msg):
    t = TagTable({"Delay": {"type": "TIMER"}, "Level": {"type": "REAL"}, "Count": {"type": "DINT"}})
    with pytest.raises(TagError, match=msg):
        t.read_word(ref) if "." not in ref or ref.startswith("Local") else t.ref(ref)


@pytest.mark.parametrize("decls,msg", [
    ({"1x": {"type": "BOOL"}}, "not a valid tag name"), ({"A": {"type": "WORD"}}, "unknown type"),
    ({"A": {"type": "BOOL"}, "a": {"type": "DINT"}}, "declared twice"),
])
def test_bad_declarations(decls, msg):
    with pytest.raises(TagError, match=msg):
        TagTable(decls)


def test_wrap():
    assert wrap(32768, "INT") == (-32768, True) and wrap(5, "DINT") == (5, False)


# -- download checks ------------------------------------------------------------------------------
def test_download_reports_unknown_tags_and_wrong_types():
    problems = Processor().download(prog(["XIC,Ghost OTE,Motor", "TON,Motor,1000,0"],
                                         {"Motor": {"type": "BOOL"}}))
    text = " ".join(str(p) for p in problems)
    assert "Ghost does not exist" in text and "Motor is a BOOL" in text


def test_download_reports_bad_tag_list():
    problems = Processor().download(prog(["XIC,A OTE,B"], {"A": {"type": "WORD"}}))
    assert problems and "unknown type" in str(problems[0])


# -- running ----------------------------------------------------------------------------------------
def test_seal_in_on_module_io():
    plc, panel = rig([f"BST,1 XIC,{IN}.0 NXB,1 XIC,Motor BND,1 XIO,{IN}.1 OTE,Motor",
                      f"XIC,Motor OTE,{OUT}.0"], {"Motor": {"type": "BOOL"}})
    assert plc.profile.name == "logix"
    panel.set_pressed(1, 0, True)
    run(plc, 30)
    panel.set_pressed(1, 0, False)
    run(plc, 30)
    assert panel.lamp(2, 0), "sealed in"
    panel.set_pressed(1, 1, True)
    run(plc, 30)
    assert not panel.lamp(2, 0)


def test_ton_counts_milliseconds():
    plc, panel = rig([f"XIC,{IN}.0 TON,Delay,1500,0", f"XIC,Delay.DN OTE,{OUT}.0"], {"Delay": {"type": "TIMER"}})
    panel.set_pressed(1, 0, True)
    run(plc, 1000)
    el = plc.dt.element("Delay")
    assert 980 <= el["ACC"] <= 1000 and el["TT"] and not el["DN"]
    run(plc, 600)
    assert el["ACC"] == 1500 and el["DN"] and panel.lamp(2, 0)
    panel.set_pressed(1, 0, False)
    run(plc, 20)
    assert el["ACC"] == 0 and not el["DN"]


def test_tof_and_rto():
    plc, panel = rig([f"XIC,{IN}.0 TOF,Off,500,0", f"XIC,{IN}.1 RTO,Keep,1000,0", f"XIC,{IN}.2 RES,Keep"],
                     {"Off": {"type": "TIMER"}, "Keep": {"type": "TIMER"}})
    off, keep = plc.dt.element("Off"), plc.dt.element("Keep")
    panel.set_pressed(1, 0, True)
    run(plc, 20)
    assert off["DN"] and off["ACC"] == 0
    panel.set_pressed(1, 0, False)
    run(plc, 300)
    assert off["DN"] and off["TT"]
    run(plc, 300)
    assert not off["DN"] and off["ACC"] == 500
    panel.set_pressed(1, 1, True)
    run(plc, 400)
    panel.set_pressed(1, 1, False)
    run(plc, 200)
    assert 380 <= keep["ACC"] <= 400, "retained while the rung is false"
    panel.set_pressed(1, 2, True)
    run(plc, 20)
    assert keep["ACC"] == 0


def test_counter_does_not_count_on_first_scan_and_counts_edges():
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    plc.download(prog([f"XIC,{IN}.0 CTU,Parts,3,0", f"XIC,Parts.DN OTE,{OUT}.0"], {"Parts": {"type": "COUNTER"}}))
    panel.set_pressed(1, 0, True)                 # already on when entering RUN
    plc.set_mode(Processor.RUN)
    run(plc, 30)
    parts = plc.dt.element("Parts")
    assert parts["ACC"] == 0
    for _ in range(3):
        panel.set_pressed(1, 0, False)
        run(plc, 20)
        panel.set_pressed(1, 0, True)
        run(plc, 20)
    assert parts["ACC"] == 3 and panel.lamp(2, 0)


def test_one_shots():
    plc, panel = rig([f"XIC,{IN}.0 ONS,Mem1 ADD,Count,1,Count", f"XIC,{IN}.0 OSF,Mem2,Fell"],
                     {"Mem1": {"type": "BOOL"}, "Mem2": {"type": "BOOL"}, "Fell": {"type": "BOOL"},
                      "Count": {"type": "DINT"}})
    panel.set_pressed(1, 0, True)
    run(plc, 100)
    assert plc.dt.read_word("Count") == 1
    panel.set_pressed(1, 0, False)
    plc.tick(10)
    assert plc.dt.read_bit("Fell")
    plc.tick(10)
    assert not plc.dt.read_bit("Fell")


def test_math_compare_and_scale():
    plc, _ = rig(["MOV,7,A DIV,A,2,Q DIV,-7,2,QN MUL,A,1.5,R SCP,8192,0,32767,0,100,Pct",
                  "GRT,A,5 LES,A,10 LIM,0,A,100 OTE,InRange", "DIV,A,0,Z"],
                 {"A": {"type": "DINT"}, "Q": {"type": "DINT"}, "QN": {"type": "DINT"}, "R": {"type": "REAL"},
                  "Pct": {"type": "REAL"}, "InRange": {"type": "BOOL"}, "Z": {"type": "DINT"}})
    dt = plc.dt
    assert dt.read_word("Q") == 3 and dt.read_word("QN") == -3, "integer division truncates toward zero"
    assert dt.read_word("R") == 10.5 and abs(dt.read_word("Pct") - 25.0) < 0.01
    assert dt.read_bit("InRange")
    assert dt.read_word("Z") == 2147483647 and dt.read_bit("S:V") and plc.mode == Processor.RUN


def test_first_scan_flag():
    plc, _ = rig(["XIC,S:FS OTL,SawFirst", "XIC,S:FS ADD,N,1,N"], {"SawFirst": {"type": "BOOL"}, "N": {"type": "DINT"}})
    run(plc, 100)
    assert plc.dt.read_bit("SawFirst") and plc.dt.read_word("N") == 1


def test_negative_preset_is_a_major_fault():
    plc, _ = rig(["MOV,-5,Delay.PRE", "TON,Delay,1000,0"], {"Delay": {"type": "TIMER"}})
    run(plc, 30)
    assert plc.mode == Processor.FAULT and plc.fault_code == 0x0422


def test_tag_initial_values_and_project_round_trip(tmp_path):
    p = prog([f"XIC,{IN}.0 MOV,Speed,Out"], {"Speed": {"type": "DINT", "value": 42}, "Out": {"type": "DINT"}})
    p.symbols = {"Speed": "Conveyor speed in %"}
    plcy.save(p, tmp_path / "x.plcy")
    back = plcy.load(tmp_path / "x.plcy")
    assert back.profile == "logix" and back.tags == p.tags and back.symbols == p.symbols
    plc = Processor()
    assert plc.download(back) == [] and plc.dt.read_word("Speed") == 42


def test_editor_validation_uses_declared_tags():
    logix = profiles.get("logix")
    p = prog([], {"Motor": {"type": "BOOL"}, "Delay": {"type": "TIMER"}})
    assert logix.validate("OTE", ["Motor"], p) == []
    assert "does not exist" in logix.validate("OTE", ["Pump"], p)[0]
    assert logix.validate("OTE", ["Pump"]) == [], "without the program only the shape is checked"
    assert logix.normalize(" Motor ") == "Motor", "tag names keep their case"
