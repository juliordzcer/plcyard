"""End-to-end flows F01-F08 (docs/testing/test-plan.md), driven through the main window like a user.
Case ids match that plan."""


import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PySide6.QtWidgets import QMessageBox

from plcyard.core.processor import Processor
from plcyard import labs
from plcyard.formats import rsl
from plcyard.ui import theme
from plcyard.ui.main_window import MainWindow

SAMPLES = labs.SAMPLES
LABS = {lab.id: lab for lab in labs.load_all()}


@pytest.fixture
def win(qtbot, qapp, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, text, *a, **k: warnings.append((title, text)))
    theme.apply(qapp, "light")
    w = MainWindow()
    w.warnings = warnings
    w.dirty = False
    w.show()
    w.clock.stop()          # scans are driven by run() so the tests do not depend on wall time
    yield w
    w.dirty = False
    w.frame.stop()
    w.close()
    w.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)   # really free it: no slowdown
    qapp.processEvents()


def run(win, ms):
    for _ in range(int(ms / 10)):
        win.plc.tick(10)
    win._refresh()


def click(qtbot, win, slot, bit):
    qtbot.mouseClick(win.sim_view.switches[(slot, bit)], Qt.LeftButton)


def go(win, mode):
    win.panel.mode.set_mode(mode)
    assert win.plc.mode == mode


def set_ops(win, *values):
    c = win.ladder.canvas
    c.open_operand_editor()
    for f, v in zip(c.editor.fields, values):
        f.setText(v)
    c.editor.commit()


# -- F01 first program ---------------------------------------------------------------------
def test_F01_H1_first_program_switch_drives_lamp(win, qtbot):
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "I:1/0")
    win.bar.picked.emit("OTE")
    set_ops(win, "O:2/0")
    win.download()
    assert win.warnings == []
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 100)
    assert win.sim_view.lamps[(2, 0)].on
    click(qtbot, win, 1, 0)
    run(win, 100)
    assert not win.sim_view.lamps[(2, 0)].on


def test_F01_N1_unset_address_blocks_download(win):
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    win.download()
    assert win.warnings and win.warnings[0][0] == "The program was not downloaded"
    assert not win.downloaded


def test_F01_N2_word_on_bit_instruction_rejected(win):
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "N7:0")
    win.download()
    assert win.warnings and "N7:0/0" in win.warnings[0][1]


def test_F01_E1_edit_in_run_needs_download(win, qtbot):
    win.open(str(SAMPLES / "start-stop.rsl"))
    win.download()
    go(win, "RUN")
    win.ladder.canvas.sel = ("rung", 0)
    win.bar.picked.emit("RUNG")
    assert not win.in_sync and "download to apply" in win.panel.status.text()


# -- F02 open an example and run it ---------------------------------------------------------
def test_F02_H1_start_stop_sample(win, qtbot):
    win.open(str(SAMPLES / "start-stop.rsl"))
    assert win.windowTitle().startswith("start-stop.rsl")
    assert win.sim.switch(1, 1).normally_closed, "Stop (NC) symbol wires an NC switch"
    win.download()
    go(win, "RUN")
    run(win, 50)
    assert not win.sim_view.lamps[(2, 0)].on
    click(qtbot, win, 1, 0)                       # start
    run(win, 50)
    click(qtbot, win, 1, 0)
    run(win, 50)
    assert win.sim_view.lamps[(2, 0)].on, "seal-in keeps the motor on"
    click(qtbot, win, 1, 1)                       # stop
    run(win, 50)
    assert not win.sim_view.lamps[(2, 0)].on


@pytest.mark.parametrize("eol", ["\r\n", "\n"])
def test_F02_E1_line_endings(win, tmp_path, eol):
    text = (SAMPLES / "start-stop.rsl").read_bytes().decode("latin-1").replace("\r\n", "\n").replace("\n", eol)
    p = tmp_path / "x.rsl"
    p.write_bytes(text.encode("latin-1"))
    win.open(str(p))
    assert win.warnings == [] and len(win.program.main.rungs) > 1


