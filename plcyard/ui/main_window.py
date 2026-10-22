"""Main window: menus, PLC strip, project tree, simulation | editor split with one tab per open
routine, status bar, laid out as PLC software usually is."""

from __future__ import annotations

from pathlib import Path

import copy
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QUndoGroup
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QDockWidget, QFileDialog,
                               QFormLayout, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QPushButton, QRadioButton, QScrollArea, QSlider, QSplitter, QTabWidget,
                               QVBoxLayout, QWidget)

from .. import grader, labs
from ..core import profiles
from ..core.processor import Processor
from ..core.profiles.base import ScopedMemory, scoped
from ..core.program import Program, ProgramFile
from .. import formats
from ..sims.io_panel import IoPanelModel
from . import theme
from ..sims.silo import SiloModel
from ..sims.tank import TankModel
from ..sims.traffic import TrafficModel
from .io_panel_view import IoPanelView
from .sim_views import SiloView, TrafficView
from .tank_view import TankView
from .block_editor import DataTypeDoc, RoutineDoc
from .project_tree import ProjectTree, routine_label
from .tags_view import TagsView
from .instruction_bar import InstructionBar
from .labs_view import LabsView
from . import notation
from .online_bar import PlcPanel

TICK_MS = 10
FRAME_MS = 33


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
        self.online = False          # the editor watches the PLC (Go Online / Download)
        self.sim_kind = "io"

        self.panel = PlcPanel()
        self.sim_view = IoPanelView(self.sim)
        self.sim_scroll = sim_scroll = QScrollArea()
        sim_scroll.setWidget(self.sim_view)
        sim_scroll.setWidgetResizable(True)
        sim_scroll.setMinimumWidth(theme.layout("sim-pane-min-w"))
        self.undo_group = QUndoGroup(self)
        self.docs = QTabWidget()              # one tab per open routine or data type
        self.docs.setTabsClosable(True)
        self.docs.setMovable(True)
        self.docs.setDocumentMode(True)
        self.docs.tabCloseRequested.connect(self.close_doc)
        self.docs.currentChanged.connect(self._doc_changed)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.bar = InstructionBar()
        self.bar.picked.connect(self._insert)
        rl.addWidget(self.bar)
        rl.addWidget(self.docs, 1)
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

        self.tree = ProjectTree()
        self.tree.open_item.connect(self._open_item)
        self.tree.action.connect(self._tree_action)
        self.tree_dock = QDockWidget("Project", self)
        self.tree_dock.setObjectName("project")
        self.tree_dock.setWidget(self.tree)
        self.tree_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.tree_dock)

        self.tags_view = TagsView()
        self.tags_view.edited.connect(self._edited)
        self.tags_view.force_requested.connect(self.force)
        self.tags_view.pid_setup.connect(self.pid_setup)
        self.table_dock = QDockWidget("Data table", self)
        self.table_dock.setObjectName("datatable")
        self.table_dock.setWidget(self.tags_view)
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
        self.panel.mode_requested.connect(self.panel.mode.set_mode)
        self.panel.go_online.connect(self.go_online)
        self.panel.go_offline.connect(self.go_offline)
        self.panel.upload.connect(self.upload)
        self.panel.remove_forces.connect(self.remove_forces)
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
        act(f, "New in &structured text", lambda: self.new(language="ST"))
        act(f, "&Open…", lambda: self.open(), QKeySequence.Open)
        ex = f.addMenu("Open &example")
        for path in sorted([*labs.SAMPLES.glob("*.rsl"), *labs.SAMPLES.glob("*.plcy")]):
            act(ex, path.stem.replace("-", " ").capitalize(), lambda _=False, p=path: self.open(str(p)))
        act(f, "&Save", self.save, QKeySequence.Save)
        act(f, "Save &as…", self.save_as, QKeySequence.SaveAs)
        f.addSeparator()
        act(f, "&Quit", self.close, QKeySequence.Quit)
        e = mb.addMenu("&Edit")
        undo = self.undo_group.createUndoAction(self, "&Undo")
        undo.setShortcut(QKeySequence.Undo)
        redo = self.undo_group.createRedoAction(self, "&Redo")
        redo.setShortcut(QKeySequence.Redo)
        e.addAction(undo)
        e.addAction(redo)
        e.addSeparator()

        def on_canvas(method):
            return lambda: self.canvas is not None and getattr(self.canvas, method)()
        act(e, "Cu&t", lambda: self.canvas is not None and self.canvas.copy_selection(cut=True))
        act(e, "&Copy", on_canvas("copy_selection"))
        act(e, "&Paste", on_canvas("paste"))
        act(e, "&Delete", on_canvas("delete_selection"))
        e.addSeparator()
        act(e, "&Insert rung", on_canvas("new_rung"))
        act(e, "Edit &operands…", on_canvas("open_operand_editor"))
        act(e, "Edit rung co&mment…", on_canvas("edit_comment"))
        act(e, "Edit s&ymbol…", on_canvas("edit_symbol"))
        pr = mb.addMenu("P&roject")
        self.add_routine_act = act(pr, "Add &routine or block…", lambda: self._tree_action("add_routine", None))
        self.add_type_act = act(pr, "New &data type…", lambda: self._tree_action("add_type", None))
        pr.addSeparator()
        act(pr, "Remove all &forces", self.remove_forces)
        s = mb.addMenu("&Simulations")
        group = QActionGroup(self)
        self.sim_actions = {}
        for key, label in (("io", "&I/O panel"), ("silo", "&Silo"), ("traffic", "&Traffic lights"),
                           ("tank", "Tank level (&analog)")):
            a = act(s, label, lambda _=False, k=key: self.select_sim(k))
            a.setCheckable(True)
            a.setChecked(key == self.sim_kind)
            group.addAction(a)
            self.sim_actions[key] = a
        s.addSeparator()
        act(s, "&Reset simulation", lambda: self._rebuild_sim())
        act(s, "Reset &timers and counters", self.reset_timers_counters)
        act(s, "Clear &data (start values)", self.clear_data)
        p = mb.addMenu("&Communications")
        act(p, "Go &Online", self.go_online, "Ctrl+K")
        act(p, "Go O&ffline", self.go_offline)
        act(p, "&Upload…", self.upload)
        act(p, "&Download", self.download, "Ctrl+D")
        p.addSeparator()
        act(p, "&Run", lambda: self.panel.mode.set_mode("RUN"), "Ctrl+R")
        act(p, "&Program mode", lambda: self.panel.mode.set_mode("PGM"), "Ctrl+P")
        act(p, "S&tep mode", lambda: self.panel.mode.set_mode("STEP"))
        act(p, "Single &scan", self.step, "F10")
        act(p, "&Clear fault", self.clear_fault)
        v = mb.addMenu("&View")
        tree = self.tree_dock.toggleViewAction()
        tree.setShortcut(QKeySequence("Ctrl+Shift+P"))
        v.addAction(tree)
        dock = self.table_dock.toggleViewAction()
        dock.setShortcut(QKeySequence("Ctrl+T"))
        v.addAction(dock)
        labs_act = self.labs_dock.toggleViewAction()
        labs_act.setShortcut(QKeySequence("Ctrl+E"))
        v.addAction(labs_act)
        v.addSeparator()
        act(v, "&Light theme", lambda: self.set_theme("light"))
        act(v, "&Dark theme", lambda: self.set_theme("dark"))
        t = mb.addMenu("&Tools")
        act(t, "&Options…", self.options)

    def options(self) -> None:
        dlg = OptionsDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.notation() != notation.current():
            self.set_notation(dlg.notation())

    def set_notation(self, n: str) -> None:
        """Show the program in the other notation; the program itself does not change."""
        notation.set_current(n)
        self.bar.set_specs(self.plc.profile.specs, force=True)
        for i in range(self.docs.count()):
            w = self.docs.widget(i)
            if isinstance(w, RoutineDoc) and w.canvas is not None:
                w.canvas._relayout()
        self.tags_view.set_program(self.program)
        self._rebuild_sim()
        self.labs_view.refresh_text() if hasattr(self.labs_view, "refresh_text") else None
        self.update()

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

    def new(self, profile: str | None = None, language: str = "LD") -> None:
        """New program with an empty main routine in `language` (LD or ST)."""
        if not self.maybe_save():
            return
        self.program = Program.new(language=language)
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
        name = notation.io_name
        if self.sim_kind == "tank":
            self.sim = TankModel()
            self.sim_view = TankView(self.sim, name, notation.analog_name)
        elif self.sim_kind == "silo":
            self.sim = SiloModel()
            self.sim_view = SiloView(self.sim, name)
        elif self.sim_kind == "traffic":
            self.sim = TrafficModel()
            self.sim_view = TrafficView(self.sim, name)
        else:
            self.sim = IoPanelModel()
            self.sim.configure_from_symbols(self.program.symbols)
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
        self.online = False
        self.dirty = False
        self.panel.mode.set_mode("PGM")
        self._show_program()

    def _show_program(self) -> None:
        prof = profiles.get(self.program.profile)
        self.bar.set_specs(prof.specs)
        while self.docs.count():
            self._remove_doc(0)
        self.tree.set_program(self.program)
        self.tree_dock.setWindowTitle("Project")
        self.add_routine_act.setEnabled(bool(prof.routine_kinds))
        self.add_type_act.setEnabled(bool(prof.tag_types))
        self.open_routine(2)
        self.table_dock.setWindowTitle("Tags")
        self.tags_view.set_program(self.program)
        if isinstance(self.sim_view, IoPanelView):
            self.sim_view.symbols = self.program.symbols
        self._title()
        self._update_status()

    # -- documents ----------------------------------------------------------
    @property
    def doc(self):
        return self.docs.currentWidget()

    @property
    def canvas(self):
        d = self.doc
        return d.canvas if isinstance(d, RoutineDoc) else None

    @property
    def ladder(self):
        d = self.doc
        return d.ladder if isinstance(d, RoutineDoc) else None

    @property
    def st_editor(self):
        d = self.doc
        return d.st if isinstance(d, RoutineDoc) else None

    def _doc_key(self, w):
        if isinstance(w, RoutineDoc):
            return ("routine", w.number)
        if isinstance(w, DataTypeDoc):
            return ("type", w.name)
        return None

    def _find_doc(self, key) -> int:
        return next((i for i in range(self.docs.count()) if self._doc_key(self.docs.widget(i)) == key), -1)

    def _doc_title(self, w) -> str:
        if isinstance(w, RoutineDoc):
            return routine_label(w.file) if w.file else "?"
        return w.name

    def open_routine(self, number: int) -> None:
        """Bring a routine to the front, opening it in a new tab the first time."""
        i = self._find_doc(("routine", number))
        if i < 0:
            if number not in self.program.files:
                self.program.files[number] = ProgramFile(number, "SBR", "")
            doc = RoutineDoc(self.program, number)
            doc.changed.connect(self._edited)
            if doc.canvas is not None:
                self.undo_group.addStack(doc.canvas.undo)
            i = self.docs.addTab(doc, self._doc_title(doc))
        self.docs.setCurrentIndex(i)

    def open_routine_named(self, name: str) -> None:
        f = self.program.routine(name)
        if f is None:                                        # an FB instance: open its block
            t = str(self.program.tags.get(name.strip('"#'), {}).get("type", ""))
            f = self.program.routine(t)
        if f is not None:
            self.open_routine(f.number)

    def open_type(self, name: str) -> None:
        i = self._find_doc(("type", name))
        if i < 0:
            doc = DataTypeDoc(self.program, name)
            doc.changed.connect(self._edited)
            i = self.docs.addTab(doc, name)
        self.docs.setCurrentIndex(i)

    def close_doc(self, i: int) -> None:
        if self.docs.count() > 1:
            self._remove_doc(i)

    def _remove_doc(self, i: int) -> None:
        w = self.docs.widget(i)
        if isinstance(w, RoutineDoc) and w.canvas is not None:
            self.undo_group.removeStack(w.canvas.undo)
        self.docs.removeTab(i)
        w.deleteLater()

    def _doc_changed(self, _i: int) -> None:
        canvas = self.canvas
        self.bar.setVisible(canvas is not None)
        self.undo_group.setActiveStack(canvas.undo if canvas is not None else None)

    def _insert(self, mnemonic: str) -> None:
        if self.canvas is not None:
            self.canvas.insert_mnemonic(mnemonic)

    def _retitle_docs(self) -> None:
        for i in reversed(range(self.docs.count())):
            w = self.docs.widget(i)
            if isinstance(w, RoutineDoc) and w.number not in self.program.files or \
                    isinstance(w, DataTypeDoc) and w.name not in self.program.types:
                self._remove_doc(i)
            else:
                self.docs.setTabText(i, self._doc_title(w))

    def _open_item(self, kind: str, key) -> None:
        if kind == "routine":
            self.open_routine(key)
        elif kind == "type":
            self.open_type(key)
        elif kind == "tags":
            self.table_dock.show()
            self.table_dock.raise_()

    # -- routines, blocks and data types --------------------------------------
    def _tree_action(self, action: str, key) -> None:
        prof = profiles.get(self.program.profile)
        if action == "add_routine" and prof.routine_kinds:
            dlg = NewRoutineDialog(self, prof)
            if dlg.exec() != QDialog.Accepted:
                return
            name, kind, language = dlg.values()
            problem = self._name_problem(name)
            if problem:
                return QMessageBox.warning(self, "Cannot add", problem)
            number = max(self.program.files) + 1
            self.program.files[number] = ProgramFile(number, kind, name, language=language)
            self._structure_changed()
            self.open_routine(number)
        elif action == "rename_routine":
            f = self.program.files[key]
            name, ok = QInputDialog.getText(self, "Rename", "New name:", text=f.title or "")
            if ok and name.strip() and name.strip() != f.title:
                problem = self._name_problem(name.strip())
                if problem:
                    return QMessageBox.warning(self, "Cannot rename", problem)
                rename_routine(self.program, f.title, name.strip())
                self._structure_changed()
        elif action == "delete_routine":
            f = self.program.files[key]
            if QMessageBox.question(self, "Delete", f"Delete {f.title or key}? Calls to it stop the download "
                                    "until they are removed.") == QMessageBox.Yes:
                del self.program.files[key]
                self._structure_changed()
        elif action == "add_type":
            name, ok = QInputDialog.getText(self, "New data type", "Name:")
            if ok and name.strip():
                problem = self._name_problem(name.strip())
                if problem:
                    return QMessageBox.warning(self, "Cannot add", problem)
                self.program.types[name.strip()] = {}
                self._structure_changed()
                self.open_type(name.strip())
        elif action == "rename_type":
            name, ok = QInputDialog.getText(self, "Rename", "New name:", text=key)
            if ok and name.strip() and name.strip() != key:
                problem = self._name_problem(name.strip())
                if problem:
                    return QMessageBox.warning(self, "Cannot rename", problem)
                rename_type(self.program, key, name.strip())
                self._structure_changed()
        elif action == "delete_type":
            if QMessageBox.question(self, "Delete", f"Delete data type {key}?") == QMessageBox.Yes:
                del self.program.types[key]
                self._structure_changed()

    def _name_problem(self, name: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            return f"{name!r} is not a valid name (letters, digits and _; no leading digit)"
        taken = {(f.title or "").lower() for f in self.program.files.values()} | {t.lower() for t in self.program.types}
        if name.lower() in taken:
            return f"{name} is already used by a routine, block or data type"
        return ""

    def _structure_changed(self) -> None:
        self.tree.set_program(self.program)
        self._retitle_docs()
        self.tags_view.set_program(self.program)
        self._edited()

    # -- PID setup ----------------------------------------------------------
    def pid_setup(self, name: str) -> None:
        from .pid_setup import PidSetup
        if not any(n.lower() == name.lower() for n in self.program.tags):
            return self.statusBar().showMessage(f"{name} is not a PID tag of this program", 4000)
        memory = self.plc.dt if self.online and self.in_sync else None
        dlg = PidSetup(self, self.program, name, memory)
        dlg.exec()
        self.tags_view.set_program(self.program)
        self.dirty = True
        self._title()

    # -- forcing ------------------------------------------------------------
    def force(self, ref: str, on) -> None:
        problem = self.plc.force(ref, on)
        if problem:
            self.statusBar().showMessage(f"Cannot force {ref}: {problem}", 5000)
        self.tags_view.set_forces(self.plc.forces)

    def remove_forces(self) -> None:
        self.plc.forces.clear()
        self.tags_view.set_forces(self.plc.forces)

    def _title(self) -> None:
        name = self.path.name if self.path else "Untitled"
        self.setWindowTitle(f"{'• ' if self.dirty else ''}{name} — PLCYard")

    def _edited(self) -> None:
        self.dirty = True
        self.in_sync = False
        if self.sender() is self.tags_view and self.st_editor is not None:
            self.st_editor.check()                    # a new or renamed tag may fix (or break) the code
        if isinstance(self.sender(), DataTypeDoc):
            self.tags_view.set_program(self.program)
        if self.sender() is self.tags_view:
            self.tree.set_program(self.program)          # data blocks are listed with the blocks
        if isinstance(self.sim_view, IoPanelView):
            self.sim_view.symbols = self.program.symbols
        self._title()
        self._update_status()

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
        self.online = True
        self.panel.mode.set_mode("PGM")
        self.statusBar().showMessage("Program downloaded. Switch to RUN to start scanning.", 4000)
        self._update_status()

    # -- online -------------------------------------------------------------
    def go_online(self) -> None:
        """Watch the controller. If it holds another program, choose to upload or download."""
        if self.plc.program is None:
            if QMessageBox.question(self, "Go Online", "The controller has no program. Download this one?") \
                    == QMessageBox.Yes:
                self.download()
            return
        same = self.in_sync or formats.plcy.dumps(self.plc.program) == formats.plcy.dumps(self.program)
        if not same:
            box = QMessageBox(QMessageBox.Question, "Go Online",
                              "The program in the controller is not the one open here.", parent=self)
            up = box.addButton("Upload", QMessageBox.AcceptRole)
            down = box.addButton("Download", QMessageBox.AcceptRole)
            box.addButton(QMessageBox.Cancel)
            box.exec()
            if box.clickedButton() is up:
                return self.upload(ask=False)
            if box.clickedButton() is down:
                return self.download()
            return
        self.in_sync = self.downloaded = self.online = True
        self.statusBar().showMessage("Online.", 3000)
        self._update_status()

    def go_offline(self) -> None:
        """Stop watching; the controller keeps running what it has."""
        self.online = False
        self._update_status()

    def upload(self, ask: bool = True) -> None:
        """Copy the controller's program into the editor."""
        if self.plc.program is None:
            QMessageBox.warning(self, "Upload", "The controller has no program to upload.")
            return
        if ask and not self.maybe_save():
            return
        self.program = copy.deepcopy(self.plc.program)
        self.path = None
        self.dirty = False
        self._show_program()
        self.in_sync = self.downloaded = self.online = True
        self.panel.mode.set_mode(self.plc.mode if self.plc.mode != Processor.FAULT else "PGM")
        self.statusBar().showMessage("Uploaded the controller's program.", 4000)
        self._update_status()

    def set_mode(self, mode: str) -> None:
        if not self.online and self.plc.program is not None and mode != self.plc.mode:
            self.statusBar().showMessage("Go online first (Communications → Go Online).", 4000)
            self.panel.mode.set_mode(self.plc.mode if self.plc.mode != Processor.FAULT else "PGM")
            return
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
        """Every tag back to its start value (the program in the PLC stays)."""
        if self.plc.program is not None:
            self.plc.profile.load(self.plc.program, self.plc.dt)
            self.plc.reset_timers_counters()

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
        self.panel.set_online(self.online, mode, self.online and not self.in_sync)
        self.panel.set_forces(bool(self.plc.forces))
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

    def _doc_memory(self, doc):
        """The PLC memory as code in this routine sees it: inside a block, through its instance
        (an FB shows its first instance)."""
        f = doc.file
        if f is None or f.kind not in ("FC", "FB") or not self.in_sync:
            return self.plc.dt
        insts = self.plc._instances(f) if self.plc.program else []
        if not insts:
            return self.plc.dt
        names = {n.lower() for sec in f.interface.values() for n in sec}
        return ScopedMemory(self.plc.dt, lambda text: scoped(text, insts[0], names))

    def _refresh(self) -> None:
        live = self.online and self.plc.mode in (Processor.RUN, Processor.STEP)
        self.sim_view.refresh()
        same = self.in_sync and live
        same_controller = True
        if self.table_dock.isVisible():
            downloaded = same_controller and self.downloaded and self.online and self.plc.program is not None
            self.tags_view.set_memory(self.plc.dt if downloaded else None)
        doc = self.doc
        if isinstance(doc, RoutineDoc):
            if doc.canvas is not None:
                doc.canvas.set_live(self._doc_memory(doc), live and same_controller, self.plc.trace if same else None)
            else:
                doc.st.set_live(self._doc_memory(doc) if same_controller and self.downloaded and self.online else None)
        self.panel.forces.setVisible(bool(self.plc.forces))
        self.panel.set_leds(running=self.plc.mode in (Processor.RUN, Processor.STEP), forced=bool(self.plc.forces),
                            fault=self.plc.mode == Processor.FAULT, io=self.downloaded, mode=self.plc.mode)
        self.panel.scans.setText(f"{self.plc.scan_count} scans")
        self.panel.io_words.setText("  ".join(f"{notation.show(n)} {v & 0xFFFF:04X}h"
                                              for n, v in self.plc.profile.io_image(self.plc.dt)))
        self._update_status()


class NewRoutineDialog(QDialog):
    """Name, kind and language of a new routine or block."""

    def __init__(self, parent, prof):
        super().__init__(parent)
        self.setWindowTitle("New routine or block")
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.name.setPlaceholderText("Filling")
        form.addRow("Name", self.name)
        self.kind = QComboBox()
        for k in prof.routine_kinds:
            self.kind.addItem({"SBR": "Routine (called with JSR, no parameters)", "FC": "Function (FC, parameters)",
                               "FB": "Function block (FB, parameters and its own data)"}[k], k)
        form.addRow("Type", self.kind)
        self.language = QComboBox()
        self.language.addItem("Ladder diagram", "LD")
        self.language.addItem("Structured text", "ST")
        form.addRow("Language", self.language)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[str, str, str]:
        return self.name.text().strip(), self.kind.currentData(), self.language.currentData()


def _rename_word(text: str, old: str, new: str) -> str:
    return re.sub(rf'(?<![\w.])("?){re.escape(old)}("?)(?!\w)', lambda m: f"{m[1]}{new}{m[2]}", text, flags=re.I)


def rename_routine(program: Program, old: str, new: str) -> None:
    """Rename a routine or block and every call to it (JSR, CALL, ST calls, FB instance types)."""
    from ..core.program import walk
    f = program.routine(old)
    f.title = new
    for g in program.files.values():
        for rung in g.rungs:
            for ins in walk(rung.body):
                if ins.mnemonic in ("JSR", "CALL") and ins.operands and ins.operands[0].strip('"').lower() == old.lower():
                    ins.operands[0] = new
        if g.language == "ST":
            g.source = _rename_word(g.source, old, new)
        for sec in g.interface.values():
            for n, t in sec.items():
                if t.lower() == old.lower():
                    sec[n] = new
    for d in program.tags.values():
        if str(d.get("type", "")).lower() == old.lower():
            d["type"] = new


def rename_type(program: Program, old: str, new: str) -> None:
    """Rename a data type where tags, other types and block interfaces use it."""
    program.types = {(new if k == old else k): v for k, v in program.types.items()}
    pattern = re.compile(rf"\b{re.escape(old)}\b", re.I)
    for d in program.tags.values():
        d["type"] = pattern.sub(new, str(d.get("type", "")))
    for ms in program.types.values():
        for n, t in ms.items():
            ms[n] = pattern.sub(new, t)
    for g in program.files.values():
        for sec in g.interface.values():
            for n, t in sec.items():
                sec[n] = pattern.sub(new, t)


class OptionsDialog(QDialog):
    """Tools → Options: how instructions and addresses are written."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Options")
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Notation for instructions, addresses and timer members:"))
        self.buttons = {}
        for key, text in notation.NAMES.items():
            b = QRadioButton(text)
            b.setChecked(key == notation.current())
            self.buttons[key] = b
            lay.addWidget(b)
        note = QLabel("Programs are the same in both; switch whenever you like.")
        note.setProperty("muted", "true")
        lay.addWidget(note)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def notation(self) -> str:
        return next(k for k, b in self.buttons.items() if b.isChecked())
