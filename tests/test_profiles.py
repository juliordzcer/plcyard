"""The scan engine is profile-agnostic: a toy tag-based controller runs on it unchanged."""

import pytest

from plcyard.core import isa, profiles
from plcyard.core.processor import Processor
from plcyard.core.profiles import Diagnostic, Profile
from plcyard.core.program import Instr, Program, ProgramFile, Rung, Series, walk
from plcyard.formats import rsl
from plcyard.sims.io_panel import IoPanelModel


class TagError(Exception):
    pass


class Tags(dict):
    def read(self, name):
        if name not in self:
            raise TagError(f"tag {name} does not exist")
        return self[name]


class TagContext:
    def __init__(self, tags):
        self.tags = tags
        self.now_ms = 0.0
        self.timer_marks = {}
        self.call = lambda n: None

    def bit(self, op):
        return bool(self.tags.read(op))

    def set_bit(self, op, on):
        self.tags.read(op)
        self.tags[op] = on


def _spec(m, fn, output=False):
    return isa.Spec(m, m, "Bit", ("bit",), ("Tag",), output, fn)


class Toy(Profile):
    """Inputs Start/Stop come from I/O panel slot 1 bits 0/1; Motor drives slot 2 bit 0."""

    name = "toy"
    title = "Toy tag controller"
    specs = {
        "XIC": _spec("XIC", lambda ctx, ops, cond: cond and ctx.bit(ops[0])),
        "XIO": _spec("XIO", lambda ctx, ops, cond: cond and not ctx.bit(ops[0])),
        "OTE": _spec("OTE", lambda ctx, ops, cond: (ctx.set_bit(ops[0], cond), cond)[1], output=True),
    }
    memory_errors = (TagError,)
    memory_fault_code = 0x7777
    TAGS = ("Start", "Stop", "Motor", "Ghost")

    def new_memory(self):
        return Tags({t: False for t in self.TAGS[:3]})     # "Ghost" is declared but missing

    def context(self, memory):
        return TagContext(memory)

    def check(self, program, memory):
        return [Diagnostic(2, i, f"{ins.mnemonic}: unknown tag {ins.operands[0]}")
                for i, r in enumerate(program.main.rungs) for ins in walk(r.body)
                if ins.mnemonic not in self.specs or ins.operands[0] not in self.TAGS]

    def read_inputs(self, tags, device):
        w = device.input_words().get(1, 0)
        tags["Start"], tags["Stop"] = bool(w & 1), bool(w & 2)

    def write_outputs(self, tags, device):
        device.set_output_words({2: int(tags["Motor"])})

    def outputs_off(self, tags, device):
        device.set_output_words({2: 0})


@pytest.fixture(autouse=True)
def toy():
    profiles.register(Toy())
    yield
    profiles.PROFILES.pop("toy", None)


def toy_program(*rungs):
    p = Program(profile="toy")
    p.files[2] = ProgramFile(2, "LAD", rungs=[Rung(Series([Instr(m, [op]) for m, op in r])) for r in rungs])
    return p


def test_unknown_profile_is_an_error():
    with pytest.raises(ValueError):
        profiles.get("nope")


def test_toy_controller_runs_a_seal_in():
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    prog = toy_program([("XIC", "Start"), ("XIO", "Stop"), ("OTE", "Motor")])
    assert plc.download(prog) == []
    assert plc.profile.name == "toy"
    plc.set_mode(Processor.RUN)
    panel.set_pressed(1, 0, True)
    plc.tick(20)
    assert panel.lamp(2, 0)
    panel.set_pressed(1, 1, True)
    plc.tick(20)
    assert not panel.lamp(2, 0)


def test_toy_check_blocks_download():
    plc = Processor()
    problems = plc.download(toy_program([("XIC", "Nope"), ("OTE", "Motor")]))
    assert problems and "unknown tag Nope" in str(problems[0])
    assert plc.profile.name == "slc500", "a rejected download does not switch the controller"


def test_toy_memory_error_is_a_major_fault_with_the_profile_code():
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    plc.download(toy_program([("XIC", "Ghost"), ("OTE", "Motor")]))
    plc.set_mode(Processor.RUN)
    plc.tick(10)
    assert plc.mode == Processor.FAULT and plc.fault_code == 0x7777


def test_switching_back_to_slc500():
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    plc.download(toy_program([("XIC", "Start"), ("OTE", "Motor")]))
    slc = rsl.loads("FILE,LAD 2\r\nSOR,0 XIC,I:1/0 OTE,O:2/1 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    assert plc.download(slc) == [] and plc.profile.name == "slc500"
    plc.set_mode(Processor.RUN)
    panel.set_pressed(1, 0, True)
    plc.tick(20)
    assert panel.lamp(2, 1) and plc.dt.read_bit("O:2/1")


def test_instruction_bar_shows_the_profile_instruction_set(qapp):
    from plcyard.ui.instruction_bar import InstructionBar
    bar = InstructionBar()
    assert "Timer/Counter" in bar.families
    bar.set_specs(Toy.specs)
    assert bar.families == ["Bit"]
    buttons = [bar.row.itemAt(i).widget() for i in range(bar.row.count()) if bar.row.itemAt(i).widget()]
    assert {getattr(b, "mnemonic", None) for b in buttons} >= {"XIC", "XIO", "OTE"}
    assert not any(getattr(b, "mnemonic", "") == "TON" for b in buttons)
