"""Editor flows driven like a user: instruction bar, keyboard, operand editor, undo."""

import pytest
from PySide6.QtCore import Qt

from plcyard.core.processor import Processor
from plcyard.formats import rsl
from plcyard.ui import theme
from plcyard.ui.main_window import MainWindow


@pytest.fixture
def win(qtbot, qapp):
    theme.apply(qapp, "light")
    w = MainWindow()
    w.dirty = False
    w.show()
    yield w
    w.dirty = False
    w.clock.stop()
    w.frame.stop()
    w.close()
    w.deleteLater()
    qapp.processEvents()


def set_ops(win, *values):
    c = win.ladder.canvas
    c.open_operand_editor()
    for f, v in zip(c.editor.fields, values):
        f.setText(v)
    c.editor.commit()


def test_build_seal_in_from_scratch_and_run(win, qtbot):
    c = win.ladder.canvas
    win.bar.picked.emit("RUNG")
    assert c.sel == ("rung", 0)
    for m, op in (("XIC", "I:1/1"), ("XIC", "I:1/0")):
        win.bar.picked.emit(m)
        set_ops(win, op)
    win.bar.picked.emit("BRANCH")                       # wrap XIC I:1/0, adds an empty leg
    c.paste()                                            # nothing in clipboard: no-op
    body = c.file.rungs[0].body
    from plcyard.core import edit
    from plcyard.core.program import Instr
    c.apply_edit("seal", lambda b: edit.insert(b, edit.Slot((1, 1), 0), Instr("XIC", ["O:2/0"])), 0)
    c.sel = ("rung", 0)
    win.bar.picked.emit("OTE")
    set_ops(win, "O:2/0")
    assert " ".join(rsl._dump_series(body, 0)) == \
        "XIC,I:1/1 BST,1 XIC,I:1/0 NXB,1 XIC,O:2/0 BND,1 OTE,O:2/0"
    assert win.dirty and "•" in win.windowTitle()

    win.sim.switch(1, 1).normally_closed = True
    win.download()
    assert win.in_sync
    win.panel.mode.set_mode("RUN")
    win.sim.set_pressed(1, 0, True)
    win.plc.tick(20)
    win.sim.set_pressed(1, 0, False)
    win.plc.tick(20)
    assert win.sim.lamp(2, 0)


def test_keyboard_navigation_delete_and_undo(win, qtbot):
    win.program = rsl.loads("FILE,LAD 2\r\nSOR,0 XIC,I:1/0 XIO,I:1/1 OTE,O:2/0 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    win._show_program()
    c = win.ladder.canvas
    c.setFocus()
    c.sel = ("rung", 0)
    qtbot.keyClick(c, Qt.Key_Right)
    qtbot.keyClick(c, Qt.Key_Right)
    assert c.sel == ("instr", 0, (1,))
    qtbot.keyClick(c, Qt.Key_Delete)
    assert [i.mnemonic for i in c.file.rungs[0].body.items] == ["XIC", "OTE"]
    c.undo.undo()
    assert [i.mnemonic for i in c.file.rungs[0].body.items] == ["XIC", "XIO", "OTE"]
    c.undo.redo()
    assert len(c.file.rungs[0].body.items) == 2


def test_operand_editor_rejects_bad_address(win):
    c = win.ladder.canvas
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("TON")
    c.open_operand_editor()
    c.editor.fields[0].setText("N7:0")
    c.editor.fields[1].setText("50")
    assert "timer" in c.editor.error.text().lower()
    c.editor.fields[0].setText("T4:0")
    assert c.editor.error.text() == ""
    c.editor.commit()
    assert c.file.rungs[0].body.items[0].operands == ["T4:0", "50"]


def test_edits_after_download_mark_out_of_sync(win):
    win.program = rsl.loads("FILE,LAD 2\r\nSOR,0 XIC,I:1/0 OTE,O:2/0 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    win._show_program()
    win.download()
    assert win.in_sync
    c = win.ladder.canvas
    c.sel = ("instr", 0, (0,))
    c.toggle_contact()
    assert not win.in_sync
    assert "edited" in win.panel.status.text()


def test_copy_paste_rung_and_datatable_goto(win):
    win.program = rsl.loads("FILE,LAD 2\r\nSOR,0 XIC,I:1/0 TON,T4:3,10 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    win._show_program()
    c = win.ladder.canvas
    c.sel = ("rung", 0)
    c.copy_selection()
    c.paste()
    assert len(c.file.rungs) == 2
    win.show_address("T4:3")
    assert win.table_dock.isVisible()
    assert win.table_view.model.file_no == 4
    assert win.table_view.table.currentIndex().row() == 3


def test_reset_timers_and_counters_keeps_presets(win):
    win.program = rsl.loads("FILE,LAD 2\r\nSOR,0 XIC,I:1/0 TON,T4:0,30 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    win._show_program()
    win.download()
    win.plc.dt.write_word("T4:0.ACC", 12)
    win.reset_timers_counters()
    assert win.plc.dt.read_word("T4:0.ACC") == 0 and win.plc.dt.read_word("T4:0.PRE") == 30


def test_switch_simulations_and_run_silo(win):
    from tests.test_sims import SILO_CONTINUOUS, program
    win.select_sim("silo")
    assert type(win.sim).__name__ == "SiloModel" and win.plc.device is win.sim
    win.program = rsl.loads(program(*SILO_CONTINUOUS))
    win._show_program()
    win.download()
    win.panel.mode.set_mode("RUN")
    win.sim.start_pressed = True
    win.plc.tick(20)
    win.sim.start_pressed = False
    win.plc.tick(500)
    assert win.sim.motor and win.sim.lamp(2)
    win._refresh()
    win.select_sim("traffic")
    assert type(win.sim).__name__ == "TrafficModel"
    win.select_sim("io")


def test_exercise_starter_wires_switches_and_sim(win):
    lab = next(l for l in win.labs_view.items if l.id == "02")
    win.labs_view.open_starter.emit(lab)
    assert win.sim_kind == "io" and win.program.symbols["I:1/1"] == "Stop (NC)"
    assert win.sim.switch(1, 1).normally_closed
    silo_lab = next(l for l in win.labs_view.items if l.id == "08")
    win.labs_view.list.setCurrentRow(win.labs_view.items.index(silo_lab))
    win.labs_view.sim_btn.click()
    assert win.sim_kind == "silo"
