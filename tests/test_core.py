import pytest

from plcyard.core.address import AddressError, parse_address, parse_literal
from plcyard.core.datatable import DataTable
from plcyard.core.processor import Processor
from plcyard.core.program import Program
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel


@pytest.mark.parametrize("text", [
    "I:1/0", "O:2/15", "B3:0/5", "B3/37", "N7:12", "N7:0/3", "T4:1.ACC", "T4:1/DN",
    "C5:0.PRE", "R6:0/EN", "N7:[C5:0.ACC]", "#N7:0", "S:1/13",
])
def test_address_roundtrip(text):
    assert str(parse_address(text)) == text


@pytest.mark.parametrize("text", ["X9:0", "N7", "T4:0.FOO", "B3:0/16", "I3:1/0", "N7:0.1"])
def test_address_rejects(text):
    with pytest.raises(AddressError):
        parse_address(text)


def test_literals():
    assert parse_literal("100") == 100
    assert parse_literal("00FFh") == 255
    assert parse_literal("FFFFh") == -1
    assert parse_literal("2.5") == 2.5
    assert parse_literal("N7:0") is None


def test_structured_bits_share_words():
    dt = DataTable()
    dt.write_bit("T4:1/DN", True)
    assert dt.read_word("T4:1/13") == 1
    dt.write_word("T4:1.ACC", 70)
    assert dt.read_word("T4:1.ACC") == 70
    assert dt.read_bit("B3/37") is False
    dt.write_bit("B3/37", True)
    assert dt.read_bit("B3:2/5")


def test_indirect():
    dt = DataTable()
    dt.write_word("N7:0", 4)
    dt.write_word("N7:[N7:0]", 99)
    assert dt.read_word("N7:4") == 99


def test_word_wraps_to_int16():
    dt = DataTable()
    dt.write_word("N7:0", 40000)
    assert dt.read_word("N7:0") == 40000 - 65536


def run(text: str, panel: IoPanelModel, scans: int = 1) -> Processor:
    plc = Processor()
    plc.device = panel
    assert plc.download(rsl.loads(text)) == []
    plc.set_mode(Processor.RUN)
    plc.tick(10 * scans)
    return plc


SEAL_IN = (
    "FILE,LAD 2\r\n"
    "SOR,0 XIC,I:1/1 BST,1 XIC,I:1/0 NXB,1 XIC,O:2/0 BND,1 OTE,O:2/0 EOR,0\r\n"
    "RCM,motor seal-in\r\n"
    "SOR,1 END,1\r\nRCM,\r\n"
)


def test_seal_in_with_nc_stop():
    panel = IoPanelModel()
    panel.switch(1, 1).normally_closed = True     # stop button wired NC
    panel.set_pressed(1, 0, True)
    plc = run(SEAL_IN, panel)
    assert panel.lamp(2, 0)
    panel.set_pressed(1, 0, False)
    plc.tick(10)
    assert panel.lamp(2, 0), "holds through the seal-in branch"
    panel.set_pressed(1, 1, True)
    plc.tick(10)
    assert not panel.lamp(2, 0)


def test_outputs_inside_branch_and_series_after_branch():
    text = (
        "FILE,LAD 2\r\n"
        "SOR,0 XIC,I:1/0 BST,1 OTE,O:2/1 NXB,1 XIO,I:1/2 OTE,O:2/2 BND,1 OTE,O:2/3 EOR,0\r\n"
        "RCM,\r\nSOR,1 END,1\r\nRCM,\r\n"
    )
    panel = IoPanelModel()
    panel.set_pressed(1, 0, True)
    panel.set_pressed(1, 2, True)
    run(text, panel)
    assert panel.lamp(2, 1)
    assert not panel.lamp(2, 2)
    assert panel.lamp(2, 3), "a parallel is true when any branch is"


def test_latch_unlatch_and_osr():
    text = (
        "FILE,LAD 2\r\n"
        "SOR,0 XIC,I:1/0 OTL,O:2/0 EOR,0\r\nRCM,\r\n"
        "SOR,1 XIC,I:1/1 OTU,O:2/0 EOR,1\r\nRCM,\r\n"
        "SOR,2 XIC,I:1/2 OSR,B3:0/0 OTE,B3:0/1 EOR,2\r\nRCM,\r\n"
        "SOR,3 XIC,B3:0/1 OTL,O:2/5 EOR,3\r\nRCM,\r\n"
        "SOR,4 END,4\r\nRCM,\r\n"
    )
    panel = IoPanelModel()
    panel.set_pressed(1, 0, True)
    plc = run(text, panel)
    panel.set_pressed(1, 0, False)
    plc.tick(10)
    assert panel.lamp(2, 0)
    panel.set_pressed(1, 1, True)
    plc.tick(10)
    assert not panel.lamp(2, 0)
    panel.set_pressed(1, 2, True)
    plc.tick(10)
    assert plc.dt.read_bit("B3:0/1")
    plc.tick(10)
    assert not plc.dt.read_bit("B3:0/1"), "one scan only"


def test_pgm_turns_outputs_off_and_rejects_unset_operands():
    panel = IoPanelModel()
    panel.set_pressed(1, 0, True)
    plc = run(SEAL_IN, panel)
    plc.set_mode(Processor.PGM)
    assert not panel.lamp(2, 0)
    bad = rsl.loads("FILE,LAD 2\r\nSOR,0 XIC,? OTE,O:2/0 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    problems = Processor().download(bad)
    assert problems and "not set" in str(problems[0])


def test_speed_independent_scan_count():
    panel = IoPanelModel()
    plc = run(SEAL_IN, panel, scans=0)
    assert plc.tick(105) == 10
    assert plc.tick(5) == 1


def test_thumbwheels_bcd():
    panel = IoPanelModel()
    panel.thumbwheels = [1, 2, 3, 4]
    assert panel.input_words()[5] == 0x1234


def test_new_program_dumps_and_loads():
    text = rsl.dumps(Program.new())
    prog = rsl.loads(text)
    assert rsl.dumps(prog) == text
    assert sorted(prog.files) == list(range(2, 10))


def test_slot_word_suffix_is_normalised():
    assert str(parse_address("I:1.0/3")) == "I:1/3"
