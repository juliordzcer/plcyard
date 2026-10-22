import pytest

from plcyard.core import edit
from plcyard.core.program import Instr, Parallel, Program, Series
from plcyard.formats import rsl


def rung(tokens: str) -> Series:
    return rsl.parse_rung_text(tokens)


def dump(body: Series) -> str:
    return " ".join(rsl._dump_series(body, 0))


def test_new_instruction_has_unset_operands():
    assert edit.new_instr("TON").operands == ["?", "?"]
    assert edit.new_instr("SQO").operands == ["?"] * 5, "optional Position left out"


def test_default_slot_puts_inputs_before_outputs():
    b = rung("XIC,%I0.0 OTE,%Q0.0")
    edit.insert(b, edit.default_slot(b, "XIO"), Instr("XIO", ["%I0.1"]))
    edit.insert(b, edit.default_slot(b, "OTL"), Instr("OTL", ["Flag"]))
    assert dump(b) == "XIC,%I0.0 XIO,%I0.1 OTE,%Q0.0 OTL,Flag"


def test_wrap_and_add_leg_build_a_seal_in():
    b = rung("XIC,%I0.1 XIC,%I0.0 OTE,%Q0.0")
    par = edit.wrap_in_branch(b, (1,))
    leg = edit.add_leg(b, par)
    edit.insert(b, edit.Slot(par + (1,), 0), Instr("XIC", ["%Q0.0"]))
    assert dump(b) == "XIC,%I0.1 BST,1 XIC,%I0.0 NXB,1 XIC,%Q0.0 NXB,1 BND,1 OTE,%Q0.0"
    edit.remove(b, leg)
    assert dump(b) == "XIC,%I0.1 BST,1 XIC,%I0.0 NXB,1 XIC,%Q0.0 BND,1 OTE,%Q0.0"


def test_removing_a_leg_unwraps_single_leg_branch():
    b = rung("BST,1 XIC,%I0.0 NXB,1 XIC,%I0.1 BND,1 OTE,%Q0.0")
    edit.remove(b, (0, 1, 0))      # empties leg 1 -> branch with an empty leg stays
    assert isinstance(b.items[0], Parallel)
    edit.remove(b, (0, 1))         # remove the empty leg -> unwrap
    assert dump(b) == "XIC,%I0.0 OTE,%Q0.0"


def test_move_instruction_within_rung():
    b = rung("XIC,%I0.0 XIC,%I0.1 XIC,%I0.2 OTE,%Q0.0")
    new = edit.move(b, (0,), edit.Slot((), 3))
    assert dump(b) == "XIC,%I0.1 XIC,%I0.2 XIC,%I0.0 OTE,%Q0.0"
    assert new == (2,)


def test_move_into_branch_leg():
    b = rung("XIC,%I0.5 BST,1 XIC,%I0.0 NXB,1 XIC,%I0.1 BND,1 OTE,%Q0.0")
    edit.move(b, (0,), edit.Slot((1, 1), 1))
    assert dump(b) == "BST,1 XIC,%I0.0 NXB,1 XIC,%I0.1 XIC,%I0.5 BND,1 OTE,%Q0.0"


def test_cannot_move_branch_into_itself():
    b = rung("BST,1 XIC,%I0.0 NXB,1 XIC,%I0.1 BND,1 OTE,%Q0.0")
    with pytest.raises(edit.EditError):
        edit.move(b, (0,), edit.Slot((0, 1), 0))


def test_toggle_and_operands():
    b = rung("XIC,%I0.0 TON,?,?")
    edit.toggle_contact(b, (0,))
    assert b.items[0].mnemonic == "XIO"
    prog = Program.new()
    prog.tags = {"Delay": {"type": "TIMER"}, "Count": {"type": "DINT"}}
    assert edit.set_operands(b, (1,), ["Delay", "T#3s"], program=prog) == []
    assert b.items[1].operands == ["Delay", "T#3s"]
    assert edit.set_operands(b, (1,), ["Count", ""], program=prog)   # problems reported


def test_navigation_order():
    b = rung("XIC,%I0.0 BST,1 XIC,%I0.1 NXB,1 XIC,%I0.2 BND,1 OTE,%Q0.0")
    assert edit.instructions_in_order(b) == [(0,), (1, 0, 0), (1, 1, 0), (2,)]


def test_new_rung_and_download_of_edited_program():
    from plcyard.core.processor import Processor
    p = Program.new()
    k = edit.new_rung(p.main, 0)
    b = p.main.rungs[k].body
    edit.insert(b, edit.default_slot(b, "XIC"), Instr("XIC", ["%I0.0"]))
    edit.insert(b, edit.default_slot(b, "OTE"), Instr("OTE", ["%Q0.0"]))
    assert Processor().download(p) == []
    assert rsl.rung_text(p.main.rungs[0].body) == "XIC,%I0.0 OTE,%Q0.0"
