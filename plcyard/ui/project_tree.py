"""Project tree on the left, laid out as the controller's own software shows it: the Controller
Organizer of Studio 5000 (Logix), the project tree of TIA Portal (S7), the project window of
RSLogix 500 (SLC 500). Double-click opens an item; right-click adds, renames or deletes."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

from ..core import profiles

ROLE = Qt.UserRole          # (kind, key): ("routine", number) ("tags", None) ("type", name) ("types", None)…


def routine_label(profile: str, f) -> str:
    """How the software names a routine or block in its tree."""
    lang = {"ST": " (ST)" if profile == "logix" else " (SCL)"}.get(f.language, "")
    if profile == "slc500":
        return ("LAD 2" if f.number == 2 else f"SBR {f.number}") + (f" - {f.title}" if f.title else "")
    if profile == "s7":
        tag = "OB1" if f.number == 2 else f"{f.kind}{f.number}"
        return f"{f.title} [{tag}]{lang}"
    return f"{f.title}{lang}"


class ProjectTree(QTreeWidget):
    open_item = Signal(str, object)        # kind, key
    action = Signal(str, object)           # "add_routine", "rename_routine", "delete_routine", "add_type",
                                           # "rename_type", "delete_type", "routine_properties"

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.program = None
        self.itemActivated.connect(self._activated)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)

    def _node(self, parent, text: str, kind: str = "", key=None, bold: bool = False) -> QTreeWidgetItem:
        it = QTreeWidgetItem([text])
        it.setData(0, ROLE, (kind, key))
        if bold:
            f = it.font(0)
            f.setBold(True)
            it.setFont(0, f)
        (parent.addChild if isinstance(parent, QTreeWidgetItem) else self.addTopLevelItem)(it)
        return it

    def set_program(self, program) -> None:
        self.program = program
        self.clear()
        if program is None:
            return
        p = program.profile
        routines = [program.files[n] for n in sorted(program.files)]
        if p == "slc500":
            proj = self._node(self, "Project", bold=True)
            files = self._node(proj, "Program Files", "routines")
            for n in range(2, 10):
                f = program.files.get(n)
                label = routine_label(p, f) if f else f"SBR {n}"
                self._node(files, label, "routine", n)
            data = self._node(proj, "Data Files", "tags")
            for name in ("O0 - OUTPUT", "I1 - INPUT", "S2 - STATUS", "B3 - BINARY", "T4 - TIMER",
                         "C5 - COUNTER", "R6 - CONTROL", "N7 - INTEGER", "F8 - FLOAT"):
                self._node(data, name, "tags", name.split()[0])
        elif p == "logix":
            ctl = self._node(self, "Controller PLCYard", bold=True)
            self._node(ctl, "Controller Tags", "tags")
            tasks = self._node(self, "Tasks", bold=True)
            task = self._node(tasks, "MainTask")
            prog = self._node(task, "MainProgram", "routines")
            for f in routines:
                self._node(prog, routine_label(p, f), "routine", f.number, bold=f.number == 2)
            dt = self._node(self, "Data Types", bold=True)
            udt = self._node(dt, "User-Defined", "types")
            for name in program.types:
                self._node(udt, name, "type", name)
        else:
            plc = self._node(self, "PLC_1 [CPU 1214C]", bold=True)
            blocks = self._node(plc, "Program blocks", "routines")
            for f in routines:
                self._node(blocks, routine_label(p, f), "routine", f.number)
            for name, d in program.tags.items():
                t = str(d.get("type", ""))
                if any(t.lower() == x.lower() for x in program.types) or any(
                        g.kind == "FB" and (g.title or "").lower() == t.lower() for g in routines):
                    self._node(blocks, f"{name} [DB]", "tags", name)
            tags = self._node(plc, "PLC tags", "tags")
            self._node(tags, "Default tag table", "tags")
            udt = self._node(plc, "PLC data types", "types")
            for name in program.types:
                self._node(udt, name, "type", name)
        self.expandAll()

    def _activated(self, item: QTreeWidgetItem, _col: int) -> None:
        kind, key = item.data(0, ROLE) or ("", None)
        if kind in ("routine", "tags", "type"):
            self.open_item.emit(kind, key)

    def _menu(self, pos) -> None:
        item = self.itemAt(pos)
        if item is None or self.program is None:
            return
        kind, key = item.data(0, ROLE) or ("", None)
        prof = profiles.get(self.program.profile)
        m = QMenu(self)
        if kind == "routine":
            m.addAction("Open", lambda: self.open_item.emit("routine", key))
        if prof.routine_kinds and kind in ("routines", "routine"):
            m.addAction("Add block…" if self.program.profile == "s7" else "Add routine…",
                        lambda: self.action.emit("add_routine", None))
        if kind == "routine" and key != 2 and key in self.program.files and prof.routine_kinds:
            m.addAction("Rename…", lambda: self.action.emit("rename_routine", key))
            m.addAction("Delete", lambda: self.action.emit("delete_routine", key))
        if prof.tag_types and kind in ("types", "type"):
            m.addAction("New data type…", lambda: self.action.emit("add_type", None))
        if kind == "type":
            m.addAction("Open", lambda: self.open_item.emit("type", key))
            m.addAction("Rename…", lambda: self.action.emit("rename_type", key))
            m.addAction("Delete", lambda: self.action.emit("delete_type", key))
        if kind == "tags":
            m.addAction("Open tags", lambda: self.open_item.emit("tags", key))
        if not m.isEmpty():
            m.exec(self.viewport().mapToGlobal(pos))
