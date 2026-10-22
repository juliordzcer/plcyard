"""Several routines per program (Logix JSR, S7 FC/FB), user data types, arrays and forcing."""

import pytest

from plcyard.core.processor import Processor
from plcyard.core.profiles.logix.tags import TagError, TagTable
from plcyard.core.profiles.s7.memory import S7Error, S7Memory
from plcyard.core.program import Program, ProgramFile, Rung
from plcyard.formats import plcy, rsl
from plcyard.sims.io_panel import IoPanelModel


def ld(number, title, rungs, kind="SBR", **kw):
    return ProgramFile(number, kind, title, rungs=[Rung(rsl.parse_rung_text(r)) for r in rungs], **kw)


def st_file(number, title, source, kind="SBR", **kw):
    return ProgramFile(number, kind, title, language="ST", source=source, **kw)


def rig(profile, files, tags=None, types=None):
    p = Program(profile=profile, tags=tags or {}, types=types or {}, symbols_section=False)
    for f in files:
        p.files[f.number] = f
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    problems = plc.download(p)
    assert problems == [], [str(x) for x in problems]
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    return plc, panel


def problems(profile, files, tags=None, types=None):
    p = Program(profile=profile, tags=tags or {}, types=types or {})
    for f in files:
        p.files[f.number] = f
    return [str(x) for x in Processor().download(p)]


