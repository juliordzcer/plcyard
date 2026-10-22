"""Online toolbar, as PLC software usually has it: controller mode with its drop-down menu (Go Online,
Upload, Download, modes), forces and edits status, status LEDs, and a button that folds the details
away."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QSlider, QToolButton,
                               QVBoxLayout, QWidget)

from . import theme
from .primitives import Lamp, ModeSelector

MODES = {"PGM": "Program", "RUN": "Run", "STEP": "Test", "FAULT": "Faulted"}


class _Led(QWidget):
    def __init__(self, name: str, colour: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.lamp = Lamp(colour, diameter=10)
        self.label = QLabel(name)
        self.label.setFont(theme.font("mono", "xs"))
        lay.addWidget(self.lamp, 0, Qt.AlignHCenter)
        lay.addWidget(self.label, 0, Qt.AlignHCenter)

    def set(self, on: bool, colour: str | None = None) -> None:
        if colour and colour != self.lamp.colour:
            self.lamp.colour = colour
            self.lamp.update()
        if self.lamp.on != on:
            self.lamp.set_on(on)


class PlcPanel(QFrame):
    go_online = Signal()
    go_offline = Signal()
    upload = Signal()
    remove_forces = Signal()
    mode_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(theme.layout("plc-strip-h") + 18)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 12, 4)
        lay.setSpacing(10)

        # the online box: mode, forces, edits, each with its menu
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(box)
        grid.setContentsMargins(6, 2, 6, 2)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(0)
        self.online_btn = QToolButton()
        self.online_btn.setPopupMode(QToolButton.InstantPopup)
        self.online_btn.setFont(theme.font("sans", "md"))
        self.online_btn.setMinimumWidth(130)
        self.online_btn.setToolTip("Controller mode. Click for Go Online, Upload, Download and modes")
        self.online_menu = QMenu(self)
        self.online_btn.setMenu(self.online_menu)
        self.forces_btn = QToolButton()
        self.forces_btn.setPopupMode(QToolButton.InstantPopup)
        fm = QMenu(self)
        fm.addAction("Remove All Forces", self.remove_forces.emit)
        self.forces_btn.setMenu(fm)
        self.edits = QLabel("No Edits")
        for w in (self.forces_btn, self.edits):
            w.setFont(theme.font("sans", "sm"))
        grid.addWidget(self.online_btn, 0, 0, 2, 1)
        grid.addWidget(self.forces_btn, 0, 1)
        grid.addWidget(self.edits, 1, 1)
        self.fold = QToolButton()
        self.fold.setArrowType(Qt.LeftArrow)
        self.fold.setToolTip("Fold the online bar")
        self.fold.setAutoRaise(True)
        self.fold.clicked.connect(lambda: self.set_folded(not self.folded))
        lay.addWidget(self.fold)
        lay.addWidget(box)

        # everything that folds away
        self.details = QWidget()
        dl = QHBoxLayout(self.details)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(10)
        self.leds: dict[str, _Led] = {}
        leds = QHBoxLayout()
        leds.setSpacing(6)
        for name, colour in (("RUN", "lamp-green"), ("FORCE", "lamp-amber"), ("FAULT", "lamp-red"), ("I/O", "lamp-green")):
            self.leds[name] = _Led(name, colour)
            leds.addWidget(self.leds[name])
        dl.addLayout(leds)
        self.status = QLabel()
        self.status.setMinimumWidth(170)
        self.download = QPushButton("Download")
        self.download.setProperty("variant", "primary")
        self.download.setToolTip("Download to the controller and go online (Ctrl+D)")
        self.mode = ModeSelector("PGM")
        self.clear_fault = QPushButton("Clear fault")
        self.clear_fault.setProperty("variant", "danger")
        self.clear_fault.setVisible(False)
        self.step = QPushButton("Step")
        self.step.setToolTip("Run one scan (F10)")
        self.step.setEnabled(False)
        self.scans = QLabel("0 scans")
        self.scans.setFont(theme.font("mono", "sm"))
        self.scans.setProperty("muted", "true")
        self.io_words = QLabel()
        self.io_words.setFont(theme.font("mono", "sm"))
        self.io_words.setProperty("muted", "true")
        self.forces = QLabel("I/O FORCED")
        self.forces.setProperty("status", "warning")
        self.forces.setToolTip("Some I/O points are forced (right-click them to remove the force)")
        self.forces.setVisible(False)
        for w in (self.status, self.clear_fault, self.download, self.mode, self.step, self.scans, self.io_words,
                  self.forces):
            dl.addWidget(w)
        dl.addStretch(1)
        speed_label = QLabel("Speed")
        speed_label.setProperty("muted", "true")
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(1, 10)
        self.speed.setValue(10)
        self.speed.setFixedWidth(140)
        self.speed.setAccessibleName("Simulation speed")
        dl.addWidget(speed_label)
        dl.addWidget(self.speed)
        lay.addWidget(self.details, 1)
        self.folded = False
        self.set_online(False, "PGM", False)
        self.set_forces(False)
        self._build_menu(False)

    # -- look ----------------------------------------------------------------
    def set_folded(self, folded: bool) -> None:
        self.folded = folded
        self.details.setVisible(not folded)
        self.fold.setArrowType(Qt.RightArrow if folded else Qt.LeftArrow)
        self.fold.setToolTip("Show the online bar" if folded else "Fold the online bar")

    def set_status(self, text: str, kind: str = "") -> None:
        self.status.setText(text)
        self.status.setProperty("status", kind)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def set_online(self, online: bool, mode: str, edits: bool) -> None:
        text = f"Online · {MODES.get(mode, mode)}" if online else "Offline"
        kind = "danger" if mode == "FAULT" and online else ("success" if online and mode in ("RUN", "STEP") else "")
        if self.online_btn.text() != text:
            self.online_btn.setText(text)
            self.online_btn.setProperty("status", kind)
            self.online_btn.style().unpolish(self.online_btn)
            self.online_btn.style().polish(self.online_btn)
        self.edits.setText("Edits pending" if edits else "No Edits")
        self.edits.setProperty("status", "warning" if edits else "")
        if getattr(self, "_menu_online", None) != online:
            self._build_menu(online)

    def set_forces(self, forced: bool) -> None:
        self.forces_btn.setText("Forces Enabled" if forced else "No Forces")
        self.forces_btn.setProperty("status", "warning" if forced else "")
        self.forces_btn.style().unpolish(self.forces_btn)
        self.forces_btn.style().polish(self.forces_btn)

    def set_leds(self, *, running: bool, forced: bool, fault: bool, io: bool, mode: str) -> None:
        run, force, fault_led, io_led = self.leds.values()
        run.set(running)
        force.set(forced)
        fault_led.set(fault)
        io_led.set(io)

    def _build_menu(self, online: bool) -> None:
        self._menu_online = online
        m = self.online_menu
        m.clear()
        dl, up = "Download", "Upload..."
        if online:
            m.addAction("Go Offline", self.go_offline.emit)
        else:
            m.addAction("Go Online", self.go_online.emit)
        m.addAction(up, self.upload.emit)
        m.addAction(dl, self.download.click)
        m.addSeparator()
        for mode, ab in (("PGM", "Program Mode"), ("RUN", "Run Mode"), ("STEP", "Test Mode (single scan)")):
            a = m.addAction(ab, lambda _=False, md=mode: self.mode_requested.emit(md))
            a.setEnabled(online)
        m.addSeparator()
        m.addAction("Clear Faults", self.clear_fault.click)
