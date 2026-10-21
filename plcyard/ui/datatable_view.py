"""Data table window (S05): pick a file, see and edit its values in any radix."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QTableView, QVBoxLayout,
                               QWidget, QHeaderView)

from ..core.address import AddressError, parse_address, parse_literal
from ..core.datatable import DataTable, to_int16
from . import theme

FILES = [(0, "O0 Output"), (1, "I1 Input"), (2, "S2 Status"), (3, "B3 Binary"), (4, "T4 Timer"),
         (5, "C5 Counter"), (6, "R6 Control"), (7, "N7 Integer"), (8, "F8 Float")]
STRUCT_COLS = {
    "T": ["EN", "TT", "DN", "PRE", "ACC"],
    "C": ["CU", "CD", "DN", "OV", "UN", "PRE", "ACC"],
    "R": ["EN", "DN", "ER", "UL", "FD", "LEN", "POS"],
}
RADIX = ["Binary", "Octal", "Decimal", "Hex/BCD"]


def fmt(v: int, radix: str) -> str:
    u = v & 0xFFFF
    if radix == "Binary":
        return f"{u:016b}"
    if radix == "Octal":
        return f"{u:o}"
    if radix == "Hex/BCD":
        return f"{u:04X}"
    return str(v)


def parse(text: str, radix: str) -> int:
    """Text in the given radix to a 16-bit word. Decimal is signed (-32768..32767); binary,
    octal and hex are the raw 16 bits (0..FFFF). Anything else raises ValueError."""
    t = text.strip().replace(" ", "")
    base = {"Binary": 2, "Octal": 8, "Hex/BCD": 16}.get(radix, 10)
    v = int(t, base)
    if base == 10:
        if not -32768 <= v <= 32767:
            raise ValueError("out of range")
        return v
    if not 0 <= v <= 0xFFFF:
        raise ValueError("out of range")
    return to_int16(v)


FLOAT_MAX = 3.4028235e38


class TableModel(QAbstractTableModel):
    def __init__(self, dt: DataTable):
        super().__init__()
        self.dt = dt
        self.file_no = 7
        self.radix = "Decimal"

    @property
    def f(self):
        return self.dt.files[self.file_no]

    def _prefix(self) -> str:
        t = self.f.type
        return f"{t}:" if t in ("O", "I", "S") else f"{t}{self.file_no}:"

    def columns(self) -> list[str]:
        if self.f.type in STRUCT_COLS:
            return STRUCT_COLS[self.f.type]
        if self.radix == "Binary" and self.f.type != "F":
            return [str(b) for b in range(15, -1, -1)]
        return ["Value"]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.f.elements

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns())

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.columns()[section]
        return f"{self._prefix()}{section}"

    def address(self, row: int, col: int) -> str:
        base = f"{self._prefix()}{row}"
        cols = self.columns()
        if self.f.type in STRUCT_COLS:
            name = cols[col]
            return f"{base}.{name}" if name in ("PRE", "ACC", "LEN", "POS") else f"{base}/{name}"
        if len(cols) == 16:
            return f"{base}/{15 - col}"
        return base

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        a = self.address(index.row(), index.column())
        if role in (Qt.DisplayRole, Qt.EditRole):
            v = self.dt.read_word(a)
            if self.f.type == "F":
                return f"{v:g}"
            if parse_address(a).is_bit:
                return str(int(v))
            return fmt(int(v), self.radix if self.f.type not in STRUCT_COLS else "Decimal")
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignCenter)
        if role == Qt.FontRole:
            return theme.font("mono", "sm")
        if role == Qt.ForegroundRole and parse_address(a).is_bit and self.dt.read_bit(a):
            return theme.color("energized")
        return None

    def flags(self, index):
        return Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable

    def setData(self, index, value, role=Qt.EditRole):
        a = self.address(index.row(), index.column())
        try:
            if parse_address(a).is_bit:
                if str(value).strip() not in ("0", "1"):
                    return False
                self.dt.write_bit(a, str(value).strip() == "1")
            elif self.f.type == "F":
                v = float(value)
                if not -FLOAT_MAX <= v <= FLOAT_MAX:
                    return False
                self.dt.write_word(a, v)
            else:
                radix = self.radix if self.f.type not in STRUCT_COLS else "Decimal"
                self.dt.write_word(a, parse(str(value), radix))
        except (ValueError, AddressError):
            return False
        self.dataChanged.emit(index, index)
        return True

    def refresh(self):
        if self.rowCount():
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1))


class DataTableView(QWidget):
    def __init__(self, dt: DataTable, symbols: dict[str, str]):
        super().__init__()
        self.symbols = symbols
        self.model = TableModel(dt)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.file_box = QComboBox()
        for n, label in FILES:
            self.file_box.addItem(label, n)
        self.file_box.setCurrentIndex(7)
        self.radix_box = QComboBox()
        self.radix_box.addItems(RADIX)
        self.radix_box.setCurrentText("Decimal")
        top.addWidget(QLabel("Table"))
        top.addWidget(self.file_box)
        top.addWidget(QLabel("Radix"))
        top.addWidget(self.radix_box)
        lay.addLayout(top)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setFont(theme.font("mono", "sm"))
        lay.addWidget(self.table, 1)
        bottom = QHBoxLayout()
        self.addr = QLineEdit()
        self.addr.setPlaceholderText("Go to address, e.g. T4:0")
        self.addr.setFont(theme.font("mono", "sm"))
        self.addr.returnPressed.connect(lambda: self.show_address(self.addr.text()))
        self.symbol = QLabel()
        self.symbol.setProperty("muted", "true")
        bottom.addWidget(self.addr)
        bottom.addWidget(self.symbol, 1)
        lay.addLayout(bottom)
        self.file_box.currentIndexChanged.connect(self._file_changed)
        self.radix_box.currentTextChanged.connect(self._radix_changed)
        self.table.selectionModel().currentChanged.connect(self._current)

    def _file_changed(self, _i):
        self.model.beginResetModel()
        self.model.file_no = self.file_box.currentData()
        self.model.endResetModel()

    def _radix_changed(self, r):
        self.model.beginResetModel()
        self.model.radix = r
        self.model.endResetModel()

    def _current(self, index, _prev):
        if index.isValid():
            a = self.model.address(index.row(), index.column())
            base = a.split("/")[0].split(".")[0]
            self.symbol.setText(f"{a}  {self.symbols.get(a, self.symbols.get(base, ''))}")

    def show_address(self, text: str) -> None:
        try:
            a = parse_address(text)
        except AddressError as e:
            self.symbol.setText(str(e))
            return
        idx = next(i for i, (n, _) in enumerate(FILES) if n == a.file)
        self.file_box.setCurrentIndex(idx)
        row = a.element if isinstance(a.element, int) else 0
        if a.element is None and a.bit is not None:
            row = a.bit // 16
        if row < self.model.rowCount():
            index = self.model.index(row, 0)
            self.table.setCurrentIndex(index)
            self.table.scrollTo(index)

    def refresh(self) -> None:
        if self.isVisible() and not self.table.state() == QTableView.EditingState:
            self.model.refresh()