def run(plc, ms):
    for _ in range(int(ms // 10)):
        plc.tick(10)


# -- Logix: user-defined types and arrays ------------------------------------------------------
UDT = {"Pump": {"Run": "BOOL", "Speed": "REAL", "Delay": "TIMER", "Hours": "DINT[3]"}}


def test_logix_udt_and_array_references():
    t = TagTable({"P1": {"type": "Pump"}, "Line": {"type": "Pump[2]"}, "Recipe": {"type": "DINT[5]",
                  "value": [1, 2, 3]}, "Step": {"type": "DINT", "value": 2}}, UDT)
    assert t.read_word("Recipe[1]") == 2 and t.read_word("Recipe[Step]") == 3
    t.write_word("Line[1].Hours[2]", 7)
    assert t.read_word("line[1].hours[2]") == 7, "names and members are case-insensitive"
    t.write_bit("P1.Run", True)
    assert t.read_bit("P1.Run") and t.ref("P1.Delay.DN").type == "BOOL"
    t.write_bit("Recipe[0].3", True)
    assert t.read_word("Recipe[0]") == 9
    assert t.element("Line[0].Delay")["PRE"] == 0


@pytest.mark.parametrize("ref,msg", [
    ("Recipe[5]", "out of range"), ("Recipe.Speed", "has no member"), ("P1.Nope", "has no member"),
    ("P1[0]", "not an array"), ("Recipe[P1.Speed]", "must be a SINT, INT or DINT"),
])
def test_logix_bad_structured_references(ref, msg):
    t = TagTable({"P1": {"type": "Pump"}, "Recipe": {"type": "DINT[5]"}}, UDT)
    with pytest.raises(TagError, match=msg):
        t.ref(ref)


@pytest.mark.parametrize("types,msg", [
    ({"A": {"B": "NOPE"}}, "unknown type"), ({"A": {"X": "A"}}, "contains itself"),
    ({"TIMER": {"X": "DINT"}}, "built-in"), ({"A": {"1x": "DINT"}}, "not a valid member name"),
])
def test_logix_bad_data_types(types, msg):
    with pytest.raises(TagError, match=msg):
        TagTable({}, types)


def test_logix_indirect_address_in_ladder_and_timer_inside_a_udt():
    plc, panel = rig("logix", [ld(2, "MainRoutine", [
        "MOV,42,Recipe[Step]", "XIC,Local:1:I.Data.0 TON,P1.Delay,100,0", "XIC,P1.Delay.DN OTE,Local:2:O.Data.0"],
        kind="LAD")], tags={"P1": {"type": "Pump"}, "Recipe": {"type": "DINT[4]"}, "Step": {"type": "DINT", "value": 3}},
        types=UDT)
    assert plc.dt.read_word("Recipe[3]") == 42
    panel.set_pressed(1, 0, True)
    run(plc, 150)
    assert panel.lamp(2, 0)


def test_logix_index_out_of_range_at_run_time_is_a_major_fault():
    plc, _ = rig("logix", [ld(2, "MainRoutine", ["MOV,1,Recipe[Step]"], kind="LAD")],
                 tags={"Recipe": {"type": "DINT[4]"}, "Step": {"type": "DINT", "value": 9}})
    assert plc.mode == Processor.FAULT and "out of range" in plc.fault


# -- Logix: routines -----------------------------------------------------------------------------
def test_logix_jsr_from_ladder_and_structured_text():
    plc, panel = rig("logix", [
        ld(2, "MainRoutine", ["XIC,Local:1:I.Data.0 JSR,Motors", "JSR,Calc"], kind="LAD"),
        ld(3, "Motors", ["OTE,Local:2:O.Data.0", "RET", "OTE,Local:2:O.Data.1"]),
        st_file(4, "Calc", "Total := Total + 1;\nIF Total > 3 THEN JSR(Flags); END_IF;"),
        ld(5, "Flags", ["OTE,Local:2:O.Data.2"]),
    ], tags={"Total": {"type": "DINT"}})
    assert not panel.lamp(2, 0)
    panel.set_pressed(1, 0, True)
    run(plc, 50)
    assert panel.lamp(2, 0) and not panel.lamp(2, 1), "RET leaves the routine"
    assert plc.dt.read_word("Total") > 3 and panel.lamp(2, 2)


def test_logix_unknown_routine_is_reported():
    msgs = problems("logix", [ld(2, "MainRoutine", ["JSR,Nope"], kind="LAD"),
                              st_file(3, "Calc", "JSR(Missing);")])
    assert any("routine Nope does not exist" in m for m in msgs)
    assert any("routine Missing does not exist" in m for m in msgs)


def test_runaway_recursion_is_a_fault():
    plc, _ = rig("logix", [ld(2, "MainRoutine", ["JSR,Loop"], kind="LAD"), ld(3, "Loop", ["JSR,Loop"])])
    assert plc.mode == Processor.FAULT and "nested deeper" in plc.fault


def test_logix_pid_operands_as_in_studio_5000():
    tags = {"Outer": {"type": "PID", "value": {"KP": 0}}, "Inner": {"type": "PID", "value": {"KP": 1}},
            "Hold": {"type": "BOOL", "value": True}, "Out": {"type": "REAL"}, "Out2": {"type": "REAL"}}
    plc, _ = rig("logix", [ld(2, "MainRoutine", [
        "PID,Outer,0,0,Out2,0,0,0", "PID,Inner,10,0,Out,Outer,Hold,37.5"], kind="LAD")], tags=tags)
    run(plc, 30)
    assert plc.dt.read_word("Out") == 37.5, "inhold holds the output"
    assert plc.dt.read_word("Inner.SP") == plc.dt.read_word("Outer.CV"), "the master loop sets the setpoint"


# -- S7: data blocks, arrays, FC and FB -----------------------------------------------------------
def test_s7_data_block_from_a_plc_data_type_and_arrays():
    m = S7Memory({"Recipe": {"type": "Settings"}, "Levels": {"type": "Array[1..5] of Int", "value": [7]},
                  "Count": {"type": "Int", "address": "%MW10", "value": 5}},
                 {"Settings": {"Speed": "Real", "Steps": "Array[0..2] of DInt"}})
    m.write_word('"Recipe".Speed', 2.5)
    m.write_word("Recipe.Steps[2]", 9)
    assert m.read_word("Recipe.Speed") == 2.5 and m.read_word('"Recipe".Steps[2]') == 9
    assert m.read_word("Levels[1]") == 7
    assert m.read_bit("Count.%X0") and m.read_bit("Count.%X2") and not m.read_bit("Count.%X1")
    with pytest.raises(S7Error, match="out of range"):
        m.ref("Levels[0]")


def test_s7_fc_with_parameters_from_ladder_and_scl():
    scale = st_file(3, "Scale", "#Out := #Raw * 2 + #Offset;", kind="FC",
                    interface={"Input": {"Raw": "Int", "Offset": "Int"}, "Output": {"Out": "Int"}})
    lamp = ld(4, "Lamp", ["XIC,#Cmd OTE,%Q0.0"], kind="FC", interface={"Input": {"Cmd": "Bool"}})
    plc, panel = rig("s7", [
        ld(2, "Main", ["CALL,Scale,Raw:=10,Offset:=1,Out=>A", "XIC,%I0.0 CALL,Lamp,Cmd:=TRUE"], kind="LAD"),
        st_file(5, "Calc", '"Scale"(Raw := 3, Offset := 0, Out => B);'), scale, lamp,
    ], tags={"A": {"type": "Int"}, "B": {"type": "Int"}})
    assert plc.dt.read_word("A") == 21 and plc.dt.read_word("B") == 0
    panel.set_pressed(1, 0, True)
    run(plc, 30)
    assert panel.lamp(2, 0)


def test_s7_fb_instances_keep_their_own_static_data():
    motor = ld(3, "Motor", ["XIC,#Start TON,#Delay,T#100ms", "XIC,#Delay.Q OTE,#Running"], kind="FB",
               interface={"Input": {"Start": "Bool"}, "Output": {"Running": "Bool"},
                          "Static": {"Delay": "IEC_TIMER"}})
    plc, panel = rig("s7", [
        ld(2, "Main", ["CALL,M1,Start:=%I0.0,Running=>%Q0.0", "CALL,M2,Start:=%I0.1,Running=>%Q0.1"],
           kind="LAD"), motor], tags={"M1": {"type": "Motor"}, "M2": {"type": "Motor"}})
    panel.set_pressed(1, 0, True)
    run(plc, 150)
    assert panel.lamp(2, 0) and not panel.lamp(2, 1)
    assert plc.dt.read_word("M1.Delay.ET") == 100 and plc.dt.read_word("M2.Delay.ET") == 0


def test_s7_fb_in_scl_with_a_multi_instance():
    inner = st_file(3, "Count", "IF #Pulse THEN #N := #N + 1; END_IF;\n#Total := #N;", kind="FB",
                    interface={"Input": {"Pulse": "Bool"}, "Output": {"Total": "Int"}, "Static": {"N": "Int"}})
    outer = st_file(4, "Pair", "#A(Pulse := TRUE);\n#B(Pulse := #Both, Total => #Sum);", kind="FB",
                    interface={"Input": {"Both": "Bool"}, "Output": {"Sum": "Int"},
                               "Static": {"A": "Count", "B": "Count"}})
    plc, _ = rig("s7", [st_file(2, "Main", '"P"(Both := FALSE, Sum => Out);', kind="LAD"), inner, outer],
                 tags={"P": {"type": "Pair"}, "Out": {"type": "Int"}})
    run(plc, 40)
    assert plc.dt.read_word("P.A.N") >= 4 and plc.dt.read_word("P.B.N") == 0 and plc.dt.read_word("Out") == 0


@pytest.mark.parametrize("main,msg", [
    ("CALL,Motor", "call an instance"), ("CALL,M1,Speed:=3", "has no input Speed"),
    ("CALL,M1,Start=>%Q0.0", "has no output Start"), ("CALL,Nope", "not a function"),
])
def test_s7_bad_calls_are_reported(main, msg):
    motor = ld(3, "Motor", ["XIC,#Start OTE,#Running"], kind="FB",
               interface={"Input": {"Start": "Bool"}, "Output": {"Running": "Bool"}})
    msgs = problems("s7", [ld(2, "Main", [main], kind="LAD"), motor], tags={"M1": {"type": "Motor"}})
    assert any(msg in m for m in msgs), msgs


def test_s7_fc_has_no_static_data_and_no_instances():
    fc = ld(3, "F", [], kind="FC", interface={"Static": {"X": "Int"}})
    assert any("keeps no static data" in m for m in problems("s7", [ld(2, "Main", [], kind="LAD"), fc]))
    fc.interface = {}
    assert any("only function blocks have instances" in m
               for m in problems("s7", [ld(2, "Main", [], kind="LAD"), fc], tags={"X": {"type": "F"}}))


def test_project_file_keeps_types_and_interfaces():
    p = Program(profile="s7", types={"Settings": {"Speed": "Real"}})
    p.files[2] = ld(2, "Main", [], kind="LAD")
    p.files[3] = st_file(3, "Motor", "", kind="FB", interface={"Input": {"Start": "Bool"}})
    back = plcy.loads(plcy.dumps(p))
    assert back.types == p.types and back.files[3].interface == p.files[3].interface and back.files[3].kind == "FB"


# -- forcing -----------------------------------------------------------------------------------------
def test_forcing_inputs_and_outputs():
    plc, panel = rig("logix", [ld(2, "MainRoutine", ["XIC,Local:1:I.Data.0 OTE,Local:2:O.Data.0"], kind="LAD")])
    assert plc.force("Local:1:I.Data.0", True) == ""
    run(plc, 20)
    assert panel.lamp(2, 0), "a forced input acts as if it were on"
    plc.force("Local:1:I.Data.0", None)
    plc.force("Local:2:O.Data.0", True)
    run(plc, 20)
    assert panel.lamp(2, 0), "a forced output stays on whatever the logic says"
    plc.force("Local:2:O.Data.0", None)
    run(plc, 20)
    assert not panel.lamp(2, 0)


def test_only_io_can_be_forced():
    plc = Processor("s7")
    assert "only I/O" in plc.force("%M0.0", True)
    assert plc.force("%I0.0", True) == "" and plc.dt.read_bit("%I0.0")