def test_F02_N1_unsupported_instruction(win, tmp_path):
    p = tmp_path / "x.rsl"
    p.write_bytes(b"FILE,LAD 2\r\nSOR,0 XIC,I:1/0 PID,N7:0,N7:1,N7:2 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
    win.open(str(p))
    if not win.warnings:
        win.download()
    assert win.warnings, "an unknown instruction is reported, on open or on download"
    assert win.plc.mode != Processor.RUN


def test_F02_N2_not_an_rsl_file(win, tmp_path):
    p = tmp_path / "x.rsl"
    p.write_bytes(bytes(range(256)) * 4)
    win.open(str(p))
    assert win.warnings and win.path is None


# -- F03 debug with slow scan and data table -----------------------------------------------
def test_F03_H1_timer_visible_in_data_table(win):
    win.open(str(SAMPLES / "timer-counter.rsl"))
    win.download()
    go(win, "RUN")
    win.sim.set_pressed(1, 0, True)
    run(win, 1510)                                # first scan starts the timer at 0
    win.show_address("T4:0")
    m = win.table_view.model
    acc = m.columns().index("ACC")
    assert int(m.data(m.index(0, acc))) == 15


def test_F03_E1_radix_change_and_edit_while_running(win):
    win.open(str(SAMPLES / "timer-counter.rsl"))
    win.download()
    go(win, "RUN")
    win.show_address("N7:0")
    tv = win.table_view
    tv.radix_box.setCurrentText("Hex/BCD")
    m = tv.model
    assert m.setData(m.index(0, 0), "FF")
    run(win, 20)
    assert win.plc.dt.read_word("N7:0") == 255
    assert m.data(m.index(0, 0)).replace(" ", "").upper().endswith("FF")


# -- F04 change switch type ----------------------------------------------------------------
@pytest.mark.parametrize("nc,mom", [(False, False), (True, False), (False, True), (True, True)])
def test_F04_H1_switch_types(win, qtbot, nc, mom):
    view = win.sim_view
    view._set_type(1, 5, view.switches[(1, 5)], nc, mom)
    assert win.sim.signal(1, 5) is nc
    sw = view.switches[(1, 5)]
    qtbot.mousePress(sw, Qt.LeftButton, pos=QPoint(sw.width() // 2, sw.height() // 2))
    assert win.sim.signal(1, 5) is (not nc)
    qtbot.mouseRelease(sw, Qt.LeftButton, pos=QPoint(sw.width() // 2, sw.height() // 2))
    assert win.sim.signal(1, 5) is (nc if mom else not nc)


# -- F05 save --------------------------------------------------------------------------------
def test_F05_H1_round_trip_unchanged_program(win, tmp_path):
    src = SAMPLES / "timer-counter.rsl"
    dst = tmp_path / "copy.rsl"
    win.open(str(src))
    win.path = dst
    win.save()
    assert dst.read_bytes() == src.read_bytes()
    assert not win.windowTitle().startswith("•")


def test_F05_E1_accents_kept_emoji_reported(win, tmp_path):
    win.open(str(SAMPLES / "start-stop.rsl"))
    win.program.main.rungs[0].comment = "Válvula ñ 🚀"
    win.path = tmp_path / "x.rsl"
    win.save()
    assert win.warnings and "🚀" in win.warnings[0][1]
    assert rsl.load(win.path).main.rungs[0].comment == "Válvula ñ ?"


def test_F05_N1_unwritable_path(win, tmp_path):
    win.open(str(SAMPLES / "start-stop.rsl"))
    win.path = tmp_path / "missing-dir" / "x.rsl"
    win.dirty = True
    win.save()
    assert win.warnings and win.warnings[0][0] == "Could not save"
    assert win.dirty, "still unsaved"


# -- F06 clear data table ------------------------------------------------------------------
def test_F06_H1_clear_data_table(win):
    win.open(str(SAMPLES / "timer-counter.rsl"))
    win.download()
    win.plc.dt.write_word("N7:3", 42)
    win.plc.dt.write_word("C5:0.ACC", 4)
    win.plc.dt.write_bit("B3:0/2", True)
    win.clear_data()
    dt = win.plc.dt
    assert dt.read_word("N7:3") == 0 and dt.read_word("C5:0.ACC") == 0 and not dt.read_bit("B3:0/2")


# -- F07 exercises on silo and traffic -----------------------------------------------------
@pytest.mark.parametrize("lab_no,kind", [("08", "silo"), ("10", "traffic")])
def test_F07_H1_reference_solution_runs_on_its_simulation(win, lab_no, kind):
    win.select_sim(kind)
    win.open(str(LABS[lab_no].solution))
    assert win.sim_kind == kind
    win.download()
    assert win.warnings == []
    go(win, "RUN")
    run(win, 5000)
    assert win.plc.mode == Processor.RUN and win.plc.scan_count > 0


def test_F07_H2_new_program_for_exercise(win, qtbot):
    win.labs_dock.show()
    lv = win.labs_view
    i = next(k for k, lab in enumerate(lv.items) if lab.simulation == "silo")
    lv.list.setCurrentRow(i)
    qtbot.mouseClick(lv.start_btn, Qt.LeftButton)
    assert win.sim_kind == "silo" and win.path is None
    assert win.program.symbols == lv.items[i].starter().symbols


# -- F08 subroutines -----------------------------------------------------------------------
SBR = ("FILE,LAD 2\r\nSOR,0 JSR,U:3 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n"
       "FILE,SBR 3\r\nSOR,0 XIC,I:1/0 OTE,O:2/3 EOR,0\r\nRCM,\r\nSOR,1 RET EOR,1\r\nRCM,\r\nSOR,2 END,2\r\nRCM,\r\n")


def test_F08_H1_subroutine_drives_output(win, qtbot, tmp_path):
    p = tmp_path / "sbr.rsl"
    p.write_bytes(SBR.encode("latin-1"))
    win.open(str(p))
    win.download()
    assert win.warnings == []
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 50)
    assert win.sim_view.lamps[(2, 3)].on


def test_F08_N1_jsr_to_missing_file(win, tmp_path):
    p = tmp_path / "sbr.rsl"
    p.write_bytes(SBR.replace("U:3", "U:5").encode("latin-1"))
    win.open(str(p))
    win.download()
    assert win.warnings and "subroutine file 5" in win.warnings[0][1]


# -- F09 check my program (new: not in the original) ---------------------------------------
def test_F09_H1_check_reference_solution(win, qtbot):
    win.labs_dock.show()
    lv = win.labs_view
    lv.list.setCurrentRow(1)                                   # 02 start/stop
    win.open(str(LABS["02"].solution))
    plc_mode = win.plc.mode
    qtbot.mouseClick(lv.check_btn, Qt.LeftButton)
    assert lv.result.isVisible() and "All requirements met" in lv.result.toPlainText()
    assert win.plc.mode == plc_mode, "checking does not touch the PLC on screen"


def test_F09_N1_check_empty_program_lists_failures(win, qtbot):
    win.labs_dock.show()
    lv = win.labs_view
    lv.list.setCurrentRow(1)
    qtbot.mouseClick(lv.start_btn, Qt.LeftButton)
    qtbot.mouseClick(lv.check_btn, Qt.LeftButton)
    text = lv.result.toPlainText()
    assert "requirements met" in text and "✘" in text
    lv.list.setCurrentRow(2)
    assert not lv.result.isVisible(), "results belong to the exercise they were run for"


def test_F05_E2_bundled_files_are_never_overwritten(win, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    asked = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (asked.append(1), ("", ""))[1])
    sol = LABS["10"].solution
    before = sol.read_bytes()
    win.open(str(sol))
    win.program = labs.load_all()[0].starter()
    win.save()
    assert asked and sol.read_bytes() == before


def test_F02_H2_open_example_menu(win):
    menu = next(a.menu() for a in win.menuBar().actions() if a.text() == "&File")
    examples = next(a.menu() for a in menu.actions() if a.menu() and "example" in a.text())
    names = [a.text() for a in examples.actions()]
    assert "Start stop" in names
    examples.actions()[names.index("Start stop")].trigger()
    assert win.path == SAMPLES / "start-stop.rsl"


def test_F05_H2_save_and_reopen_project(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    target = tmp_path / "mine"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "PLCYard projects (*.plcy)"))
    win.open(str(SAMPLES / "start-stop.rsl"))
    win.save()                                              # bundled file: goes to Save as
    assert win.path == tmp_path / "mine.plcy" and win.path.exists()
    win.open(str(win.path))
    assert win.warnings == [] and win.windowTitle().startswith("mine.plcy")
    win.download()
    assert win.warnings == [] and win.downloaded


def test_F05_N2_other_controller_cannot_be_saved_as_rsl(win, tmp_path, monkeypatch):
    from plcyard.core import profiles
    from plcyard.core.profiles.slc500 import Slc500
    other = type("Other", (Slc500,), {"name": "other"})()
    monkeypatch.setitem(profiles.PROFILES, "other", other)
    win.open(str(SAMPLES / "start-stop.rsl"))
    win.program.profile = "other"
    win.path = tmp_path / "x.rsl"
    win.save()
    assert win.warnings and "SLC 500 ladder only" in win.warnings[0][1]


# -- F10 Logix controller (Studio 5000 style) -----------------------------------------------------
def test_F10_H1_logix_program_from_scratch(win, qtbot):
    nf = next(a.menu() for a in win.menuBar().actions() if a.text() == "&File")
    sub = next(a.menu() for a in nf.actions() if a.menu() and "controller" in a.text())
    next(a for a in sub.actions() if a.text().startswith("Logix")).trigger()
    assert win.program.profile == "logix" and win.tabs.tabText(0) == "MainRoutine"
    assert win.sim_view.switches[(1, 0)].toolTip().startswith("Local:1:I.Data.0")
    win.table_dock.show()
    tv = win.tags_view
    assert win.table_dock.windowTitle() == "Tags"
    tv.add_tag()
    tv.table.item(0, 0).setText("Motor")
    assert list(win.program.tags) == ["Motor"]
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "Local:1:I.Data.0")
    win.bar.picked.emit("OTE")
    set_ops(win, "Motor")
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "Motor")
    win.bar.picked.emit("OTE")
    set_ops(win, "Local:2:O.Data.0")
    win.download()
    assert win.warnings == [] and win.plc.profile.name == "logix"
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 50)
    assert win.sim_view.lamps[(2, 0)].on
    assert tv.table.item(0, 2).text() == "1", "live value in the tag list"
    assert "Local:1:I" in win.panel.io_words.text()


