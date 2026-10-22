"""Regression tests for docs/testing/bugs.md. Each was written failing before its fix."""

from plcyard.core.processor import Processor
from plcyard.core.program import Program, Rung
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel


def prog(rung: str, tags=None) -> Program:
    p = Program.new()
    p.tags = tags or {}
    p.main.rungs = [Rung(rsl.parse_rung_text(rung))]
    return p


def test_bug007_download_clears_previous_program_data():
    plc = Processor()
    plc.device = IoPanelModel()
    plc.download(prog("CTU,Parts,10", {"Parts": {"type": "COUNTER"}, "Data": {"type": "INT"}}))
    plc.dt.write_word("Parts.ACC", 7)
    plc.dt.write_word("%MW50", 3)
    plc.download(prog("XIC,%I0.0 OTE,%Q0.0", {"Parts": {"type": "COUNTER"}}))
    assert plc.dt.read_word("Parts.ACC") == 0 and plc.dt.read_word("%MW50") == 0


def test_bug008_download_while_running_turns_outputs_off():
    panel = IoPanelModel()
    plc = Processor()
    plc.device = panel
    plc.download(prog("OTE,%Q0.0"))
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    assert panel.lamp(2, 0)
    plc.download(prog("OTE,%Q0.1"))
    assert plc.mode == Processor.PGM and not panel.lamp(2, 0)
