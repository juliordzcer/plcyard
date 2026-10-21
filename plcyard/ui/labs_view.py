"""Exercises dock (S14): list, text, and buttons to load the simulation and a starter program."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QSplitter,
                               QTextBrowser, QVBoxLayout, QWidget)
from PySide6.QtCore import Qt

from .. import labs
from ..core import profiles

SIM_NAMES = {"io": "I/O panel", "silo": "Silo", "traffic": "Traffic lights", "tank": "Tank level"}


class LabsView(QWidget):
    load_simulation = Signal(str)
    open_starter = Signal(object)        # labs.Lab
    check_requested = Signal(object)     # labs.Lab

    def __init__(self):
        super().__init__()
        self.items = labs.load_all()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        split = QSplitter(Qt.Vertical)
        self.list = QListWidget()
        for lab in self.items:
            it = QListWidgetItem(f"{lab.id}. {lab.title}")
            it.setToolTip(f"Level {lab.level}, simulation: {SIM_NAMES[lab.simulation]}, controller: "
                          f"{profiles.get(lab.controller).title}")
            self.list.addItem(it)
        self.text = QTextBrowser()
        self.text.setOpenExternalLinks(True)
        split.addWidget(self.list)
        split.addWidget(self.text)
        self.result = QTextBrowser()
        self.result.setAccessibleName("Check results")
        self.result.hide()
        split.addWidget(self.result)
        split.setSizes([160, 400, 200])
        lay.addWidget(split, 1)
        row = QHBoxLayout()
        self.sim_btn = QPushButton("Load simulation")
        self.start_btn = QPushButton("New program for this exercise")
        self.start_btn.setProperty("variant", "primary")
        self.start_btn.setToolTip("Empty program with the exercise's symbols (switch types come wired)")
        row.addWidget(self.sim_btn)
        row.addWidget(self.start_btn)
        lay.addLayout(row)
        self.check_btn = QPushButton("Check my program")
        self.check_btn.setToolTip("Runs the program in the editor against every requirement of this exercise")
        lay.addWidget(self.check_btn)
        self.list.currentRowChanged.connect(self._show)
        self.sim_btn.clicked.connect(lambda: self.current and self.load_simulation.emit(self.current.simulation))
        self.start_btn.clicked.connect(lambda: self.current and self.open_starter.emit(self.current))
        self.check_btn.clicked.connect(lambda: self.current and self.check_requested.emit(self.current))
        if self.items:
            self.list.setCurrentRow(0)

    @property
    def current(self) -> labs.Lab | None:
        i = self.list.currentRow()
        return self.items[i] if 0 <= i < len(self.items) else None

    def _show(self, i: int) -> None:
        if 0 <= i < len(self.items):
            self.text.setMarkdown(self.items[i].body)
            self.result.hide()

    def show_report(self, report) -> None:
        if report.error:
            md = f"**Could not check the program**\n\n{report.error}"
        else:
            head = "**All requirements met**" if report.passed else f"**{report.score} requirements met**"
            lines = [f"- {'✔' if c.passed else '✘'} {c.requirement}" + (f" — {c.detail}" if c.detail else "")
                     for c in report.checks]
            md = head + "\n\n" + "\n".join(lines)
        self.result.setMarkdown(md)
        self.result.show()