def test_F10_N1_logix_unknown_tag_blocks_download(win):
    win.new("logix")
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "Pump")
    win.download()
    assert win.warnings and "Pump does not exist" in win.warnings[0][1]


def test_F10_E1_back_to_slc_after_logix(win, qtbot):
    win.new("logix")
    win.open(str(SAMPLES / "start-stop.rsl"))
    assert win.table_dock.windowTitle() == "Data table" and win.tabs.count() == 8
    win.download()
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 50)
    assert win.sim_view.lamps[(2, 0)].on and win.plc.profile.name == "slc500"


# -- F11 S7-1200/1500 controller (TIA Portal style) ------------------------------------------------
def test_F11_H1_s7_program_with_timer(win, qtbot):
    win.new("s7")
    assert win.program.profile == "s7" and win.sim_view.switches[(1, 0)].toolTip().startswith("%I0.0")
    win.table_dock.show()
    tv = win.tags_view
    assert "Address" in tv.columns
    tv.add_tag()
    tv.table.item(0, 0).setText("Delay")
    tv.table.cellWidget(0, 1).setCurrentText("IEC_TIMER")
    assert win.program.tags == {"Delay": {"type": "IEC_TIMER"}}
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "i0.0")
    assert win.program.main.rungs[0].body.items[0].operands == ["%I0.0"], "address normalised"
    win.bar.picked.emit("TON")
    set_ops(win, "Delay", "T#200ms")
    win.download()
    assert win.warnings == [], win.warnings
    win.ladder.canvas.sel = ("rung", 0)
    win.bar.picked.emit("OTE")
    set_ops(win, "%Q0.0")
    assert [i.mnemonic for i in win.program.main.rungs[0].body.items] == ["XIC", "TON", "OTE"]
    win.download()
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 100)
    assert not win.sim_view.lamps[(2, 0)].on
    run(win, 150)
    assert win.sim_view.lamps[(2, 0)].on, "TON passes Q to the coil after PT"
    assert "%IW0" in win.panel.io_words.text()


