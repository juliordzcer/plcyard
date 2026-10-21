"""Instruction palette: categories as tabs, one button per instruction. Click inserts
next to the selection; drag drops it where you want."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QTabBar, QToolButton, QVBoxLayout, QWidget

from ..core import isa
from . import theme
from .ladder_view import start_new_drag

FAMILIES = ["Bit", "Timer/Counter", "Compare", "Math", "Move/Logical", "File/Shift",
            "Sequencer", "Program Control"]


class _Button(QToolButton):
    def __init__(self, mnemonic: str, text: str, tip: str):
        super().__init__()
        self.mnemonic = mnemonic
        self.setText(text)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setFont(theme.font("mono", "sm"))
        self.setMinimumWidth(44)
        self._start: QPoint | None = None

    def mousePressEvent(self, e):
        self._start = e.position().toPoint() if e.button() == Qt.LeftButton else None
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._start is not None and (e.position().toPoint() - self._start).manhattanLength() > 8:
            self._start = None
            self.setDown(False)
            start_new_drag(self, self.mnemonic)
            return
        super().mouseMoveEvent(e)


class InstructionBar(QWidget):
    picked = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(2)
        self.tabs = QTabBar()
        self.tabs.setDrawBase(False)
        lay.addWidget(self.tabs)
        self.row = QHBoxLayout()
        self.row.setSpacing(4)
        lay.addLayout(self.row)
        self.specs: dict[str, isa.Spec] = {}
        self.families: list[str] = []
        self.set_specs(isa.SPECS)
        self.tabs.currentChanged.connect(self._show)

    def set_specs(self, specs: dict[str, isa.Spec]) -> None:
        """Show the instruction set of the selected controller."""
        if specs is self.specs:
            return
        self.specs = specs
        present = list(dict.fromkeys(s.family for s in specs.values()))
        self.families = [f for f in FAMILIES if f in present] + [f for f in present if f not in FAMILIES]
        self.tabs.blockSignals(True)
        while self.tabs.count():
            self.tabs.removeTab(0)
        for f in self.families:
            self.tabs.addTab(f)
        self.tabs.setCurrentIndex(0)
        self.tabs.blockSignals(False)
        self._show(0)

    def _add(self, mnemonic, text, tip):
        b = _Button(mnemonic, text, tip)
        b.clicked.connect(lambda: self.picked.emit(mnemonic))
        self.row.addWidget(b)

    def _show(self, index: int) -> None:
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self._add("RUNG", "Rung +", "New rung below the selection (Insert)")
        self._add("BRANCH", "Branch", "Put the selected instruction in a branch")
        if not 0 <= index < len(self.families):
            self.row.addStretch(1)
            return
        family = self.families[index]
        for m, spec in self.specs.items():
            if spec.family == family:
                glyph = {"contact": "-] [-", "contact_nc": "-]/[-", "coil": f"-({spec.letter or ' '})-"}.get(
                    spec.shape, spec.letter if spec.shape == "small" and spec.letter else m)
                self._add(m, glyph, f"{m} — {spec.title}")
        self.row.addStretch(1)
