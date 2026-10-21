"""Tag list for tag-based controllers (Logix, S7): declare tags, see and change their values live.
Columns come from the controller profile: S7 adds the absolute address of a tag."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ..core import profiles
from . import theme

STRUCT_WORDS = ("TIMER", "COUNTER", "PID")        # types whose value is a structure (not editable as a number)


class TagsView(QWidget):
    edited = Signal()          # declarations or descriptions changed (the program is dirty)

    def __init__(self):
        super().__init__()
        self.program = None
        self.profile = None
        self.memory = None
        self._filling = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        self.table = QTableWidget(0, 0)
        self.table.verticalHeader().hide()
        self.table.setFont(theme.font("mono", "sm"))
        self.table.itemChanged.connect(self._changed)
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
        return ["Name", "Type", *fields, "Value", "Description"]

    def col(self, name: str) -> int:
        return self.columns.index(name)

    def _is_struct(self, type_: str) -> bool:
        return any(w in type_.upper() for w in STRUCT_WORDS)

    # -- data ------------------------------------------------------------------------
    def set_program(self, program) -> None:
        self.program = program
        self.profile = profiles.get(program.profile) if program else None
        self._fill()

    def set_memory(self, memory) -> None:
        """Live values while the PLC runs this program; None shows the start values."""
        self.memory = memory
        self.refresh()

    def _fill(self) -> None:
        self._filling = True
        cols = self.columns
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        head = self.table.horizontalHeader()
        for c in range(len(cols) - 1):
            head.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        head.setSectionResizeMode(len(cols) - 1, QHeaderView.Stretch)
        self.table.setRowCount(0)
        for name, d in (self.program.tags.items() if self.program else []):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, self.col("Name"), QTableWidgetItem(name))
            box = QComboBox()
            box.addItems(self.profile.tag_types)
            box.setCurrentText(next((t for t in self.profile.tag_types if t.lower() == str(d.get("type", "")).lower()),
                                    self.profile.tag_types[0]))
            box.currentTextChanged.connect(lambda t, n=name: self._retype(n, t))
            self.table.setCellWidget(r, self.col("Type"), box)
            for f in self.profile.tag_fields:
                self.table.setItem(r, self.col(f.capitalize()), QTableWidgetItem(str(d.get(f, ""))))
            self.table.setItem(r, self.col("Value"), QTableWidgetItem(""))
            self.table.setItem(r, self.col("Description"), QTableWidgetItem(self.program.symbols.get(name, "")))
        self._filling = False
        self.refresh()

    def _value_text(self, name: str, d: dict) -> str:
        if self.memory is not None:
            try:
                return self.profile.tag_value(self.memory, name)
            except Exception:
                return "?"
        return "" if self._is_struct(str(d.get("type", ""))) else str(d.get("value", 0))

    def refresh(self) -> None:
        if not self.program or self.table.state() == QTableWidget.EditingState:
            return
        self._filling = True
        vc = self.col("Value")
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text()
            d = self.program.tags.get(name, {})
            item = self.table.item(r, vc)
            item.setText(self._value_text(name, d))
            editable = not self._is_struct(str(d.get("type", "")))
            item.setFlags((item.flags() | Qt.ItemIsEditable) if editable else (item.flags() & ~Qt.ItemIsEditable))
        self._filling = False

    # -- editing -----------------------------------------------------------------------
    def _reject(self, problem: str) -> None:
        self.message.setText(problem)
        self._fill()

    def _changed(self, item: QTableWidgetItem) -> None:
        if self._filling or not self.program:
            return
        r, header = item.row(), self.columns[item.column()]
        old = list(self.program.tags)[r]
        text = item.text().strip()
        if header == "Name":
            tags = {(text if k == old else k): v for k, v in self.program.tags.items()}
            problem = self.profile.check_tags(tags)
            if problem:
                return self._reject(problem)
            self.program.tags = tags
            if old in self.program.symbols:
                self.program.symbols[text] = self.program.symbols.pop(old)
            self._fill()
        elif header == "Description":
            if text:
                self.program.symbols[old] = text
            else:
                self.program.symbols.pop(old, None)
        elif header == "Value":
            t = str(self.program.tags[old].get("type", "")).lower()
            try:
                v = float(text) if t == "real" else int(float(text))
            except ValueError:
                self.message.setText(f"{text!r} is not a number")
                self.refresh()
                return
            if self.memory is not None:
                self.memory.write_word(old, v)          # live change; the declaration keeps its start value
            else:
                self.program.tags[old]["value"] = v
        else:                                           # an extra field such as the S7 address
            field = header.lower()
            decl = dict(self.program.tags[old])
            if text:
                decl[field] = text
            else:
                decl.pop(field, None)
            tags = {**self.program.tags, old: decl}
            problem = self.profile.check_tags(tags)
            if problem:
                return self._reject(problem)
            self.program.tags[old] = decl
        self.message.setText("")
        self.edited.emit()

    def _retype(self, name: str, type_: str) -> None:
        if self._filling or not self.program:
            return
        decl = {"type": type_}
        if "address" in self.program.tags[name] and not self._is_struct(type_):
            decl["address"] = self.program.tags[name]["address"]
        problem = self.profile.check_tags({**self.program.tags, name: decl})
        if problem:                                   # e.g. a Bool address on an Int: drop the address
            decl.pop("address", None)
        self.program.tags[name] = decl
        self.message.setText(problem and f"{problem}; address removed")
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
        self.table.setCurrentCell(self.table.rowCount() - 1, 0)
        self.edited.emit()

    def delete_tag(self) -> None:
        r = self.table.currentRow()
        if not self.program or r < 0:
            return
        name = list(self.program.tags)[r]
        del self.program.tags[name]
        self.program.symbols.pop(name, None)
        self._fill()
        self.edited.emit()