def test_F11_N1_s7_bad_address_in_tag_list_is_rejected(win):
    win.new("s7")
    win.table_dock.show()
    tv = win.tags_view
    tv.add_tag()
    tv.table.item(0, tv.col("Address")).setText("%MW0")      # Bool needs a bit
    assert "needs a bit address" in tv.message.text() and "address" not in win.program.tags["Tag1"]


# -- F12 analog tank and PID -----------------------------------------------------------------------
def test_F12_H1_tank_pid_exercise(win, qtbot):
    win.labs_dock.show()
    lv = win.labs_view
    i = next(k for k, lab in enumerate(lv.items) if lab.id == "12")
    lv.list.setCurrentRow(i)
    qtbot.mouseClick(lv.start_btn, Qt.LeftButton)
    assert win.program.profile == "logix" and win.sim_kind == "tank"
    assert "Local:7:I.Ch0Data" in win.sim_view.canvas.a("I", 0)
    win.open(str(LABS["12"].solution))
    qtbot.mouseClick(lv.check_btn, Qt.LeftButton)
    assert "All requirements met" in lv.result.toPlainText()
    win.download()
    go(win, "RUN")
    win.sim.setpoint_knob = 50.0
    run(win, 60000)
    assert abs(win.sim.level - 50.0) < 2.0
    assert len(win.sim.trend) > 100


