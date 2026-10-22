"""Compare languages: an exercise's reference solution in ladder, structured text and function block
diagram, side by side. Each column is a copy: changes stay here; "Open" loads one into the editor."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QSplitter, QVBoxLayout, QWidget

from .. import formats
from . import theme
from .block_editor import RoutineDoc

NAMES = {"LD": "Ladder", "ST": "Structured text", "FBD": "Function block diagram"}


class CompareDialog(QDialog):
    open_file = Signal(str)

    def __init__(self, parent, lab):
        super().__init__(parent)
        self.setWindowTitle(f"Exercise {lab.id}: {lab.title} — three languages")
        self.resize(1500, 760)
        lay = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        self.docs: dict[str, RoutineDoc] = {}
        for lang, path in lab.solutions.items():
            program = formats.load(path)
            col = QWidget()
            cl = QVBoxLayout(col)
            cl.setContentsMargins(4, 4, 4, 4)
            head = QHBoxLayout()
            title = QLabel(NAMES[lang])
            title.setFont(theme.font("sans", "md"))
            head.addWidget(title)
            head.addStretch(1)
            btn = QPushButton("Open")
            btn.setToolTip("Open this solution in the editor (read-only file: Save asks for a new name)")
            btn.clicked.connect(lambda _=False, p=str(path): (self.open_file.emit(p), self.accept()))
            head.addWidget(btn)
            cl.addLayout(head)
            doc = RoutineDoc(program, 2)
            self.docs[lang] = doc
            cl.addWidget(doc, 1)
            split.addWidget(col)
        for k in range(split.count()):
            split.setStretchFactor(k, 1)
            split.widget(k).setMinimumWidth(320)
        split.setSizes([500] * split.count())
        lay.addWidget(split, 1)
