"""Regression tests for docs/testing/bugs.md. Each was written failing before its fix."""

import pytest

from plcyard.core import isa
from plcyard.core.processor import Processor
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel

PROG = "FILE,LAD 2\r\nSOR,0 {} EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n"


def test_bug001_unsupported_characters_are_reported_on_save(tmp_path):
    p = rsl.loads(PROG.format("XIC,I:1/0 OTE,O:2/0"))
    p.main.rungs[0].comment = "Válvula 🚀"
    p.symbols["I:1/0"] = "Señal ✓"
    replaced = rsl.save(p, tmp_path / "x.rsl")
    assert sorted(replaced) == ["✓", "🚀"]
    back = rsl.load(tmp_path / "x.rsl")
    assert back.main.rungs[0].comment == "Válvula ?", "accents survive, emoji replaced"


def test_bug002_no_symbols_section_added_when_absent():
    text = PROG.format("XIC,I:1/0 OTE,O:2/0")
    assert rsl.dumps(rsl.loads(text)) == text


@pytest.mark.parametrize("op", ["N7:256", "O:9/0", "B3:300/1", "T4:999.ACC", "N7:[N7:0]"])
def test_bug003_addresses_outside_the_data_table_rejected_at_download(op):
    rung = f"XIC,{op} OTE,O:2/0" if "/" in op else f"MOV,1,{op}"
    problems = Processor().download(rsl.loads(PROG.format(rung)))
    if op == "N7:[N7:0]":
        assert problems == [], "indirect addresses are checked at run time"
    else:
        assert problems and "out of range" in str(problems[0])


def test_bug004_float_file_has_no_bits():
    assert isa.validate("XIC", ["F8:0/1"])


def test_bug007_download_clears_previous_program_data():
    plc = Processor()
    plc.device = IoPanelModel()
    plc.download(rsl.loads(PROG.format("CTU,C5:0,10")))
    plc.dt.write_word("C5:0.ACC", 7)
    plc.dt.write_word("N7:50", 3)
    plc.download(rsl.loads(PROG.format("XIC,I:1/0 OTE,O:2/0")))
    assert plc.dt.read_word("C5:0.ACC") == 0 and plc.dt.read_word("N7:50") == 0


def test_bug008_download_while_running_turns_outputs_off():
    panel = IoPanelModel()
    plc = Processor()
    plc.device = panel
    plc.download(rsl.loads(PROG.format("OTE,O:2/0")))
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    assert panel.lamp(2, 0)
    plc.download(rsl.loads(PROG.format("OTE,O:2/1")))
    assert plc.mode == Processor.PGM and not panel.lamp(2, 0)
