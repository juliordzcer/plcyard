"""Design-system gallery: `python -m plcyard.ui.gallery [light|dark] [--shot out.png]`."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import (QApplication, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget, QComboBox)
from PySide6.QtCore import Qt

from . import theme
from .primitives import DigitDisplay, InstructionDemo, Lamp, ModeSelector, SimSwitch


def _row(*widgets) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(12)
    for x in widgets:
        lay.addWidget(x)
    lay.addStretch(1)
    return w


def _box(title: str, *rows) -> QGroupBox:
    g = QGroupBox(title)
    lay = QVBoxLayout(g)
    lay.setSpacing(8)
    for r in rows:
        lay.addWidget(r)
    return g


def _label(text, **props) -> QLabel:
    l = QLabel(text)
    for k, v in props.items():
        l.setProperty(k, v)
    return l


def build() -> QWidget:
    root = QWidget()
    root.setAutoFillBackground(True)
    grid = QGridLayout(root)
    grid.setContentsMargins(16, 16, 16, 16)
    grid.setSpacing(16)

    buttons = []
    for name, variant in (("Download", "primary"), ("Cancel", ""), ("Clear fault", "danger"), ("More", "ghost")):
        b = QPushButton(name)
        b.setProperty("variant", variant)
        buttons.append(b)
    disabled = QPushButton("Disabled")
    disabled.setEnabled(False)
    grid.addWidget(_box("Buttons", _row(*buttons, disabled)), 0, 0)

    good = QLineEdit("T4:0")
    bad = QLineEdit("N7:0x")
    bad.setProperty("invalid", "true")
    radix = QComboBox()
    radix.addItems(["Binary", "Octal", "Decimal", "Hex/BCD"])
    grid.addWidget(_box("Inputs", _row(good, bad, radix)), 0, 1)

    speed = QSlider(Qt.Horizontal)
    speed.setValue(60)
    speed.setFixedWidth(140)
    status = _row(_label("PLC: RUN", status="success"), _label("Program differs", status="warning"),
                  _label("FAULT 0020h", status="danger"), _label("1 024 scans", muted="true"))
    grid.addWidget(_box("PLC panel", _row(ModeSelector("RUN"), speed), status), 1, 0)

    lamps = _row(Lamp("lamp-red", True), Lamp("lamp-amber", True), Lamp("lamp-green", True),
                 Lamp("lamp-generic", True), Lamp("lamp-red", False))
    switches = _row(SimSwitch(), SimSwitch(pressed=True), SimSwitch(normally_closed=True),
                    SimSwitch(momentary=True), SimSwitch(momentary=True, pressed=True))
    grid.addWidget(_box("Simulation I/O", lamps, switches, _row(DigitDisplay(0x1234))), 1, 1)

    contacts = _row(
        InstructionDemo("XIC", ["I:1/0"], "Start"),
        InstructionDemo("XIC", ["I:1/1"], "Stop", energized=True),
        InstructionDemo("XIO", ["I:1/3"], "Prox"),
        InstructionDemo("XIC", ["?"]),
        InstructionDemo("OTE", ["O:2/0"], "Motor", energized=True),
        InstructionDemo("OTL", ["B3:0/0"], selected=True),
        InstructionDemo("OTU", ["B3:0/0"]),
        InstructionDemo("OSR", ["B3:0/1"]),
    )
    blocks = _row(
        InstructionDemo("TON", ["T4:0", "0.1", "100", "37"], labels=["Timer", "Base", "Preset", "Accum"], energized=True),
        InstructionDemo("CTU", ["C5:0", "10", "0"], labels=["Counter", "Preset", "Accum"]),
        InstructionDemo("MOV", ["?", "N7:0"], labels=["Source", "Dest"], selected=True),
    )
    grid.addWidget(_box("Ladder instructions", contacts, blocks), 2, 0, 1, 2)
    return root


def main(argv: list[str]) -> int:
    mode = "dark" if "dark" in argv else "light"
    app = QApplication.instance() or QApplication(argv)
    theme.apply(app, mode)
    w = build()
    w.setWindowTitle(f"PLCYard design — {mode}")
    if "--shot" in argv:
        out = argv[argv.index("--shot") + 1]
        w.adjustSize()
        w.grab().save(out)
        return 0
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
