"""Project tree on the left, laid out as PLC software usually shows it: the controller with its tags,
the program with its routines and blocks, the data types. Double-click opens an item; right-click
adds, renames or deletes."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem

ROLE = Qt.UserRole          # (kind, key): ("routine", number) ("tags", None) ("type", name) ("types", None)…


def routine_label(f) -> str:
    """How the tree and the tabs name a routine or block."""
    lang = {"ST": " (ST)", "FBD": " (FBD)"}.get(f.language, "")
    if f.kind in ("FC", "FB"):
        return f"{f.title} [{f.kind}]{lang}"
    return f"{f.title}{lang}"


class ProjectTree(QTreeWidget):
    open_item = Signal(str, object)        # kind, key
    action = Signal(str, object)           # "add_routine", "rename_routine", "delete_routine", "add_type",
                                           # "rename_type", "delete_type"

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
        routines = [program.files[n] for n in sorted(program.files)]
        plc = self._node(self, "PLC", bold=True)
        self._node(plc, "Tags", "tags")
        prog = self._node(self, "Program", "routines", bold=True)
        for f in routines:
            self._node(prog, routine_label(f), "routine", f.number, bold=f.number == 2)
        fbs = {(f.title or "").lower() for f in routines if f.kind == "FB"}
        instances = [n for n, d in program.tags.items() if str(d.get("type", "")).lower() in fbs]
        if instances:
            inst = self._node(prog, "Block instances", "tags")
            for n in instances:
                self._node(inst, f"{n} [{program.tags[n]['type']}]", "tags", n)
        udt = self._node(self, "Data types", "types", bold=True)
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
        m = QMenu(self)
        if kind == "routine":
            m.addAction("Open", lambda: self.open_item.emit("routine", key))
        if kind in ("routines", "routine"):
            m.addAction("Add routine or block…", lambda: self.action.emit("add_routine", None))
        if kind == "routine" and key != 2 and key in self.program.files:
            m.addAction("Rename…", lambda: self.action.emit("rename_routine", key))
            m.addAction("Delete", lambda: self.action.emit("delete_routine", key))
        if kind in ("types", "type"):
            m.addAction("New data type…", lambda: self.action.emit("add_type", None))
        if kind == "type":
            m.addAction("Open", lambda: self.open_item.emit("type", key))
            m.addAction("Rename…", lambda: self.action.emit("rename_type", key))
            m.addAction("Delete", lambda: self.action.emit("delete_type", key))
        if kind == "tags":
            m.addAction("Open tags", lambda: self.open_item.emit("tags", key))
        if not m.isEmpty():
            m.exec(self.viewport().mapToGlobal(pos))