def test_F12_N1_empty_program_fails_tank_checks(win, qtbot):
    win.labs_dock.show()
    lv = win.labs_view
    lv.list.setCurrentRow(next(k for k, lab in enumerate(lv.items) if lab.id == "11"))
    qtbot.mouseClick(lv.start_btn, Qt.LeftButton)
    qtbot.mouseClick(lv.check_btn, Qt.LeftButton)
    assert "✘" in lv.result.toPlainText() and "✔" not in lv.result.toPlainText()


# -- F13 structured text ---------------------------------------------------------------------------
def test_F13_H1_s7_scl_program(win, qtbot):
    nf = next(a.menu() for a in win.menuBar().actions() if a.text() == "&File")
    sub = next(a.menu() for a in nf.actions() if a.menu() and "controller" in a.text())
    next(a for a in sub.actions() if a.text().startswith("S7") and "structured" in a.text()).trigger()
    assert win.program.main.language == "ST" and win.editor_stack.currentWidget() is win.st_editor
    assert win.tabs.tabText(0).endswith("(ST)") and not win.bar.isVisible()
    ed = win.st_editor
    ed.edit.setPlainText('"Delay".TON(IN := %I0.0, PT := T#200ms);\n%Q0.0 := "Delay".Q;\n')
    assert "Delay does not exist" in "\n".join(ed.check())
    assert 1 in ed.edit.error_lines
    win.table_dock.show()
    win.tags_view.add_tag()
    win.tags_view.table.item(0, 0).setText("Delay")
    win.tags_view.table.cellWidget(0, 1).setCurrentText("IEC_TIMER")
    assert ed.check() == [] and not ed.problems.isVisible()
    assert [ed.watch.item(r, 0).text() for r in range(ed.watch.rowCount())] == ["%I0.0", "%Q0.0", "Delay.Q", "Delay"]
    win.download()
    assert win.warnings == []
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 300)
    assert win.sim_view.lamps[(2, 0)].on
    assert ed.watch.item(1, 1).text() == "TRUE"


def test_F13_N1_syntax_error_blocks_download(win):
    win.new("logix", "ST")
    win.st_editor.edit.setPlainText("Motor := Start\n")
    assert "line 1" in win.st_editor.check()[0] and "missing ;" in win.st_editor.check()[0]
    win.download()
    assert win.warnings and "line 1" in win.warnings[0][1]


def test_F13_E1_save_and_reopen_st(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    win.new("logix", "ST")
    win.st_editor.edit.setPlainText("Local:2:O.Data.0 := Local:1:I.Data.0;\n")
    target = tmp_path / "st"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "PLCYard projects (*.plcy)"))
    win.save()
    win.open(str(tmp_path / "st.plcy"))
    assert win.st_editor.edit.toPlainText() == "Local:2:O.Data.0 := Local:1:I.Data.0;\n"
