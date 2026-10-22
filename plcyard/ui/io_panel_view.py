"""Widget for the generic I/O simulation."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QMenu, QSpinBox, QVBoxLayout,
                               QWidget, QFrame)

from ..sims.io_panel import DISPLAY_SLOT, INPUT_SLOTS, OUTPUT_SLOTS, THUMBWHEEL_SLOT, IoPanelModel
from . import theme
from .io_drag import attach
from .primitives import DigitDisplay, Lamp, SimSwitch


class IoPanelView(QWidget):
    def __init__(self, model: IoPanelModel, symbols: dict[str, str] | None = None, io_name=None):
        super().__init__()
        self.n = io_name or (lambda d, s, b=None: f"{d}:{s}" + ("" if b is None else f"/{b}"))
        self.model = model
        self.symbols = symbols or {}
        self.switches: dict[tuple[int, int], SimSwitch] = {}
        self.lamps: dict[tuple[int, int], Lamp] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(12)
        cards = QHBoxLayout()
        cards.setSpacing(8)
        for slot in (1, 2, 3, 4):
            cards.addWidget(self._card(slot), 0, Qt.AlignTop)
        cards.addStretch(1)
        outer.addLayout(cards)
        outer.addWidget(self._bcd(), 0, Qt.AlignLeft)
        outer.addStretch(1)

    def _card(self, slot: int) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        grid = QGridLayout(frame)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setVerticalSpacing(2)
        is_input = slot in INPUT_SLOTS
        title = QLabel(self.n("I" if is_input else "O", slot))
        title.setFont(theme.font("mono", "md"))
        grid.addWidget(title, 0, 0, 1, 2, Qt.AlignHCenter)
        grid.setRowMinimumHeight(0, 28)
        for bit in range(16):
            addr = self.n("I" if is_input else "O", slot, bit)
            label = QLabel(f"{bit:02d}")
            label.setFont(theme.font("mono", "sm"))
            label.setProperty("muted", "true")
            if is_input:
                cfg = self.model.switch(slot, bit)
                w = SimSwitch(cfg.normally_closed, cfg.momentary, self.model.pressed.get((slot, bit), False))
                w.changed.connect(lambda _sig, s=slot, b=bit, sw=w: self.model.set_pressed(s, b, sw.pressed))
                w.setContextMenuPolicy(Qt.CustomContextMenu)
                w.customContextMenuRequested.connect(lambda pos, s=slot, b=bit, sw=w: self._switch_menu(s, b, sw, pos))
                w.address = addr
                self.switches[(slot, bit)] = w
            else:
                w = Lamp("lamp-generic")
                self.lamps[(slot, bit)] = w
            from ..core.plc import PLC
            canon = PLC.io_name("I" if is_input else "O", slot, bit)
            tip = f"{addr} {self.symbols.get(canon, self.symbols.get(addr, ''))}".strip()
            w.setToolTip(tip)
            w.setAccessibleName(tip)
            if not is_input:
                attach(w, addr)
            attach(label, addr)
            grid.setRowMinimumHeight(bit + 1, 34)
            grid.addWidget(w, bit + 1, 0, Qt.AlignCenter)
            grid.addWidget(label, bit + 1, 1)
        return frame

    def _bcd(self) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        lay = QGridLayout(frame)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setHorizontalSpacing(12)
        t = QLabel(f"{self.n('I', THUMBWHEEL_SLOT)}  (BCD)")
        t.setFont(theme.font("mono", "md"))
        lay.addWidget(t, 0, 0)
        row = QHBoxLayout()
        self.wheels = []
        for i in range(4):
            sb = QSpinBox()
            sb.setRange(0, 9)
            sb.setWrapping(True)
            sb.setValue(self.model.thumbwheels[i])
            sb.setFont(theme.font("mono", "lg"))
            sb.setMinimumWidth(52)
            sb.setAccessibleName(f"Thumbwheel digit {4 - i}")
            sb.valueChanged.connect(lambda v, k=i: self.model.thumbwheels.__setitem__(k, v))
            row.addWidget(sb)
            self.wheels.append(sb)
        lay.addLayout(row, 0, 1)
        t2 = QLabel(f"{self.n('O', DISPLAY_SLOT)}  (BCD)")
        t2.setFont(theme.font("mono", "md"))
        lay.addWidget(t2, 1, 0)
        self.display = DigitDisplay(0)
        lay.addWidget(self.display, 1, 1)
        return frame

    def _switch_menu(self, slot: int, bit: int, sw: SimSwitch, pos) -> None:
        cfg = self.model.switch(slot, bit)
        menu = QMenu(self)
        for label, nc, mom in (("Toggle, normally open", False, False),
                               ("Toggle, normally closed", True, False),
                               ("Pushbutton, normally open", False, True),
                               ("Pushbutton, normally closed", True, True)):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(cfg.normally_closed == nc and cfg.momentary == mom)
            act.triggered.connect(lambda _=False, n=nc, m=mom: self._set_type(slot, bit, sw, n, m))
        menu.exec(sw.mapToGlobal(pos))

    def _set_type(self, slot, bit, sw: SimSwitch, nc: bool, momentary: bool) -> None:
        cfg = self.model.switch(slot, bit)
        cfg.normally_closed, cfg.momentary = nc, momentary
        sw.nc, sw.momentary = nc, momentary
        if momentary:
            sw.pressed = False
            self.model.set_pressed(slot, bit, False)
        sw.update()

    def refresh(self) -> None:
        for (slot, bit), lamp in self.lamps.items():
            on = self.model.lamp(slot, bit)
            if lamp.on != on:
                lamp.set_on(on)
        self.display.set_word(self.model.outputs.get(DISPLAY_SLOT, 0))
