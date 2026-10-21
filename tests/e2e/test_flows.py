"""End-to-end flows F01-F08 (docs/testing/test-plan.md), driven through the main window like a user.
Case ids match that plan."""

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QMessageBox

from plcyard.core.processor import Processor
from plcyard.formats import rsl
from plcyard.ui import theme
from plcyard.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"


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
    win.open(str(ROOT / "labs" / "solutions" / f"{lab_no}.rsl"))
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
    win.open(str(ROOT / "labs" / "solutions" / "02.rsl"))
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
