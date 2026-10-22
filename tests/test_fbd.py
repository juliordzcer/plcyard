"""Function block diagram: model, checks, execution and files."""

import pytest

from plcyard.core.fbd import Block, Diagram, Wire
from plcyard.core.processor import Processor
from plcyard.core.program import Program
from plcyard.formats import plcy
from plcyard.sims.io_panel import IoPanelModel


def rig(blocks, wires=(), tags=None):
    p = Program.new(language="FBD")
    p.main.diagram = Diagram(list(blocks), [Wire(*w) for w in wires])
    p.tags = tags or {}
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    problems = plc.download(p)
    assert problems == [], [str(x) for x in problems]
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    return plc, panel, p


def run(plc, ms):
    for _ in range(int(ms // 10)):
        plc.tick(10)


def test_seal_in_with_or_and_and_blocks():
    plc, panel, _ = rig([
        Block(1, "OR", 0, 0, operands={"IN1": "%I0.0", "IN2": "%Q0.0"}),
        Block(2, "AND", 200, 0, operands={"IN2": "%I0.1", "OUT": "%Q0.0"})],
        [(1, "OUT", 2, "IN1")])
    panel.switch(1, 1).normally_closed = True
    run(plc, 20)
    assert not panel.lamp(2, 0)
    panel.set_pressed(1, 0, True)
    run(plc, 20)
    panel.set_pressed(1, 0, False)
    run(plc, 20)
    assert panel.lamp(2, 0), "sealed in"
    panel.set_pressed(1, 1, True)
    run(plc, 20)
    assert not panel.lamp(2, 0)


def test_timer_counter_and_edges_share_the_instructions():
    plc, panel, _ = rig([
        Block(1, "TON", 0, 0, instance="Delay", operands={"IN": "%I0.0", "PT": "T#300ms", "Q": "%Q0.0"}),
        Block(2, "R_TRIG", 0, 100, operands={"CLK": "%I0.1"}),
        Block(3, "CTU", 200, 100, instance="Parts", operands={"PV": "2", "Q": "%Q0.1", "CV": "Count"})],
        [(2, "Q", 3, "CU")],
        {"Delay": {"type": "TIMER"}, "Parts": {"type": "COUNTER"}, "Count": {"type": "DINT"}})
    panel.set_pressed(1, 0, True)
    run(plc, 200)
    assert not panel.lamp(2, 0)
    run(plc, 150)
    assert panel.lamp(2, 0) and plc.dt.read_word("Delay.ET") == 300
    for _ in range(2):
        panel.set_pressed(1, 1, True)
        run(plc, 20)
        panel.set_pressed(1, 1, False)
        run(plc, 20)
    assert panel.lamp(2, 1) and plc.dt.read_word("Count") == 2


def test_math_compare_select_and_data_flow_order():
    # placed right to left on purpose: the order follows the wires, not the position
    plc, _, _ = rig([
        Block(1, "GT", 400, 0, operands={"IN2": "10", "OUT": "%Q0.0"}),
        Block(2, "ADD", 200, 0, operands={"IN1": "4", "IN2": "8"}, inputs=3),
        Block(3, "SEL", 0, 100, operands={"G": "%Q0.0", "IN0": "1.5", "IN1": "2.5", "OUT": "Choice"})],
        [(2, "OUT", 1, "IN1")], {"Choice": {"type": "REAL"}})
    run(plc, 20)
    assert plc.dt.read_bit("%Q0.0") and plc.dt.read_word("Choice") == 2.5


def test_checks_report_blocks():
    p = Program.new(language="FBD")
    p.main.diagram = Diagram([Block(1, "TON", 0, 0), Block(2, "NOT", 0, 0, operands={"IN": "Ghost"}),
                              Block(3, "ADD", 0, 0)], [Wire(2, "OUT", 3, "IN1")])
    msgs = [str(x) for x in Processor().download(p)]
    assert any("block 1" in m and "needs a TIMER tag" in m for m in msgs)
    assert any("Ghost does not exist" in m for m in msgs)
    assert any("takes a number, the wire brings a BOOL" in m for m in msgs)


def test_project_file_keeps_the_diagram(tmp_path):
    p = Program.new(language="FBD")
    p.main.diagram = Diagram([Block(1, "NOT", 10, 20, operands={"IN": "%I0.0", "OUT": "%Q0.0"})], [])
    back = plcy.loads(plcy.dumps(p))
    assert back.main.language == "FBD" and back.main.diagram.to_dict() == p.main.diagram.to_dict()
    with pytest.raises(plcy.PlcyError, match="unknown function block"):
        plcy.loads(plcy.dumps(p).replace('"NOT"', '"NOPE"'))


def test_fbd_routine_called_from_ladder_and_inside_a_function_block():
    from plcyard.core.program import ProgramFile, Rung
    from plcyard.formats import rsl
    p = Program.new()
    p.main.rungs = [Rung(rsl.parse_rung_text("JSR,Logic")), Rung(rsl.parse_rung_text("CALL,M1,Start:=%I0.2,Run=>%Q0.3"))]
    p.files[3] = ProgramFile(3, "SBR", "Logic", language="FBD",
                             diagram=Diagram([Block(1, "NOT", 0, 0, operands={"IN": "%I0.0", "OUT": "%Q0.2"})]))
    p.files[4] = ProgramFile(4, "FB", "Motor", language="FBD", interface={"Input": {"Start": "BOOL"}, "Output": {"Run": "BOOL"},
                                                                          "Static": {"Delay": "TIMER"}},
                             diagram=Diagram([Block(1, "TON", 0, 0, instance="#Delay",
                                                    operands={"IN": "#Start", "PT": "T#100ms", "Q": "#Run"})]))
    p.tags = {"M1": {"type": "Motor"}}
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    assert plc.download(p) == []
    plc.set_mode(Processor.RUN)
    run(plc, 20)
    assert panel.lamp(2, 2)
    panel.set_pressed(1, 2, True)
    run(plc, 150)
    assert panel.lamp(2, 3) and plc.dt.read_word("M1.Delay.ACC") == 100
