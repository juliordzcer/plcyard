"""The PLC: memory, references in both notations, the instruction set and its timing."""

import pytest

from plcyard.core.plc.memory import Memory, PlcMemoryError, absolute_to_module, module_to_absolute
from plcyard.core.processor import Processor
from plcyard.core.program import Program, Rung
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel


def rig(rungs, tags=None):
    p = Program.new()
    p.tags = tags or {}
    p.main.rungs = [Rung(rsl.parse_rung_text(r)) for r in rungs]
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    problems = plc.download(p)
    assert problems == [], [str(x) for x in problems]
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    return plc, panel


def run(plc, ms):
    for _ in range(int(ms // 10)):
        plc.tick(10)


# -- memory and notations -------------------------------------------------------------------------
@pytest.mark.parametrize("module,absolute", [
    ("Local:1:I.Data.0", "%I0.0"), ("Local:1:I.Data.9", "%I1.1"), ("Local:3:I.Data.15", "%I3.7"),
    ("Local:2:O.Data.3", "%Q0.3"), ("Local:4:O.Data.8", "%Q3.0"), ("Local:7:I.Ch0Data", "%IW64"),
    ("Local:7:I.Ch1Data", "%IW66"), ("Local:8:O.Ch0Data", "%QW64"), ("Local:5:I.Data", "%IW4"),
])
def test_module_names_and_absolute_addresses_are_the_same_points(module, absolute):
    assert module_to_absolute(module) == absolute
    assert absolute_to_module(absolute) == module


def test_one_memory_reads_both_notations():
    m = Memory({"Delay": {"type": "TIMER"}, "Parts": {"type": "COUNTER"}, "Flag": {"type": "BOOL", "address": "%M0.0"}})
    m.write_bit("Local:2:O.Data.9", True)
    assert m.read_bit("%Q1.1")
    m.element("Delay").update(ACC=1200, DN=True)
    assert m.read_word("Delay.ET") == 1200 and m.read_bit("Delay.Q") and m.read_word("delay.acc") == 1200
    m.write_word("Parts.PV", 5)
    assert m.read_word("Parts.PRE") == 5
    m.write_bit("S:FS", True)
    assert m.read_bit("FirstScan") and m.read_bit("Flag") is False


def test_data_types_and_arrays():
    m = Memory({"Line": {"type": "Pump[2]"}, "Steps": {"type": "Array[1..4] of DINT", "value": [7]}},
               {"Pump": {"Speed": "REAL", "Run": "BOOL"}})
    m.write_word("Line[1].Speed", 2.5)
    assert m.read_word("line[1].speed") == 2.5 and m.read_word("Steps[1]") == 7
    with pytest.raises(PlcMemoryError, match="out of range"):
        m.ref("Steps[0]")
    with pytest.raises(PlcMemoryError, match="no such module point"):
        m.ref("Local:9:I.Data.0")


def test_notation_display_and_input():
    from plcyard.ui import notation
    p = Program.new()
    p.tags = {"Delay": {"type": "TIMER"}, "T": {"type": "TIMER[3]"}}
    notation.set_current("A")
    assert notation.show("%I0.1", p) == "Local:1:I.Data.1" and notation.show("FirstScan") == "S:FS"
    assert notation.store("Local:2:O.Data.0", p) == "%Q0.0" and notation.store("Delay.Q", p) == "Delay.DN"
    notation.set_current("B")
    assert notation.show("%I0.1", p) == "%I0.1" and notation.show("T[2].DN", p) == "T[2].Q"
    assert notation.mnemonic("MOV") == "MOVE" and notation.labels("TON", ["Timer", "Preset", "Accum"])[:2] == ["Instance", "PT"]
    assert "`NO contact`" in notation.show_text("Use `XIC` on %I0.0")
    notation.set_current("A")
    assert notation.show_text("Use `XIC` on %I0.0") == "Use `XIC` on Local:1:I.Data.0"


# -- instructions ---------------------------------------------------------------------------------
def test_timer_box_passes_q_to_the_rest_of_the_rung():
    plc, panel = rig(["XIC,%I0.0 TON,Delay,T#300ms OTE,%Q0.0"], {"Delay": {"type": "TIMER"}})
    panel.set_pressed(1, 0, True)
    run(plc, 200)
    assert not panel.lamp(2, 0) and plc.dt.read_bit("Delay.TT")
    run(plc, 150)
    assert panel.lamp(2, 0) and plc.dt.read_word("Delay.ACC") == 300


def test_pulse_and_off_delay_timers():
    plc, panel = rig(["XIC,%I0.0 TP,Pulse,200 OTE,%Q0.0", "XIC,%I0.1 TOF,Off,200 OTE,%Q0.1"],
                     {"Pulse": {"type": "TIMER"}, "Off": {"type": "TIMER"}})
    panel.set_pressed(1, 0, True)
    panel.set_pressed(1, 1, True)
    run(plc, 30)
    panel.set_pressed(1, 0, False)
    panel.set_pressed(1, 1, False)
    run(plc, 100)
    assert panel.lamp(2, 0), "a pulse runs to the end once started"
    assert panel.lamp(2, 1), "off delay holds the output after the input drops"
    run(plc, 200)
    assert not panel.lamp(2, 0) and not panel.lamp(2, 1)


def test_counter_with_reset_operand():
    plc, panel = rig(["XIC,%I0.0 CTU,Parts,3,%I0.1 OTE,%Q0.0"], {"Parts": {"type": "COUNTER"}})
    for _ in range(3):
        panel.set_pressed(1, 0, True)
        run(plc, 20)
        panel.set_pressed(1, 0, False)
        run(plc, 20)
    assert panel.lamp(2, 0) and plc.dt.read_word("Parts.CV") == 3
    panel.set_pressed(1, 1, True)
    run(plc, 20)
    assert not panel.lamp(2, 0) and plc.dt.read_word("Parts.ACC") == 0


def test_math_wraps_sets_overflow_and_division_by_zero_passes_no_power():
    plc, panel = rig(["ADD,32767,1,Small", "DIV,10,Zero,Big OTE,%Q0.0", "MOD,17,5,Rest"],
                     {"Small": {"type": "INT"}, "Zero": {"type": "DINT"}, "Big": {"type": "DINT"}, "Rest": {"type": "DINT"}})
    assert plc.dt.read_word("Small") == -32768 and plc.dt.read_bit("Overflow")
    assert not panel.lamp(2, 0) and plc.dt.read_word("Rest") == 2 and plc.mode == Processor.RUN


def test_compares_and_moves():
    plc, panel = rig(["LIM,10,V,20 OTE,%Q0.0", "GRT,V,15 OTE,%Q0.1", "MOV,V,%QW2", "MVM,255,15,Masked"],
                     {"V": {"type": "DINT", "value": 17}, "Masked": {"type": "DINT"}})
    assert panel.lamp(2, 0) and panel.lamp(2, 1) and plc.dt.read_word("%QW2") == 17
    assert plc.dt.read_word("Masked") == 15


def test_bit_shift_and_sequencer_on_arrays():
    plc, panel = rig([
        "XIC,%I0.0 BSL,Bits[0],Shift,%I0.1,16",
        "XIC,%I0.2 SQO,Steps[0],255,%QW2,Seq,3",
        "XIC,FirstScan COP,Src[0],Dst[1],2", "XIC,FirstScan FLL,9,Fill[0],3"],
        {"Bits": {"type": "INT[1]"}, "Shift": {"type": "CONTROL"}, "Steps": {"type": "DINT[4]", "value": [0, 1, 2, 4]},
         "Seq": {"type": "CONTROL"}, "Src": {"type": "DINT[2]", "value": [5, 6]}, "Dst": {"type": "DINT[3]"},
         "Fill": {"type": "INT[3]"}})
    assert plc.dt.read_word("Dst[1]") == 5 and plc.dt.read_word("Dst[2]") == 6 and plc.dt.read_word("Fill[2]") == 9
    panel.set_pressed(1, 1, True)
    for _ in range(2):
        panel.set_pressed(1, 0, True)
        run(plc, 20)
        panel.set_pressed(1, 0, False)
        run(plc, 20)
    assert plc.dt.read_word("Bits[0]") == 3, "two shifts of a 1 into bit 0"
    seen = []
    for _ in range(3):
        panel.set_pressed(1, 2, True)
        run(plc, 20)
        seen.append(plc.dt.read_word("%QW2") & 0xFF)
        panel.set_pressed(1, 2, False)
        run(plc, 20)
    assert seen == [1, 2, 4]


def test_edge_contacts_and_one_shots():
    plc, panel = rig(["XIC,%I0.0 ONS,Mem1 OTL,Count1", "P,%I0.0,Mem2 OTL,Count2", "N,%I0.0,Mem3 OTL,Count3"],
                     {n: {"type": "BOOL"} for n in ("Mem1", "Mem2", "Mem3", "Count1", "Count2", "Count3")})
    panel.set_pressed(1, 0, True)
    run(plc, 20)
    assert plc.dt.read_bit("Count1") and plc.dt.read_bit("Count2") and not plc.dt.read_bit("Count3")
    panel.set_pressed(1, 0, False)
    run(plc, 20)
    assert plc.dt.read_bit("Count3")
