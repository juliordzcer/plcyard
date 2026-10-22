"""End-to-end flows F01-F16 (docs/testing/test-plan.md), driven through the main window like a user.
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
OLD_RSL = ("FILE,LAD 2\r\nSOR,0 XIC,I:1/1 BST,1 XIC,I:1/0 NXB,1 XIC,O:2/0 BND,1 OTE,O:2/0 EOR,0\r\nRCM,\r\n"
           "SOR,1 XIC,O:2/0 OTE,O:2/1 EOR,1\r\nRCM,\r\nSOR,2 END,2\r\nRCM,\r\nSYMBOLS\r\nI:1/1 Stop (NC)\r\n")
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
    set_ops(win, "%I0.0")
    win.bar.picked.emit("OTE")
    set_ops(win, "%Q0.0")
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
    set_ops(win, "%MW0")
    win.download()
    assert win.warnings and "%MW0 is a INT; needs a BOOL" in win.warnings[0][1]


def test_F01_E1_edit_in_run_needs_download(win, qtbot):
    win.open(str(SAMPLES / "start-stop.plcy"))
    win.download()
    go(win, "RUN")
    win.ladder.canvas.sel = ("rung", 0)
    win.bar.picked.emit("RUNG")
    assert not win.in_sync and "download to apply" in win.panel.status.text()


# -- F02 open an example and run it ---------------------------------------------------------
def test_F02_H1_start_stop_sample(win, qtbot):
    win.open(str(SAMPLES / "start-stop.plcy"))
    assert win.windowTitle().startswith("start-stop.plcy")
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
    text = OLD_RSL.replace("\r\n", "\n").replace("\n", eol)
    p = tmp_path / "x.rsl"
    p.write_bytes(text.encode("latin-1"))
    win.open(str(p))
    assert win.warnings == [] and len(win.program.main.rungs) > 1


def test_F02_N1_unsupported_instruction(win, tmp_path):
    p = tmp_path / "x.rsl"
    p.write_bytes(b"FILE,LAD 2\r\nSOR,0 XIC,I:1/0 PIX,N7:0,N7:1,N7:2 EOR,0\r\nRCM,\r\nSOR,1 END,1\r\nRCM,\r\n")
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


# -- F03 debug: live values in the tag list ---------------------------------------------------
def test_F03_H1_timer_visible_in_the_tag_list(win):
    win.open(str(SAMPLES / "timer-counter.plcy"))
    win.download()
    go(win, "RUN")
    win.sim.set_pressed(1, 0, True)
    run(win, 1510)                                # first scan starts the timer at 0
    win.table_dock.show()
    tv = win.tags_view
    row = next(r for r in range(tv.table.topLevelItemCount()) if tv.row(r).text(0) == "Timers")
    tv.row(row).setExpanded(True)
    first = tv.row(row).child(0)
    first.setExpanded(True)
    acc = next(first.child(k) for k in range(first.childCount()) if first.child(k).text(0) in (".ACC", ".ET"))
    win._refresh()
    assert acc.text(tv.col("Value")) == "1500"


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
def test_F05_N1_unwritable_path(win, tmp_path):
    win.open(str(SAMPLES / "start-stop.plcy"))
    win.path = tmp_path / "missing-dir" / "x.plcy"
    win.dirty = True
    win.save()
    assert win.warnings and win.warnings[0][0] == "Could not save"
    assert win.dirty, "still unsaved"


# -- F06 clear data ------------------------------------------------------------------------
def test_F06_H1_clear_data(win):
    win.open(str(SAMPLES / "timer-counter.plcy"))
    win.download()
    win.plc.dt.write_word("Counters[0].ACC", 4)
    win.plc.dt.write_word("%MW10", 42)
    win.clear_data()
    assert win.plc.dt.read_word("Counters[0].ACC") == 0 and win.plc.dt.read_word("%MW10") == 0


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


def test_F08_N1_jsr_to_missing_routine(win, tmp_path):
    p = tmp_path / "sbr.rsl"
    p.write_bytes(SBR.replace("U:3", "U:5").encode("latin-1"))
    win.open(str(p))
    win.download()
    assert win.warnings and "routine SBR5 does not exist" in win.warnings[0][1]


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
    assert win.path == SAMPLES / "start-stop.plcy"


def test_F05_H2_save_and_reopen_project(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    target = tmp_path / "mine"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "PLCYard projects (*.plcy)"))
    win.open(str(SAMPLES / "start-stop.plcy"))
    win.save()                                              # bundled file: goes to Save as
    assert win.path == tmp_path / "mine.plcy" and win.path.exists()
    win.open(str(win.path))
    assert win.warnings == [] and win.windowTitle().startswith("mine.plcy")
    win.download()
    assert win.warnings == [] and win.downloaded


# -- F10 tags and notations ------------------------------------------------------------------------
def test_F10_H1_program_with_tags_in_notation_a(win, qtbot):
    win.set_notation("A")
    assert win.sim_view.switches[(1, 0)].toolTip().startswith("Local:1:I.Data.0")
    win.table_dock.show()
    tv = win.tags_view
    assert win.table_dock.windowTitle() == "Tags"
    tv.add_tag()
    tv.item(0, 0).setText("Motor")
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
    assert win.program.main.rungs[1].body.items[1].operands == ["%Q0.0"], "stored in the canonical form"
    win.download()
    assert win.warnings == []
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 50)
    assert win.sim_view.lamps[(2, 0)].on
    assert tv.item(0, tv.col("Value")).text() == "1", "live value in the tag list"
    assert "Local:1:I" in win.panel.io_words.text()


def test_F10_N1_unknown_tag_blocks_download(win):
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "Pump")
    win.download()
    assert win.warnings and "Pump does not exist" in win.warnings[0][1]


def test_F10_E1_switching_notation_keeps_the_program(win):
    from plcyard.formats import plcy
    win.open(str(SAMPLES / "timer-counter.plcy"))
    before = plcy.dumps(win.program)
    win.set_notation("B")
    assert win.sim_view.switches[(1, 0)].toolTip().startswith("%I0.0")
    win.set_notation("A")
    assert plcy.dumps(win.program) == before


# -- F11 timer box passes Q, tag addresses -------------------------------------------------------------
def test_F11_H1_timer_with_iec_names(win, qtbot):
    win.set_notation("B")
    win.table_dock.show()
    tv = win.tags_view
    assert "Address" in tv.columns
    tv.add_tag()
    tv.item(0, 0).setText("Delay")
    tv.set_type(0, "TIMER")
    assert win.program.tags == {"Delay": {"type": "TIMER"}}
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "i0.0")
    assert win.program.main.rungs[0].body.items[0].operands == ["%I0.0"], "address normalised"
    win.bar.picked.emit("TON")
    set_ops(win, "Delay", "T#200ms")
    win.ladder.canvas.sel = ("rung", 0)
    win.bar.picked.emit("OTE")
    set_ops(win, "%Q0.0")
    assert [i.mnemonic for i in win.program.main.rungs[0].body.items] == ["XIC", "TON", "OTE"]
    win.download()
    assert win.warnings == [], win.warnings
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 100)
    assert not win.sim_view.lamps[(2, 0)].on
    run(win, 150)
    assert win.sim_view.lamps[(2, 0)].on, "TON passes Q to the coil after PT"
    assert "%IW0" in win.panel.io_words.text()
    win.set_notation("A")


def test_F11_N1_bad_address_in_tag_list_is_rejected(win):
    win.table_dock.show()
    tv = win.tags_view
    tv.add_tag()
    tv.item(0, tv.col("Address")).setText("%MW0")      # BOOL needs a bit
    assert "needs a bit address" in tv.message.text() and "address" not in win.program.tags["Tag1"]


# -- F12 analog tank and PID -----------------------------------------------------------------------
def test_F12_H1_tank_pid_exercise(win, qtbot):
    win.labs_dock.show()
    lv = win.labs_view
    i = next(k for k, lab in enumerate(lv.items) if lab.id == "12")
    lv.list.setCurrentRow(i)
    qtbot.mouseClick(lv.start_btn, Qt.LeftButton)
    assert win.sim_kind == "tank" and win.sim_view.canvas.a("I", 0) in ("%IW64", "Local:7:I.Ch0Data")
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
def test_F13_H1_structured_text_program(win, qtbot):
    nf = next(a.menu() for a in win.menuBar().actions() if a.text() == "&File")
    next(a for a in nf.actions() if "structured text" in a.text()).trigger()
    assert win.program.main.language == "ST" and win.st_editor is not None
    assert win.docs.tabText(0).endswith("(ST)") and not win.bar.isVisible()
    ed = win.st_editor
    ed.edit.setPlainText('"Delay".TON(IN := %I0.0, PT := T#200ms);\n%Q0.0 := "Delay".Q;\n')
    assert "Delay does not exist" in "\n".join(ed.check())
    assert 1 in ed.edit.error_lines
    win.table_dock.show()
    win.tags_view.add_tag()
    win.tags_view.item(0, 0).setText("Delay")
    win.tags_view.set_type(0, "TIMER")
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
    win.new(language="ST")
    win.st_editor.edit.setPlainText("Motor := Start\n")
    assert "line 1" in win.st_editor.check()[0] and "missing ;" in win.st_editor.check()[0]
    win.download()
    assert win.warnings and "line 1" in win.warnings[0][1]


def test_F13_E1_save_and_reopen_st(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    win.new(language="ST")
    win.st_editor.edit.setPlainText("%Q0.0 := %I0.0;\n")
    target = tmp_path / "st"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), "PLCYard projects (*.plcy)"))
    win.save()
    win.open(str(tmp_path / "st.plcy"))
    assert win.st_editor.edit.toPlainText() == "%Q0.0 := %I0.0;\n"


# -- F14 several routines, blocks, data types, forcing -----------------------------------------------
def add_routine(win, monkeypatch, name, kind, language="LD"):
    from plcyard.ui import main_window
    monkeypatch.setattr(main_window.NewRoutineDialog, "exec", lambda self: main_window.QDialog.Accepted)
    monkeypatch.setattr(main_window.NewRoutineDialog, "values", lambda self: (name, kind, language))
    win._tree_action("add_routine", None)


def test_F14_H1_main_ladder_calls_an_st_routine(win, qtbot, monkeypatch):
    win.new()
    assert win.tree_dock.windowTitle() == "Project"
    add_routine(win, monkeypatch, "Calc", "SBR", "ST")
    assert win.docs.count() == 2 and win.docs.tabText(1) == "Calc (ST)" and win.st_editor is not None
    win.st_editor.edit.setPlainText("%Q0.0 := %I0.0;\n")
    win.docs.setCurrentIndex(0)
    assert win.ladder is not None and win.bar.isVisible()
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("JSR")
    set_ops(win, "Calc")
    win.download()
    assert win.warnings == [], win.warnings
    go(win, "RUN")
    click(qtbot, win, 1, 0)
    run(win, 50)
    assert win.sim_view.lamps[(2, 0)].on
    from plcyard.ui.main_window import rename_routine
    rename_routine(win.program, "Calc", "Compute")
    assert win.program.main.rungs[0].body.items[0].operands == ["Compute"]


def test_F14_H2_function_block_with_interface(win, monkeypatch):
    win.new()
    add_routine(win, monkeypatch, "Motor", "FB")
    doc = win.doc
    assert doc.interface is not None and win.docs.tabText(win.docs.currentIndex()) == "Motor [FB]"
    doc.interface.add_member("Input")
    assert win.program.files[3].interface == {"Input": {"Member1": "BOOL"}}
    win.tags_view.add_tag()
    win.tags_view.set_type(0, "Motor")
    assert win.program.tags["Tag1"]["type"] == "Motor"
    prog = win.tree.topLevelItem(1)
    labels = [prog.child(k).text(0) for k in range(prog.childCount())]
    instances = prog.child(labels.index("Block instances"))
    assert "Motor [FB]" in labels and instances.child(0).text(0) == "Tag1 [Motor]"


def test_F14_H3_data_type_and_array_tags(win, monkeypatch):
    win.new()
    monkeypatch.setattr("plcyard.ui.main_window.QInputDialog.getText", lambda *a, **k: ("Pump", True))
    win._tree_action("add_type", None)
    doc = win.doc
    doc.add_member()
    assert win.program.types == {"Pump": {"Member1": "BOOL"}}
    tv = win.tags_view
    tv.add_tag()
    tv.set_type(0, "Pump[2]")
    assert win.program.tags["Tag1"]["type"] == "Pump[2]" and tv.message.text() == ""
    tv.row(0).setExpanded(True)
    assert tv.row(0).childCount() == 2 and tv.row(0).child(1).text(0) == "[1]"


def test_F14_H4_force_an_input_from_the_tag_list(win, qtbot):
    win.open(str(SAMPLES / "start-stop.plcy"))
    win.download()
    go(win, "RUN")
    win.force("%I0.0", True)
    run(win, 50)
    win._refresh()
    assert win.sim_view.lamps[(2, 0)].on and not win.panel.forces.isHidden()
    win.force("%M0.0", True)
    assert "only I/O points" in win.statusBar().currentMessage()
    win.remove_forces()
    assert win.plc.forces == {}


def test_F14_N1_bad_names_are_refused(win, monkeypatch):
    win.new()
    add_routine(win, monkeypatch, "1bad", "SBR")
    add_routine(win, monkeypatch, "Main", "SBR")
    assert len(win.program.files) == 1 and len(win.warnings) == 2


# -- F15 drag inputs and outputs from the simulation onto the ladder ---------------------------------
def test_F15_H1_drop_io_on_rungs_and_instructions(win):
    win.new()
    c = win.canvas
    c.drop_address("Local:1:I.Data.0", ("newrung", 0))
    c.drop_address("Local:2:O.Data.3", (0, None, None, None))
    items = win.program.main.rungs[0].body.items
    assert [(i.mnemonic, i.operands) for i in items] == [("XIC", ["%I0.0"]), ("OTE", ["%Q0.3"])]
    rect = c._instr_rect(0, (0,))
    target = c._address_target(rect.center(), "Local:1:I.Data.5")
    assert target[0] == "operand"
    c.drop_address("Local:1:I.Data.5", target)
    assert win.program.main.rungs[0].body.items[0].operands == ["%I0.5"]
    win.download()
    assert win.warnings == []


def test_F15_H2_analog_channel_fills_a_value_operand(win):
    win.new()
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("MOV")
    c = win.canvas
    rect = c._instr_rect(0, (0,))
    c.drop_address("%IW64", c._address_target(rect.center(), "%IW64"))
    c.drop_address("%QW64", c._address_target(rect.center(), "%QW64"))
    assert win.program.main.rungs[0].body.items[0].operands == ["%IW64", "%QW64"]


def test_F15_H3_sim_widgets_carry_their_address(win):
    from plcyard.ui.io_drag import Draggable
    win.set_notation("B")
    assert win.sim_view.switches[(1, 0)].address == "%I0.0"
    assert win.sim_view.lamps[(2, 1)].findChild(Draggable).address == "%Q0.1"
    win.set_notation("A")
    win.select_sim("silo")
    win.sim_view.canvas.grab()
    assert win.sim_view.canvas.hotspot_at(win.sim_view.canvas._spots[0][0].center()) is not None


# -- F16 online bar -------------------------------------------------------------------------------------
def test_F16_H1_offline_online_upload(win, monkeypatch):
    win.open(str(SAMPLES / "start-stop.plcy"))
    assert win.panel.online_btn.text() == "Offline"
    win.download()
    go(win, "RUN")
    assert win.panel.online_btn.text() == "Online · Run" and win.panel.edits.text() == "No Edits"
    win.go_offline()
    win.panel.mode.set_mode("PGM")
    assert win.plc.mode == Processor.RUN, "offline, the mode cannot be changed"
    win.go_online()
    assert win.online and win.panel.online_btn.text() == "Online · Run"
    win.bar.picked.emit("RUNG")
    assert win.panel.edits.text() == "Edits pending"
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Discard)
    win.upload()
    assert win.in_sync and len(win.program.main.rungs) == len(win.plc.program.main.rungs)
    win.panel.set_folded(True)
    assert win.panel.details.isHidden()


def test_F16_H2_download_goes_online_in_program_mode(win):
    win.new()
    win.bar.picked.emit("RUNG")
    win.bar.picked.emit("XIC")
    set_ops(win, "%I0.0")
    win.bar.picked.emit("OTE")
    set_ops(win, "%Q0.0")
    win.download()
    assert win.panel.online_btn.text() == "Online · Program"
    assert [l.label.text() for l in win.panel.leds.values()] == ["RUN", "FORCE", "FAULT", "I/O"]


# -- F17 PID setup ---------------------------------------------------------------------------------------
def test_F17_H1_pid_setup_writes_start_values_and_the_running_pid(win, monkeypatch):
    from plcyard.ui.pid_setup import PidSetup
    win.open(str(LABS["12"].solution))
    win.download()
    go(win, "RUN")
    seen = {}

    def fake_exec(dlg):
        assert [dlg.tabs.tabText(k) for k in range(dlg.tabs.count())] == ["Tuning", "Configuration", "Alarms", "Scaling"]
        dlg.fields["KP"].setValue(2.5)
        dlg.fields["PE"].setCurrentIndex(1)
        seen["label"] = dlg._label_KI.text()
        dlg.fields["PVH"].setValue(95.0)
        dlg.accept()
    monkeypatch.setattr(PidSetup, "exec", fake_exec)
    win.pid_setup("LevelPID")
    assert seen["label"].startswith("Reset time")
    start = win.program.tags["LevelPID"]["value"]
    assert start["KP"] == 2.5 and start["PE"] is True and start["PVH"] == 95.0
    assert win.plc.dt.element("LevelPID")["KP"] == 2.5, "applied to the running PID too"
