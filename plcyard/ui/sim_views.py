"""Views for the Silo and Traffic simulations. Own vector drawings, colours from tokens."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from ..sims import silo as S
from ..sims import traffic as T
from . import theme
from .primitives import Lamp, SimSwitch


def _mono(text: str, muted=False) -> QLabel:
    l = QLabel(text)
    l.setFont(theme.font("mono", "sm"))
    if muted:
        l.setProperty("muted", "true")
    return l


class _EventBar(QFrame):
    """Shows what went wrong in the machine, with a reset button."""
    reset = Signal()

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        self.text = QLabel()
        self.text.setProperty("status", "danger")
        self.text.setWordWrap(True)
        b = QPushButton("Reset simulation")
        b.clicked.connect(self.reset.emit)
        lay.addWidget(self.text, 1)
        lay.addWidget(b)
        self.hide()

    def show_events(self, events: list[str]) -> None:
        if events:
            self.text.setText(" · ".join(dict.fromkeys(events)))
        self.setVisible(bool(events))


# -- Silo ------------------------------------------------------------------------

def slc_name(direction: str, slot: int, bit: int | None = None) -> str:
    return f"{direction}:{slot}" + ("" if bit is None else f"/{bit}")


class SiloCanvas(QWidget):
    def __init__(self, model: S.SiloModel, io_name=slc_name):
        super().__init__()
        self.n = io_name
        self.model = model
        self.setMinimumSize(320, 200)
        self.setAccessibleName("Silo filling line")

    def paintEvent(self, _):
        m = self.model
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("sim-bg"))
        k = min(self.width() / (S.CONVEYOR_LEN + 40), self.height() / 330)
        p.scale(k, k)
        ox, belt_y = 20, 240
        steel, rail = theme.color("sim-steel"), theme.color("rail")
        # hopper
        hx = ox + S.SENSOR_X
        p.setPen(QPen(rail, 2))
        p.setBrush(theme.color("surface-2"))
        p.drawPolygon([QPointF(hx - 70, 20), QPointF(hx + 70, 20), QPointF(hx + 70, 80),
                       QPointF(hx + 8, 120), QPointF(hx - 8, 120), QPointF(hx - 70, 80)])
        p.setBrush(theme.color("sim-product"))
        p.setPen(Qt.NoPen)
        p.drawPolygon([QPointF(hx - 66, 40), QPointF(hx + 66, 40), QPointF(hx + 66, 78),
                       QPointF(hx + 6, 116), QPointF(hx - 6, 116), QPointF(hx - 66, 78)])
        # solenoid valve + stream
        p.setBrush(theme.color("lamp-amber") if m.solenoid else steel)
        p.drawRect(QRectF(hx - 14, 122, 28, 14))
        if m.solenoid:
            p.setBrush(theme.color("sim-product"))
            p.drawRect(QRectF(hx - 4, 136, 8, belt_y - 136 - 4))
        self._label(p, hx + 20, 132, f"Solenoid {self.n('O', 2, 1)}")
        # belt and motor
        p.setBrush(steel)
        p.drawRoundedRect(QRectF(ox, belt_y, S.CONVEYOR_LEN, 18), 9, 9)
        p.setBrush(theme.color("energized") if m.motor else theme.color("lamp-off"))
        p.drawEllipse(QPointF(ox + S.CONVEYOR_LEN - 10, belt_y + 32), 16, 16)
        self._label(p, ox + S.CONVEYOR_LEN - 120, belt_y + 60, f"Motor {self.n('O', 2, 0)}")
        # boxes
        for b in m.boxes:
            r = QRectF(ox + b.x, belt_y - 56, S.BOX_W, 56)
            p.setPen(QPen(rail, 2))
            p.setBrush(theme.color("bg"))
            p.drawRect(r)
            h = 52 * min(b.fill, 100) / 100
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("danger") if b.spilled else theme.color("sim-product"))
            p.drawRect(QRectF(r.left() + 2, r.bottom() - 2 - h, r.width() - 4, h))
        # sensors
        prox_on, level_on = m.prox(), m.level()
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("energized") if prox_on else theme.color("lamp-off"))
        p.drawRect(QRectF(ox + S.SENSOR_X - 5, belt_y + 22, 10, 22))
        self._label(p, ox + S.SENSOR_X - 50, belt_y + 60, f"Prox {self.n('I', 1, 3)}")
        p.setBrush(theme.color("energized") if level_on else theme.color("lamp-off"))
        p.drawRect(QRectF(hx + 40, belt_y - 100, 10, 26))
        self._label(p, hx + 56, belt_y - 82, f"Level {self.n('I', 1, 4)}")
        if m.spill:
            p.setBrush(theme.color("sim-product"))
            p.drawEllipse(QRectF(ox + S.SENSOR_X - 40, belt_y + 70, 80 + min(m.spill, 200), 12))

    def _label(self, p, x, y, text):
        p.setPen(theme.color("text"))
        p.setFont(theme.font("mono", "xs"))
        p.drawText(QPointF(x, y), text)
        p.setPen(Qt.NoPen)


class SiloView(QWidget):
    reset_requested = Signal()

    def __init__(self, model: S.SiloModel, io_name=slc_name):
        super().__init__()
        self.n = io_name
        self.model = model
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        g = QGridLayout(panel)
        self.start = SimSwitch(normally_closed=False, momentary=True)
        self.stop = SimSwitch(normally_closed=True, momentary=True)
        self.start.changed.connect(lambda _s: setattr(model, "start_pressed", self.start.pressed))
        self.stop.changed.connect(lambda _s: setattr(model, "stop_pressed", self.stop.pressed))
        for w, t in ((self.start, f"Start {self.n('I', 1, 0)}"), (self.stop, f"Stop {self.n('I', 1, 1)}")):
            w.setToolTip(t)
            w.setAccessibleName(t)
        g.addWidget(self.start, 0, 0)
        g.addWidget(_mono(f"Start {self.n('I', 1, 0)}"), 0, 1)
        g.addWidget(self.stop, 1, 0)
        g.addWidget(_mono(f"Stop {self.n('I', 1, 1)} (NC)"), 1, 1)
        sel = QHBoxLayout()
        self.sel_group = QButtonGroup(self)
        for i, name in enumerate("ABC"):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(name == model.selector)
            b.setToolTip(f"Selector {name} → {self.n('I', 1, 5 + i)}")
            b.clicked.connect(lambda _=False, n=name: setattr(model, "selector", n))
            self.sel_group.addButton(b)
            sel.addWidget(b)
        g.addLayout(sel, 2, 0, 1, 2)
        g.addWidget(_mono(f"Selector {self.n('I', 1, 5)}..7", muted=True), 3, 0, 1, 2)
        self.lamps = {}
        for row, (bit, name) in enumerate(((2, f"Run {self.n('O', 2, 2)}"), (3, f"Fill {self.n('O', 2, 3)}"), (4, f"Full {self.n('O', 2, 4)}"))):
            lamp = Lamp({2: "lamp-green", 3: "lamp-amber", 4: "lamp-red"}[bit])
            self.lamps[bit] = lamp
            g.addWidget(lamp, row, 2)
            g.addWidget(_mono(name), row, 3)
        top = QHBoxLayout()
        top.addWidget(panel)
        top.addStretch(1)
        lay.addLayout(top)
        self.canvas = SiloCanvas(model, io_name)
        lay.addWidget(self.canvas, 1)
        self.events = _EventBar()
        self.events.reset.connect(self.reset_requested.emit)
        lay.addWidget(self.events)

    def refresh(self) -> None:
        for bit, lamp in self.lamps.items():
            if lamp.on != self.model.lamp(bit):
                lamp.set_on(self.model.lamp(bit))
        self.events.show_events(self.model.events)
        self.canvas.update()


# -- Traffic ---------------------------------------------------------------------

class TrafficCanvas(QWidget):
    def __init__(self, model: T.TrafficModel, io_name=slc_name):
        super().__init__()
        self.n = io_name
        self.model = model
        self.setMinimumSize(320, 320)
        self.setAccessibleName("Traffic intersection")

    def paintEvent(self, _):
        m = self.model
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("sim-bg"))
        k = min(self.width(), self.height()) / (T.ROAD_LEN + 20)
        p.scale(k, k)
        p.translate(10, 10)
        jc = (T.JUNCTION[0] + T.JUNCTION[1]) / 2
        w = T.JUNCTION[1] - T.JUNCTION[0]
        road = theme.color("sim-steel")
        p.setPen(Qt.NoPen)
        p.setBrush(road)
        p.drawRect(QRectF(0, jc - w / 2, T.ROAD_LEN, w))          # road A (left → right)
        p.drawRect(QRectF(jc - w / 2, 0, w, T.ROAD_LEN))          # road B (top → bottom)
        p.setPen(QPen(theme.color("bg"), 3, Qt.DashLine))
        p.drawLine(QPointF(T.STOP_LINE, jc - w / 2), QPointF(T.STOP_LINE, jc + w / 2))
        p.drawLine(QPointF(jc - w / 2, T.STOP_LINE), QPointF(jc + w / 2, T.STOP_LINE))
        self._head(p, QPointF(T.STOP_LINE - 45, jc + w / 2 + 26), "A", f"{self.n('O', 2, 0)}..2")
        self._head(p, QPointF(jc + w / 2 + 12, T.STOP_LINE - 80), "B", f"{self.n('O', 2, 4)}..6")
        self._walk(p, QPointF(T.STOP_LINE - 200, jc + w / 2 + 40), m.walk("A"), f"Walk {self.n('O', 2, 3)}")
        self._walk(p, QPointF(jc - w / 2 - 150, T.STOP_LINE - 60), m.walk("B"), f"Walk {self.n('O', 2, 7)}")
        for name, car in m.cars.items():
            if car.parked or car.wait > 0:
                continue
            col = theme.color("danger") if m.crashed else theme.color("accent")
            p.setPen(QPen(theme.color("rail"), 1.5))
            p.setBrush(col)
            if name == "A":
                r = QRectF(car.pos - T.CAR_LEN, jc - 18, T.CAR_LEN, 28)
            else:
                r = QRectF(jc - 14, car.pos - T.CAR_LEN, 28, T.CAR_LEN)
            p.drawRoundedRect(r, 6, 6)
        p.setPen(theme.color("text"))
        p.setFont(theme.font("mono", "xs"))
        p.drawText(QPointF(4, jc - w / 2 - 12), f"Car waiting A → {self.n('I', 1, 2)}")
        p.drawText(QPointF(jc + w / 2 + 8, 30), f"Car waiting B → {self.n('I', 1, 3)}")

    def _head(self, p, at: QPointF, road: str, label: str):
        p.setPen(QPen(theme.color("rail"), 2))
        p.setBrush(theme.color("display-bg"))
        p.drawRoundedRect(QRectF(at.x(), at.y(), 30, 76), 6, 6)
        for i, colour in enumerate(("red", "amber", "green")):
            on = self.model.light(road, colour)
            p.setBrush(theme.color(f"lamp-{colour}") if on else theme.color("lamp-off"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(at.x() + 15, at.y() + 14 + i * 24), 9, 9)
        p.setPen(theme.color("text"))
        p.setFont(theme.font("mono", "xs"))
        p.drawText(QPointF(at.x() - 4, at.y() - 6), f"{road}: {label}")

    def _walk(self, p, at: QPointF, on: bool, label: str):
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("lamp-green") if on else theme.color("lamp-off"))
        p.drawRoundedRect(QRectF(at.x(), at.y(), 22, 16), 3, 3)
        p.setPen(theme.color("text"))
        p.setFont(theme.font("mono", "xs"))
        p.drawText(QPointF(at.x() + 28, at.y() + 12), label)


class TrafficView(QWidget):
    reset_requested = Signal()

    def __init__(self, model: T.TrafficModel, io_name=slc_name):
        super().__init__()
        self.n = io_name
        self.model = model
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        row = QHBoxLayout()
        for road, bit in (("A", 0), ("B", 1)):
            sw = SimSwitch(momentary=True)
            sw.changed.connect(lambda _s, r=road, w=sw: model.buttons.__setitem__(r, w.pressed))
            sw.setToolTip(f"Crosswalk button {road} → {self.n('I', 1, bit)}")
            sw.setAccessibleName(sw.toolTip())
            row.addWidget(sw)
            row.addWidget(_mono(f"Walk button {road} {self.n('I', 1, bit)}"))
            row.addSpacing(16)
        for road in "AB":
            cb = QCheckBox(f"Park car {road}")
            cb.setChecked(model.cars[road].parked)
            cb.toggled.connect(lambda on, r=road: setattr(model.cars[r], "parked", on))
            row.addWidget(cb)
        row.addStretch(1)
        lay.addLayout(row)
        self.canvas = TrafficCanvas(model, io_name)
        lay.addWidget(self.canvas, 1)
        self.events = _EventBar()
        self.events.reset.connect(self.reset_requested.emit)
        lay.addWidget(self.events)

    def refresh(self) -> None:
        self.events.show_events(self.model.events)
        self.canvas.update()
