from plcyard.formats import rsl
from plcyard.ui.ladder_layout import BRANCH_GAP, CONTACT_W, WIRE_Y, layout_rung


def body(tokens: str):
    text = f"FILE,LAD 2\r\nSOR,0 {tokens} EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n"
    return rsl.loads(text).main.rungs[0].body


def test_outputs_pushed_to_right_rail():
    g = layout_rung(body("XIC,I:1/0 OTE,O:2/0"), 800)
    xic, ote = g.instrs
    assert xic.x == 0
    assert ote.x + ote.w == 800


def test_parallel_stacks_branches_and_rails_connect():
    g = layout_rung(body("BST,1 XIC,I:1/0 NXB,1 XIC,O:2/0 BND,1 OTE,O:2/0"), 800)
    a, b, _ = g.instrs
    assert a.x == b.x == BRANCH_GAP
    assert b.y == a.h
    verticals = [(w.x1, w.y1, w.x2, w.y2) for w in g.wires if w.x1 == w.x2]
    assert (0, WIRE_Y, 0, b.y + WIRE_Y) in verticals


def test_rung_grows_beyond_pane_when_needed():
    g = layout_rung(body(" ".join(f"XIC,I:1/{i}" for i in range(12)) + " OTE,O:2/0"), 300)
    assert g.width >= 13 * CONTACT_W


def test_wire_tags_follow_processor_trace():
    from plcyard.core.processor import Processor
    from plcyard.sims.io_panel import IoPanelModel

    text = ("FILE,LAD 2\r\nSOR,0 XIC,I:1/0 BST,1 XIC,I:1/1 NXB,1 XIC,I:1/2 BND,1 OTE,O:2/0 EOR,0\r\n"
            "RCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    panel = IoPanelModel()
    plc = Processor()
    plc.device = panel
    plc.tracing = True
    plc.download(rsl.loads(text))
    plc.set_mode(Processor.RUN)
    panel.set_pressed(1, 0, True)
    panel.set_pressed(1, 2, True)
    plc.tick(10)
    g = layout_rung(plc.program.main.rungs[0].body, 800)
    lit = {w.tag for w in g.wires if plc.trace[(2, 0) + w.tag[0]][0 if w.tag[1] == "in" else 1]}
    assert ((1, 1), "out") in lit, "second branch passes power"
    assert ((1, 0), "out") not in lit, "first branch is open"
    assert ((1,), "out") in lit, "parallel passes power to the coil"
