"""Tag list: declare tags, see and change their values live, open structures and arrays to their
members, force I/O points. A tag may have an address (%M10.0, %MW20) or live in the tag memory."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QMenu, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from ..core import profiles
from . import notation, theme

REF = Qt.UserRole              # full reference of a row: "Line[2].Speed"
MAX_CHILDREN = 200             # rows shown under a big array


class TagsView(QWidget):
    edited = Signal()                      # declarations or descriptions changed (the program is dirty)
    force_requested = Signal(str, object)  # reference, True / False / None (remove)

    def __init__(self):
        super().__init__()
        self.program = None
        self.profile = None
        self.memory = None
        self.forces: dict[str, bool] = {}
        self._filling = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.table = QTreeWidget()
        self.table.setFont(theme.font("mono", "sm"))
        self.table.itemChanged.connect(self._changed)
        self.table.itemExpanded.connect(self._expand)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.add_btn = QPushButton("Add tag")
        self.del_btn = QPushButton("Delete tag")
        self.add_btn.clicked.connect(self.add_tag)
        self.del_btn.clicked.connect(self.delete_tag)
        row.addWidget(self.add_btn)
        row.addWidget(self.del_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.message = QLabel()
        self.message.setProperty("status", "danger")
        self.message.setWordWrap(True)
        lay.addWidget(self.message)

    # -- columns ---------------------------------------------------------------------
    @property
    def columns(self) -> list[str]:
        fields = [f.capitalize() for f in (self.profile.tag_fields if self.profile else ())]
        return ["Name", "Type", *fields, "Value", "Force", "Description"]

    def col(self, name: str) -> int:
        return self.columns.index(name)

    def row(self, r: int) -> QTreeWidgetItem:
        return self.table.topLevelItem(r)

    def item(self, r: int, c: int) -> QTreeWidgetItem:
        """Row r of the tag list (column c is read with .text(c)), as a table would give it."""
        return _Cell(self.row(r), c)

    def type_box(self, r: int) -> QComboBox:
        return self.table.itemWidget(self.row(r), self.col("Type"))

    def set_type(self, r: int, type_: str) -> None:
        """Choose or type a data type for row r, as picking it in the list does."""
        self.type_box(r).setCurrentText(type_)
        self._retype(self.row(r).data(0, REF), type_)

    # -- data ------------------------------------------------------------------------
    def set_program(self, program) -> None:
        self.program = program
        self.profile = profiles.get(program.profile) if program else None
        self._fill()

    def set_memory(self, memory) -> None:
        """Live values while the PLC runs this program; None shows the start values."""
        self.memory = memory
        self.refresh()

    def set_forces(self, forces: dict[str, bool]) -> None:
        self.forces = forces

    def _types(self) -> list[str]:
        blocks = [f.title for f in self.program.files.values() if f.kind == "FB"]
        return [notation.type_name(t) for t in self.profile.tag_types] + [*self.program.types, *blocks]

    def _view_memory(self):
        """Memory the rows are read from: the PLC's while live, else one built from the declarations."""
        if self.memory is not None:
            return self.memory
        try:
            mem = self.profile.build_memory(self.program)
        except self.profile.memory_errors:
            return None
        return mem

    def _fill(self) -> None:
        self._filling = True
        cols = self.columns
        self.table.clear()
        self.table.setColumnCount(len(cols))
        self.table.setHeaderLabels(cols)
        head = self.table.header()
        for c in range(len(cols) - 1):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(len(cols) - 1, QHeaderView.Stretch)
        types = self._types() if self.program else []
        for name, d in (self.program.tags.items() if self.program else []):
            it = QTreeWidgetItem([""] * len(cols))
            it.setText(0, name)
            it.setData(0, REF, name)
            it.setFlags(it.flags() | Qt.ItemIsEditable)
            self.table.addTopLevelItem(it)
            box = QComboBox()
            box.setEditable(True)
            box.addItems(types)
            box.setCurrentText(next((t for t in types if t.lower() == str(d.get("type", "")).lower()),
                                    str(d.get("type", ""))))
            box.lineEdit().editingFinished.connect(lambda n=name, b=box: self._retype(n, b.currentText()))
            box.activated.connect(lambda _i, n=name, b=box: self._retype(n, b.currentText()))
            box.setMinimumWidth(140)
            self.table.setItemWidget(it, self.col("Type"), box)
            for f in self.profile.tag_fields:
                it.setText(self.col(f.capitalize()), str(d.get(f, "")))
            it.setText(self.col("Description"), self.program.symbols.get(name, ""))
            self._add_placeholder(it, name)
        self._filling = False
        self.refresh()

    def _add_placeholder(self, it: QTreeWidgetItem, ref: str) -> None:
        mem = self._view_memory()
        try:
            structured = mem is not None and not mem.is_scalar(mem.ref(ref).type)
        except Exception:
            structured = False
        if structured and it.childCount() == 0:
            it.addChild(QTreeWidgetItem(["…"]))

    def _expand(self, it: QTreeWidgetItem) -> None:
        if it.childCount() != 1 or it.child(0).data(0, REF) is not None:
            return
        mem = self._view_memory()
        ref = it.data(0, REF)
        if mem is None or ref is None:
            return
        self._filling = True
        it.takeChild(0)
        t = mem.ref(ref).type
        arr = mem.ts.array(t)
        if arr:
            children = [(f"[{k}]", f"{ref}[{k}]", arr.elem) for k in range(arr.lo, min(arr.hi, arr.lo + MAX_CHILDREN - 1) + 1)]
        else:
            children = [(f".{notation.show(f'X.{m}', self.program).split('.', 1)[1] if t in ('TIMER', 'COUNTER') else m}",
                         f"{ref}.{m}", mt) for m, mt in mem.ts.structs[t].items()]
        for label, child_ref, ct in children:
            c = QTreeWidgetItem([""] * len(self.columns))
            c.setText(0, label)
            c.setText(self.col("Type"), notation.type_name(ct))
            c.setData(0, REF, child_ref)
            if mem.is_scalar(ct):
                c.setFlags(c.flags() | Qt.ItemIsEditable)
            it.addChild(c)
            self._add_placeholder(c, child_ref)
        self._filling = False
        self.refresh()

    def _value_text(self, mem, ref: str) -> str:
        try:
            r = mem.ref(ref)
            if not mem.is_scalar(r.type):
                return self.profile.tag_value(mem, ref) if "." not in ref and "[" not in ref else _summary(mem, ref)
            if r.type.lower() == "bool":
                return "1" if mem.read_bit(ref) else "0"
            v = mem.read_word(ref)
            return f"{v:g}" if isinstance(v, float) else str(v)
        except Exception:
            return "?"

    def refresh(self) -> None:
        if not self.program or self.table.state() == QTreeWidget.EditingState:
            return
        mem = self._view_memory()
        self._filling = True
        vc, fc = self.col("Value"), self.col("Force")
        stack = [self.row(r) for r in range(self.table.topLevelItemCount())]
        while stack:
            it = stack.pop()
            ref = it.data(0, REF)
            if ref is None:
                continue
            it.setText(vc, self._value_text(mem, ref) if mem is not None else "")
            forced = next((v for k, v in self.forces.items() if k.lower() == ref.lower()), None)
            it.setText(fc, "" if forced is None else ("ON" if forced else "OFF"))
            if it.isExpanded():
                stack.extend(it.child(k) for k in range(it.childCount()))
        self._filling = False

    # -- editing -----------------------------------------------------------------------
    def _check(self, tags: dict) -> str:
        candidate = copy.copy(self.program)
        candidate.tags = tags
        return self.profile.check_tags(candidate)

    def _reject(self, problem: str) -> None:
        self.message.setText(problem)
        self._fill()

    def _changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._filling or not self.program:
            return
        header, ref = self.columns[column], item.data(0, REF)
        text = item.text(column).strip()
        top = item.parent() is None
        old = ref if top else None
        if header == "Name" and top:
            tags = {(text if k == old else k): v for k, v in self.program.tags.items()}
            problem = self._check(tags)
            if problem:
                return self._reject(problem)
            self.program.tags = tags
            if old in self.program.symbols:
                self.program.symbols[text] = self.program.symbols.pop(old)
            self._fill()
        elif header == "Description" and top:
            if text:
                self.program.symbols[old] = text
            else:
                self.program.symbols.pop(old, None)
        elif header == "Value":
            mem = self._view_memory()
            try:
                t = mem.ref(ref).type.lower()
                v = float(text) if t == "real" else int(float(text))
            except (ValueError, TypeError, AttributeError):
                self.message.setText(f"{text!r} is not a number")
                self.refresh()
                return
            except Exception as e:
                self.message.setText(str(e))
                return
            if self.memory is not None:
                self.memory.write_word(ref, v)          # live change; the declaration keeps its start value
            else:
                self._set_start_value(ref, v)
        elif header not in ("Force",) and top:          # an extra field such as the address
            field = header.lower()
            decl = dict(self.program.tags[old])
            if text:
                decl[field] = text
            else:
                decl.pop(field, None)
            problem = self._check({**self.program.tags, old: decl})
            if problem:
                return self._reject(problem)
            self.program.tags[old] = decl
        else:
            return
        self.message.setText("")
        self.edited.emit()

    def _set_start_value(self, ref: str, value) -> None:
        """Start value of a tag or of one member/element (kept in the declaration's value)."""
        mem = self._view_memory()
        r = mem.ref(ref)
        base = getattr(r, "base", None) or r.tag
        decl = self.program.tags[base]
        path = getattr(r, "path", ())
        if not path:
            decl["value"] = value
            return
        full = _plain(mem, base)
        cur = full
        for key in path[:-1]:
            cur = cur[key]
        cur[path[-1]] = value
        decl["value"] = full

    def _retype(self, name: str, type_: str) -> None:
        if self._filling or not self.program or name not in self.program.tags:
            return
        if type_.lower() == str(self.program.tags[name].get("type", "")).lower():
            return
        decl = {"type": type_}
        problem = ""
        if "address" in self.program.tags[name]:
            decl["address"] = self.program.tags[name]["address"]
            problem = self._check({**self.program.tags, name: decl})
            if problem:                                  # e.g. a Bool address on an Int: drop the address
                decl.pop("address", None)
                problem += "; address removed"
        bad = self._check({**self.program.tags, name: decl})
        if bad:
            return self._reject(bad)
        self.program.tags[name] = decl
        self.message.setText(problem)
        self._fill()
        self.edited.emit()

    def add_tag(self) -> None:
        if not self.program:
            return
        n = 1
        while f"Tag{n}".lower() in {k.lower() for k in self.program.tags}:
            n += 1
        self.program.tags[f"Tag{n}"] = {"type": self.profile.tag_types[0]}
        self._fill()
        self.table.setCurrentItem(self.row(self.table.topLevelItemCount() - 1))
        self.edited.emit()

    def delete_tag(self) -> None:
        it = self.table.currentItem()
        while it is not None and it.parent() is not None:
            it = it.parent()
        if not self.program or it is None:
            return
        name = it.data(0, REF)
        del self.program.tags[name]
        self.program.symbols.pop(name, None)
        self._fill()
        self.edited.emit()

    # -- forcing -------------------------------------------------------------------------
    def _menu(self, pos) -> None:
        it = self.table.itemAt(pos)
        if it is None or it.data(0, REF) is None:
            return
        ref = it.data(0, REF)
        mem = self._view_memory()
        m = QMenu(self)
        try:
            is_bool = mem is not None and mem.ref(ref).type.lower() == "bool"
        except Exception:
            is_bool = False
        if is_bool:
            m.addAction("Force On", lambda: self.force_requested.emit(ref, True))
            m.addAction("Force Off", lambda: self.force_requested.emit(ref, False))
            m.addAction("Remove Force", lambda: self.force_requested.emit(ref, None))
        if it.parent() is None:
            m.addAction("Delete tag", lambda: (self.table.setCurrentItem(it), self.delete_tag()))
        if not m.isEmpty():
            m.exec(self.table.viewport().mapToGlobal(pos))


def _plain(mem, name: str):
    """A tag's current start value as plain lists and dicts."""
    r = mem.ref(name)
    return copy.deepcopy(mem.values[getattr(r, "base", None) or r.tag])


def _summary(mem, ref: str) -> str:
    r = mem.ref(ref)
    arr = mem.ts.array(r.type)
    return f"[{arr.size}]" if arr else "{…}"


class _Cell:
    """A row and a column of the tag tree, read and written like a table cell."""

    def __init__(self, item: QTreeWidgetItem, column: int):
        self._item, self._col = item, column

    def text(self) -> str:
        return self._item.text(self._col)

    def setText(self, text: str) -> None:
        self._item.setText(self._col, text)
