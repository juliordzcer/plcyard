"""Main window: menus, PLC strip, simulation | ladder split, file tabs, status bar."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QSlider, QSplitter, QStackedWidget, QTabBar,
                               QVBoxLayout, QWidget)

from .. import grader, labs
from ..core import profiles
from ..core.processor import Processor
from ..core.program import Program
from .. import formats
from ..sims.io_panel import IoPanelModel
from . import theme
from ..sims.silo import SiloModel
from ..sims.traffic import TrafficModel
from .io_panel_view import IoPanelView
from .sim_views import SiloView, TrafficView
from .datatable_view import DataTableView
from .tags_view import TagsView
from .instruction_bar import InstructionBar
from .labs_view import LabsView
from .ladder_view import LadderView
from .primitives import ModeSelector

TICK_MS = 10
FRAME_MS = 33


class PlcPanel(QFrame):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(theme.layout("plc-strip-h"))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(12)
        self.status = QLabel()
        self.status.setMinimumWidth(170)
        self.download = QPushButton("Download")
        self.download.setProperty("variant", "primary")
        self.download.setToolTip("Send the program to the PLC (Ctrl+D)")
        self.mode = ModeSelector("PGM")
        self.clear_fault = QPushButton("Clear fault")
        self.clear_fault.setProperty("variant", "danger")
        self.clear_fault.setVisible(False)
        self.step = QPushButton("Step")
        self.step.setToolTip("Run one scan (F10)")
        self.step.setEnabled(False)
        self.scans = QLabel("0 scans")
        self.scans.setFont(theme.font("mono", "sm"))
        self.scans.setProperty("muted", "true")
        self.io_words = QLabel()
        self.io_words.setFont(theme.font("mono", "sm"))
        self.io_words.setProperty("muted", "true")
        speed_label = QLabel("Speed")
        speed_label.setProperty("muted", "true")
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(1, 10)
        self.speed.setValue(10)
        self.speed.setFixedWidth(140)
        self.speed.setAccessibleName("Simulation speed")
        for w in (self.status, self.clear_fault, self.download, self.mode, self.step, self.scans, self.io_words):
            lay.addWidget(w)
        lay.addStretch(1)
        lay.addWidget(speed_label)
        lay.addWidget(self.speed)

    def set_status(self, text: str, kind: str = "") -> None:
        self.status.setText(text)
        self.status.setProperty("status", kind)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None):
        super().__init__()
        self.plc = Processor()
        self.plc.tracing = True
        self.sim = IoPanelModel()
        self.plc.device = self.sim
        self.program = Program.new()
        self.path: Path | None = None
        self.downloaded = False      # the PLC holds a program
        self.in_sync = False         # ...and it is the one in the editor
        self.dirty = False           # unsaved edits
        self.sim_kind = "io"

        self.panel = PlcPanel()
        self.sim_view = IoPanelView(self.sim)
        self.sim_scroll = sim_scroll = QScrollArea()
        sim_scroll.setWidget(self.sim_view)
        sim_scroll.setWidgetResizable(True)
        sim_scroll.setMinimumWidth(theme.layout("sim-pane-min-w"))
        self.ladder = LadderView()
        self.tabs = QTabBar()
        self.tab_files: list[int] = []
        self.tabs.currentChanged.connect(
            lambda i: 0 <= i < len(self.tab_files) and self.ladder.canvas.set_file(self.tab_files[i]))

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.bar = InstructionBar()
        self.bar.picked.connect(self.ladder.canvas.insert_mnemonic)
        rl.addWidget(self.bar)
        rl.addWidget(self.ladder, 1)
        rl.addWidget(self.tabs)
        self.ladder.canvas.changed.connect(self._edited)
        split = QSplitter()
        split.addWidget(sim_scroll)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([620, 780])

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self.panel)
        cl.addWidget(split, 1)
        self.setCentralWidget(central)

        self.table_view = DataTableView(self.plc.dt, self.program.symbols)
        self.tags_view = TagsView()
        self.tags_view.edited.connect(self._edited)
        self.data_stack = QStackedWidget()
        self.data_stack.addWidget(self.table_view)
        self.data_stack.addWidget(self.tags_view)
        self.table_dock = QDockWidget("Data table", self)
        self.table_dock.setObjectName("datatable")
        self.table_dock.setWidget(self.data_stack)
        self.table_dock.setMinimumWidth(theme.layout("dock-w"))
        self.addDockWidget(Qt.RightDockWidgetArea, self.table_dock)
        self.table_dock.hide()

        self.labs_view = LabsView()
        self.labs_dock = QDockWidget("Exercises", self)
        self.labs_dock.setObjectName("labs")
        self.labs_dock.setWidget(self.labs_view)
        self.labs_dock.setMinimumWidth(theme.layout("dock-w"))
        self.addDockWidget(Qt.RightDockWidgetArea, self.labs_dock)
        self.labs_dock.hide()
        self.labs_view.load_simulation.connect(self.select_sim)
        self.labs_view.open_starter.connect(self.start_lab)
        self.labs_view.check_requested.connect(self.check_lab)

        self._menus()
        self.panel.download.clicked.connect(self.download)
        self.panel.mode.modeChanged.connect(self.set_mode)
        self.panel.step.clicked.connect(self.step)
        self.panel.clear_fault.clicked.connect(self.clear_fault)
        self._fault_shown = None

        self.clock = QTimer(self)
        self.clock.timeout.connect(self._tick)
        self.clock.start(TICK_MS)
        self.frame = QTimer(self)
        self.frame.timeout.connect(self._refresh)
        self.frame.start(FRAME_MS)

        if path:
            self.open(path)
        else:
            self._show_program()
        self.resize(1400, 860)

    # -- menus --------------------------------------------------------------
    def _menus(self) -> None:
        mb = self.menuBar()

        def act(menu, text, slot, shortcut=None):
            a = QAction(text, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            menu.addAction(a)
            return a

        f = mb.addMenu("&File")
        act(f, "&New", self.new, QKeySequence.New)
        nf = f.addMenu("New for controller")
        for prof in profiles.PROFILES.values():
            act(nf, f"{prof.title} program", lambda _=False, n=prof.name: self.new(n))
        act(f, "&Open…", lambda: self.open(), QKeySequence.Open)
        ex = f.addMenu("Open &example")
        for path in sorted(labs.SAMPLES.glob("*.rsl")):
            act(ex, path.stem.replace("-", " ").capitalize(), lambda _=False, p=path: self.open(str(p)))
        act(f, "&Save", self.save, QKeySequence.Save)
        act(f, "Save &as…", self.save_as, QKeySequence.SaveAs)
        f.addSeparator()
        act(f, "&Quit", self.close, QKeySequence.Quit)
        e = mb.addMenu("&Edit")
        undo = self.ladder.canvas.undo.createUndoAction(self, "&Undo")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.ladder.canvas.undo.createRedoAction(self, "&Redo")
        redo.setShortcut(QKeySequence.Redo)
        e.addAction(undo)
        e.addAction(redo)
        e.addSeparator()
        c = self.ladder.canvas
        act(e, "Cu&t", lambda: c.copy_selection(cut=True))
        act(e, "&Copy", c.copy_selection)
        act(e, "&Paste", c.paste)
        act(e, "&Delete", c.delete_selection)
        e.addSeparator()
        act(e, "&Insert rung", c.new_rung)
        act(e, "Edit &operands…", c.open_operand_editor)
        act(e, "Edit rung co&mment…", c.edit_comment)
        act(e, "Edit s&ymbol…", c.edit_symbol)
        s = mb.addMenu("&Simulations")
        group = QActionGroup(self)
        self.sim_actions = {}
        for key, label in (("io", "&I/O panel"), ("silo", "&Silo"), ("traffic", "&Traffic lights")):
            a = act(s, label, lambda _=False, k=key: self.select_sim(k))
            a.setCheckable(True)
            a.setChecked(key == self.sim_kind)
            group.addAction(a)
            self.sim_actions[key] = a
        s.addSeparator()
        act(s, "&Reset simulation", lambda: self._rebuild_sim())
        act(s, "Reset &timers and counters", self.reset_timers_counters)
        act(s, "Clear &data table", self.clear_data)
        p = mb.addMenu("&PLC")
        act(p, "&Download", self.download, "Ctrl+D")
        act(p, "&Run", lambda: self.panel.mode.set_mode("RUN"), "Ctrl+R")
        act(p, "&Program mode", lambda: self.panel.mode.set_mode("PGM"), "Ctrl+P")
        act(p, "S&tep mode", lambda: self.panel.mode.set_mode("STEP"))
        act(p, "Single &scan", self.step, "F10")
        act(p, "&Clear fault", self.clear_fault)
        v = mb.addMenu("&View")
        dock = self.table_dock.toggleViewAction()
        dock.setShortcut(QKeySequence("Ctrl+T"))
        v.addAction(dock)
        labs_act = self.labs_dock.toggleViewAction()
        labs_act.setShortcut(QKeySequence("Ctrl+E"))
        v.addAction(labs_act)
        v.addSeparator()
        act(v, "&Light theme", lambda: self.set_theme("light"))
        act(v, "&Dark theme", lambda: self.set_theme("dark"))

    # -- files --------------------------------------------------------------
    def maybe_save(self) -> bool:
        """True when it is fine to discard the current program."""
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save the changes to this program first?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            self.save()
            return not self.dirty
        return r == QMessageBox.Discard

    def closeEvent(self, e):
        if self.maybe_save():
            e.accept()
        else:
            e.ignore()

    def new(self, profile: str | None = None) -> None:
        """New program for `profile`; by default the same controller as the current program."""
        if not self.maybe_save():
            return
        self.program = Program.new(profile or self.program.profile)
        self.path = None
        self._program_changed()
        self._rebuild_sim()

    def open(self, path: str | None = None) -> None:
        if not self.maybe_save():
            return
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Open program", "", formats.OPEN_FILTER)
            if not path:
                return
        try:
            self.program = formats.load(path)
        except (OSError, *formats.FormatError) as e:
            QMessageBox.warning(self, "Could not open the program", str(e))
            return
        self.path = Path(path)
        self._program_changed()
        self._rebuild_sim()

    def start_lab(self, lab) -> None:
        """New program for an exercise: its symbols, its simulation."""
        if not self.maybe_save():
            return
        self.program = lab.starter()
        self.path = None
        self._program_changed()
        self.select_sim(lab.simulation)
        self.statusBar().showMessage(f"Exercise {lab.id}: {lab.title}. Insert a rung to start.", 6000)

    def check_lab(self, lab) -> None:
        """Grade the program in the editor; the PLC and the simulation on screen are untouched."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = grader.grade(lab, self.program)
        finally:
            QApplication.restoreOverrideCursor()
        self.labs_view.show_report(report)

    def select_sim(self, kind: str) -> None:
        self.sim_kind = kind
        self.sim_actions[kind].setChecked(True)
        self._rebuild_sim()

    def _rebuild_sim(self) -> None:
        """Fresh simulation of the selected kind. The I/O panel is wired from the program's
        symbols (NC stops, pushbuttons)."""
        name = profiles.get(self.program.profile).io_name
        if self.sim_kind == "silo":
            self.sim = SiloModel()
            self.sim_view = SiloView(self.sim, name)
        elif self.sim_kind == "traffic":
            self.sim = TrafficModel()
            self.sim_view = TrafficView(self.sim, name)
        else:
            self.sim = IoPanelModel()
            self.sim.configure_from_symbols(self.program.symbols, name)
            self.sim_view = IoPanelView(self.sim, self.program.symbols, name)
        if hasattr(self.sim_view, "reset_requested"):
            self.sim_view.reset_requested.connect(lambda: self._rebuild_sim())
        self.plc.device = self.sim
        if self.plc.mode in (Processor.PGM, Processor.FAULT):
            self.plc.outputs_off()
        self.sim_scroll.setWidget(self.sim_view)   # the scroll area deletes the old view

    def save(self) -> None:
        if self.path is None or self.path.resolve().is_relative_to(labs.DATA):
            return self.save_as()       # examples and exercise solutions are never overwritten
        try:
            replaced = formats.save(self.program, self.path)
        except (OSError, *formats.FormatError) as e:
            QMessageBox.warning(self, "Could not save", str(e))
            return
        if replaced:
            QMessageBox.warning(self, "Some characters were replaced",
                                ".rsl files only hold Western European characters. These were saved as '?': "
                                + " ".join(replaced))
        self.dirty = False
        self._title()
        self.statusBar().showMessage(f"Saved {self.path.name}", 3000)

    def save_as(self) -> None:
        path, chosen = QFileDialog.getSaveFileName(self, "Save program", "", formats.FILTER)
        if path:
            if Path(path).suffix.lower() not in (".plcy", ".rsl"):
                path += ".rsl" if "rsl" in chosen and "plcy" not in chosen else ".plcy"
            self.path = Path(path)
            self.save()

    def _program_changed(self) -> None:
        self.in_sync = False
        self.dirty = False
        self.panel.mode.set_mode("PGM")
        self._show_program()

    def _show_program(self) -> None:
        prof = profiles.get(self.program.profile)
        self.bar.set_specs(prof.specs)
        self.ladder.canvas.set_program(self.program)
        self._show_tabs()
        tagged = bool(prof.tag_types)
        self.data_stack.setCurrentWidget(self.tags_view if tagged else self.table_view)
        self.table_dock.setWindowTitle("Tags" if tagged else "Data table")
        self.tags_view.set_program(self.program if tagged else None)
        if isinstance(self.sim_view, IoPanelView):
            self.sim_view.symbols = self.program.symbols
        self.table_view.symbols = self.program.symbols
        self._title()
        self._update_status()

    def _show_tabs(self) -> None:
        """One tab per program file: LAD 2 and SBR 3-9 on SLC 500, the main routine on Logix."""
        if self.program.profile == "slc500":
            files = list(range(2, 10))
            label = {n: "LAD 2" if n == 2 else f"SBR {n}" for n in files}
        else:
            files = sorted(self.program.files)
            label = {n: self.program.files[n].title or f"Routine {n}" for n in files}
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for n in files:
            self.tabs.addTab(label[n])
        self.tab_files = files
        self.tabs.setCurrentIndex(0)
        self.tabs.blockSignals(False)
        self.ladder.canvas.set_file(files[0])

    def _title(self) -> None:
        name = self.path.name if self.path else "Untitled"
        self.setWindowTitle(f"{'• ' if self.dirty else ''}{name} — PLCYard")

    def _edited(self) -> None:
        self.dirty = True
        self.in_sync = False
        if isinstance(self.sim_view, IoPanelView):
            self.sim_view.symbols = self.program.symbols
        self._title()
        self._update_status()

    def show_address(self, address: str) -> None:
        self.table_dock.show()
        if self.data_stack.currentWidget() is self.table_view:
            self.table_view.show_address(address)

    # -- PLC ----------------------------------------------------------------
    def download(self) -> None:
        problems = self.plc.download(self.program)
        if problems:
            text = "\n".join(str(p) for p in problems[:12])
            more = f"\n…and {len(problems) - 12} more" if len(problems) > 12 else ""
            QMessageBox.warning(self, "The program was not downloaded", text + more)
            return
        self.downloaded = True
        self.in_sync = True
        self.panel.mode.set_mode("PGM")
        self.statusBar().showMessage("Program downloaded. Switch to RUN to start scanning.", 4000)
        self._update_status()

    def set_mode(self, mode: str) -> None:
        if self.plc.mode == Processor.FAULT:
            # The selector shows PGM while faulted; only "Clear fault" leaves FAULT.
            if mode != "PGM":
                self.statusBar().showMessage("Clear the fault first.", 4000)
                self.panel.mode.set_mode("PGM")
            return
        try:
            self.plc.set_mode(mode)
        except RuntimeError as e:
            self.statusBar().showMessage(f"Cannot switch to {mode}: {e}.", 4000)
            self.panel.mode.set_mode(self.plc.mode if self.plc.mode != "FAULT" else "PGM")
            return
        self.panel.step.setEnabled(mode == "STEP")
        self._update_status()

    def step(self) -> None:
        if self.plc.mode == Processor.STEP:
            self.plc.step()

    def clear_fault(self) -> None:
        self._fault_shown = None
        self.statusBar().clearMessage()
        self.plc.clear_fault()
        self.panel.mode.set_mode("PGM")

    def reset_timers_counters(self) -> None:
        self.plc.reset_timers_counters()

    def clear_data(self) -> None:
        self.plc.dt.clear(keep_io=True)

    def set_theme(self, name: str) -> None:
        theme.apply(QApplication.instance(), name)
        self.update()
        for w in self.findChildren(QWidget):
            w.update()

    def _tick(self) -> None:
        self.plc.tick(TICK_MS * self.panel.speed.value() / 10)
        if self.plc.mode == Processor.FAULT:
            self.panel.mode.set_mode("PGM")

    def _update_status(self) -> None:
        mode = self.plc.mode
        self.panel.clear_fault.setVisible(mode == Processor.FAULT)
        if mode == Processor.FAULT:
            self.panel.set_status(f"FAULT {self.plc.fault_code:04X}h", "danger")
            if self._fault_shown != self.plc.fault:
                self._fault_shown = self.plc.fault
                self.statusBar().showMessage(f"Major fault {self.plc.fault_code:04X}h: {self.plc.fault}")
        elif not self.downloaded:
            self.panel.set_status("Not downloaded", "warning")
        elif not self.in_sync:
            self.panel.set_status(f"PLC: {mode} · edited, download to apply", "warning")
        elif mode in (Processor.RUN, Processor.STEP):
            self.panel.set_status(f"PLC: {mode}", "success")
        else:
            self.panel.set_status("PLC: PGM", "")

    def _refresh(self) -> None:
        live = self.plc.mode in (Processor.RUN, Processor.STEP)
        self.sim_view.refresh()
        same = self.in_sync and live
        same_controller = self.plc.profile.name == self.program.profile
        if self.data_stack.currentWidget() is self.table_view:
            if same_controller and self.table_view.model.dt is not self.plc.dt:
                self.table_view.model.dt = self.plc.dt      # a download switched controllers
            self.table_view.refresh()
        elif self.table_dock.isVisible():
            downloaded = same_controller and self.downloaded and self.plc.program is not None
            self.tags_view.set_memory(self.plc.dt if downloaded else None)
        self.ladder.canvas.set_live(self.plc.dt, live and same_controller, self.plc.trace if same else None)
        self.panel.scans.setText(f"{self.plc.scan_count} scans")
        self.panel.io_words.setText("  ".join(f"{n} {v & 0xFFFF:04X}h" for n, v in self.plc.profile.io_image(self.plc.dt)))
        self._update_status()
