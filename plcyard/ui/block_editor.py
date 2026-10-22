"""Documents of the editor area: one routine or block in its language, the interface of a function
or function block (shown above its code) and a user data type's members."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMenu, QPushButton, QSplitter, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from ..core import profiles
from . import theme
from .ladder_view import LadderView
from .st_editor import StEditor


class MembersTree(QWidget):
    """Name / data type rows, grouped by section (a block interface) or flat (a data type).
    Every change is checked against the whole program before it is kept."""

    changed = Signal()

    def __init__(self, sections: tuple[str, ...] | None):
        super().__init__()
        self.sections = sections
        self.program = None
        self._filling = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Name", "Data type"])
        self.tree.setFont(theme.font("mono", "sm"))
        self.tree.setRootIsDecorated(bool(sections))
        self.tree.itemChanged.connect(self._edited)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.del_btn = QPushButton("Delete")
        self.add_btn.clicked.connect(lambda: self.add_member())
        self.del_btn.clicked.connect(self.delete_member)
        row.addWidget(self.add_btn)
        row.addWidget(self.del_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.message = QLabel()
        self.message.setProperty("status", "danger")
        self.message.setWordWrap(True)
        lay.addWidget(self.message)

    # -- what is edited: subclasses say where the members live -------------------------------
    def members(self) -> dict:
        raise NotImplementedError

    def store(self, program, members: dict) -> None:
        raise NotImplementedError

    def default_type(self) -> str:
        return "BOOL"

    # -- view --------------------------------------------------------------------------------
    def fill(self) -> None:
        self._filling = True
        self.tree.clear()
        data = self.members()
        groups = self.sections or (None,)
        for sec in groups:
            parent = self.tree.invisibleRootItem()
            if sec is not None:
                parent = QTreeWidgetItem([sec, ""])
                parent.setData(0, Qt.UserRole, sec)
                self.tree.addTopLevelItem(parent)
            for name, t in (data.get(sec, {}) if sec else data).items():
                it = QTreeWidgetItem([name, t])
                it.setFlags(it.flags() | Qt.ItemIsEditable)
                it.setData(0, Qt.UserRole, sec)
                parent.addChild(it)
        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self._filling = False

    def _collect(self) -> dict:
        def rows(parent):
            out = {}
            for k in range(parent.childCount()):
                it = parent.child(k)
                out[it.text(0).strip()] = it.text(1).strip()
            return out
        if not self.sections:
            return rows(self.tree.invisibleRootItem())
        return {self.tree.topLevelItem(k).text(0): rows(self.tree.topLevelItem(k))
                for k in range(self.tree.topLevelItemCount()) if self.tree.topLevelItem(k).childCount()}

    def _apply(self, members: dict) -> bool:
        flat = [n for sec in (members.values() if self.sections else [members]) for n in sec]
        if len({n.lower() for n in flat}) != len(flat):
            return self._reject("two members have the same name")
        candidate = copy.deepcopy(self.program)
        self.store(candidate, members)
        problem = profiles.get(self.program.profile).check_tags(candidate)
        if problem:
            return self._reject(problem)
        self.store(self.program, members)
        self.message.setText("")
        self.changed.emit()
        return True

    def _reject(self, problem: str) -> bool:
        self.message.setText(problem)
        self.fill()
        return False

    def _edited(self, item, col) -> None:
        if not self._filling:
            self._apply(self._collect())

    def add_member(self, section: str | None = None) -> None:
        members = copy.deepcopy(self.members())
        group = members
        if self.sections:
            if section is None:
                cur = self.tree.currentItem()
                section = cur.data(0, Qt.UserRole) if cur is not None else self.sections[0]
            group = members.setdefault(section, {})
        taken = {n.lower() for sec in (members.values() if self.sections else [members]) for n in sec}
        n = 1
        while f"Member{n}".lower() in taken:
            n += 1
        group[f"Member{n}"] = self.default_type()
        if self._apply(members):
            self.fill()

    def delete_member(self) -> None:
        it = self.tree.currentItem()
        if it is None or it.parent() is None and self.sections:
            return
        members = copy.deepcopy(self.members())
        group = members.get(it.data(0, Qt.UserRole), {}) if self.sections else members
        group.pop(it.text(0), None)
        if self.sections:
            members = {k: v for k, v in members.items() if v}
        if self._apply(members):
            self.fill()

    def _menu(self, pos) -> None:
        it = self.tree.itemAt(pos)
        m = QMenu(self)
        sec = it.data(0, Qt.UserRole) if it is not None else None
        m.addAction("Add" + (f" to {sec}" if sec else ""), lambda: self.add_member(sec))
        if it is not None and (it.parent() is not None or not self.sections):
            self.tree.setCurrentItem(it)
            m.addAction("Delete", self.delete_member)
        m.exec(self.tree.viewport().mapToGlobal(pos))


class InterfaceTree(MembersTree):
    """Block interface (FC/FB): Input, Output, InOut, Static (FB only), Temp."""

    def __init__(self, program, number: int):
        f = program.files[number]
        secs = tuple(s for s in profiles.get(program.profile).interface_sections if f.kind == "FB" or s != "Static")
        super().__init__(secs)
        self.program, self.number = program, number
        self.fill()

    def members(self) -> dict:
        return self.program.files[self.number].interface

    def store(self, program, members: dict) -> None:
        program.files[self.number].interface = members


class DataTypeDoc(MembersTree):
    """Members of a user-defined data type."""

    def __init__(self, program, name: str):
        super().__init__(None)
        self.program, self.name = program, name
        self.fill()

    def members(self) -> dict:
        return self.program.types.get(self.name, {})

    def store(self, program, members: dict) -> None:
        program.types[self.name] = members


class RoutineDoc(QWidget):
    """One routine in its editor (ladder or structured text), with the interface above it for an
    function or function block."""

    changed = Signal()

    def __init__(self, program, number: int):
        super().__init__()
        self.program, self.number = program, number
        f = program.files[number]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.ladder: LadderView | None = None
        self.st: StEditor | None = None
        if f.language == "ST":
            self.st = StEditor()
            self.st.set_program(program, number)
            self.st.changed.connect(self.changed)
            editor = self.st
        else:
            self.ladder = LadderView()
            self.ladder.canvas.set_program(program)
            self.ladder.canvas.set_file(number)
            self.ladder.canvas.changed.connect(self.changed)
            editor = self.ladder
        self.interface = None
        if f.kind in ("FC", "FB"):
            self.interface = InterfaceTree(program, number)
            self.interface.changed.connect(self._interface_changed)
            split = QSplitter(Qt.Vertical)
            split.addWidget(self.interface)
            split.addWidget(editor)
            split.setSizes([160, 500])
            lay.addWidget(split)
        else:
            lay.addWidget(editor)

    @property
    def canvas(self):
        return self.ladder.canvas if self.ladder else None

    @property
    def file(self):
        return self.program.files.get(self.number)

    def _interface_changed(self) -> None:
        if self.st:
            self.st.check()
        else:
            self.ladder.canvas._relayout()
        self.changed.emit()

    def set_live(self, memory, live: bool, trace) -> None:
        if self.ladder:
            self.ladder.canvas.set_live(memory, live, trace)
        else:
            self.st.set_live(memory)
