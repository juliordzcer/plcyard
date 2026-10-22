"""Views for the elevator, bottle line, sorting conveyor, pick and place, parking garage, pump
station, room climate and washing machine. Same pattern as more_sim_views: controls on top, an
animated drawing with draggable address labels, events at the bottom."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QCheckBox, QPushButton

from ..sims import bottles as B
from ..sims import elevator as E
from ..sims import hvac as H
from ..sims import parking as P
from ..sims import pick_place as K
from ..sims import pump_station as S
from ..sims import sorter as O
from ..sims import washer as M
from . import theme
from .more_sim_views import TwoTankTrend, _Canvas, _Panel
from .primitives import SimSwitch
from .sim_views import _mono, default_name
from .tank_view import default_analog
from .io_drag import attach


def _check(panel: _Panel, row: int, text: str, attr: str, col: int = 0) -> QCheckBox:
    box = QCheckBox(text)
    box.setChecked(bool(getattr(panel.model, attr)))
    box.toggled.connect(lambda on: setattr(panel.model, attr, on))
    panel.grid.addWidget(box, row, col, 1, 2)
    panel.checks = getattr(panel, "checks", []) + [(box, attr)]
    return box


def _sync_checks(panel: _Panel) -> None:
    for box, attr in getattr(panel, "checks", []):
        if box.isChecked() != bool(getattr(panel.model, attr)):
            box.setChecked(bool(getattr(panel.model, attr)))


def _box(p, r: QRectF, on: bool, text: str = "") -> None:
    p.setPen(QPen(theme.color("sim-steel"), 2))
    p.setBrush(theme.color("energized") if on else theme.color("bg"))
    p.drawRect(r)
    if text:
        p.setPen(theme.color("text"))
        p.setFont(theme.font("sans", "xs"))
        p.drawText(r, Qt.AlignCenter, text)


def _belt(p, y: float, length: float, moving: bool) -> None:
    p.setPen(QPen(theme.color("sim-steel"), 3))
    p.setBrush(theme.color("energized") if moving else theme.color("bg"))
    p.drawRoundedRect(QRectF(0, y, length, 12), 6, 6)


# -- elevator ----------------------------------------------------------------------------------------------
class ElevatorCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(520, 360))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        steel = theme.color("sim-steel")
        shaft = QRectF(200, 20, 120, 320)
        p.setPen(QPen(steel, 3))
        p.setBrush(theme.color("surface"))
        p.drawRect(shaft)
        floor_y = lambda k: shaft.bottom() - 10 - k * 100            # floor k (0-2) sill
        for k in range(3):
            y = floor_y(k)
            p.setPen(QPen(steel, 2))
            p.drawLine(QPointF(shaft.left() - 60, y), QPointF(shaft.left(), y))
            p.setPen(theme.color("text"))
            p.setFont(theme.font("sans", "md"))
            p.drawText(QPointF(shaft.left() - 60, y - 70), f"Floor {k + 1}")
            self.switch(p, QPointF(shaft.right() + 12, y - 40), m.floor_at() == k)
            self._label(p, shaft.right() + 22, y - 36, f"At {k + 1} {self.n('I', 1, 6 + k)}")
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("lamp-amber") if m.out(4 + k) else theme.color("lamp-off"))
            p.drawEllipse(QPointF(shaft.left() - 20, y - 60), 6, 6)
            if k in m.waiting:
                p.setBrush(theme.color("accent"))
                p.drawEllipse(QPointF(shaft.left() - 44, y - 22), 7, 7)          # a waiting passenger
                p.drawRect(QRectF(shaft.left() - 50, y - 15, 12, 15))
        car_y = shaft.bottom() - 10 - m.position * 100 / E.FLOOR
        car = QRectF(shaft.left() + 10, car_y - 80, shaft.width() - 20, 80)
        p.setPen(QPen(theme.color("text"), 2))
        p.setBrush(theme.color("accent-soft"))
        p.drawRect(car)
        gap = (car.width() / 2) * m.door / 100.0                       # doors slide apart
        p.setBrush(QColor(theme.color("sim-steel")).lighter(150))
        p.drawRect(QRectF(car.left(), car.top(), car.width() / 2 - gap, car.height()))
        p.drawRect(QRectF(car.center().x() + gap, car.top(), car.width() / 2 - gap, car.height()))
        if m.blocked:
            p.setPen(QPen(theme.color("danger"), 2, Qt.DashLine))
            p.drawLine(QPointF(car.center().x(), car.top() + 10), QPointF(car.center().x(), car.bottom()))
        p.setPen(QPen(steel, 2))
        p.drawLine(QPointF(car.center().x(), shaft.top()), QPointF(car.center().x(), car.top()))
        _box(p, QRectF(230, 0, 60, 16), m.out(0) or m.out(1), "▲" if m.out(0) else ("▼" if m.out(1) else "motor"))
        for k, text in enumerate((f"Up {self.n('O', 2, 0)}", f"Down {self.n('O', 2, 1)}",
                                  f"Door open {self.n('O', 2, 2)}", f"Door close {self.n('O', 2, 3)}",
                                  f"Open limit {self.n('I', 1, 9)}", f"Closed limit {self.n('I', 1, 10)}",
                                  f"Safety edge {self.n('I', 1, 11)}")):
            self._label(p, 4, 268 + 14 * k, text)
        self._label(p, 4, 14, f"Served {m.served}")
        p.end()


class ElevatorView(_Panel):
    def __init__(self, model: E.ElevatorModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        for k in range(3):
            for col, (kind, bit) in enumerate((("Call", k), ("Car", 3 + k))):
                w = SimSwitch(momentary=True)
                if kind == "Call":
                    w.changed.connect(lambda _s, f=k, sw=w: model.press_hall(f, sw.pressed))
                else:
                    w.changed.connect(lambda _s, f=k, sw=w: model.car.__setitem__(f, sw.pressed))
                label = f"{kind} {k + 1} {self.n('I', 1, bit)}"
                w.setToolTip(label)
                w.address = self.n("I", 1, bit)
                self.grid.addWidget(w, 2 - k, col * 2)
                self.grid.addWidget(attach(_mono(label), w.address), 2 - k, col * 2 + 1)
        _check(self, 3, "Someone in the doorway", "blocked")
        self.finish(ElevatorCanvas(model, io_name, analog_name))

    def refresh(self) -> None:
        _sync_checks(self)
        super().refresh()


# -- bottle line ---------------------------------------------------------------------------------------------
class BottleCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(660, 300))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        belt_y = 200.0
        _belt(p, belt_y, B.LENGTH, m.out(0))
        for b in m.bottles:
            if b.x < -30:
                continue
            body = QRectF(b.x - 12, belt_y - 60, 24, 60)
            p.setPen(QPen(theme.color("sim-steel"), 2))
            p.setBrush(theme.color("bg"))
            p.drawRoundedRect(body, 5, 5)
            h = 55 * min(b.fill, 100.0) / 100.0
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("sim-product"))
            p.drawRect(QRectF(body.left() + 3, body.bottom() - 3 - h, body.width() - 6, h))
            if b.capped:
                p.setBrush(theme.color("danger") if b.bad_cap else theme.color("success"))
                p.drawRect(QRectF(b.x - 8, body.top() - 8, 16, 8))
        for row, (x, on, name, label) in enumerate(((B.FILLER, m.out(1), "Filler", f"Fill {self.n('O', 2, 1)}"),
                                   (B.CAPPER, m.out(2), "Capper", f"Cap {self.n('O', 2, 2)}"),
                                   (B.INSPECT, m.out(3), "Reject", f"Reject {self.n('O', 2, 3)}"))):
            drop = 40 if on else 0
            _box(p, QRectF(x - 22, 70 + (drop if name == "Capper" else 0), 44, 30), on, name)
            if name == "Filler" and on:
                p.setPen(QPen(theme.color("sim-product"), 4))
                p.drawLine(QPointF(x, 100), QPointF(x, belt_y - 60))
            self._label(p, x - 30, 34 + 14 * row, label)
        for x, bit, label in ((B.FILLER, 2, "at filler"), (B.CAPPER, 4, "at capper"), (B.INSPECT, 5, "inspect")):
            self.switch(p, QPointF(x, belt_y + 26), m.at(x) is not None)
            self._label(p, x - 30, belt_y + 46, f"{self.n('I', 1, bit)}")
        self._label(p, 4, 16, f"Conveyor {self.n('O', 2, 0)}   Full {self.n('I', 1, 3)}   Good {self.n('I', 1, 6)}")
        p.setFont(theme.font("mono", "sm"))
        p.setPen(theme.color("text"))
        p.drawText(QPointF(4, 290), f"Shipped good {m.shipped_good}  bad {m.shipped_bad}   "
                                    f"Rejected bad {m.rejected_bad}  good {m.rejected_good}")
        p.end()


class BottleView(_Panel):
    def __init__(self, model: B.BottleModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Start", "start_pressed")
        self.button(1, 1, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 4, "Run", "lamp-green")
        self.finish(BottleCanvas(model, io_name, analog_name))


# -- sorting conveyor -------------------------------------------------------------------------------------------
class SorterCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(760, 320))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        p.translate(100, 0)
        belt_y = 150.0
        _belt(p, belt_y, O.LENGTH, m.out(0))
        for b in m.boxes:
            h = O.HEIGHT[b.size]
            p.setPen(QPen(theme.color("text"), 1.5))
            p.setBrush(theme.color("warning"))
            p.drawRect(QRectF(b.x - 18, belt_y - h, 36, h))
        # beams
        for h, bit, name in ((28.0, 3, "Low beam"), (42.0, 4, "High beam")):
            p.setPen(QPen(theme.color("danger"), 1.5, Qt.DashLine))
            p.drawLine(QPointF(O.MEASURE - 26, belt_y - h), QPointF(O.MEASURE + 26, belt_y - h))
            p.setFont(theme.font("mono", "xs"))
            label = f"{name} {self.n('I', 1, bit)}"
            self._label(p, O.MEASURE - 32 - p.fontMetrics().horizontalAdvance(label), belt_y - h + 4, label)
        self.switch(p, QPointF(O.MEASURE, belt_y + 26), m.at(O.MEASURE) is not None)
        self._label(p, O.MEASURE - 40, belt_y + 46, f"Box {self.n('I', 1, 2)}")
        for k, x in enumerate(O.PUSHERS):
            out = m.out(k + 1)
            _box(p, QRectF(x - 18, belt_y + 20 + (0 if out else 20), 36, 16), out)
            self._label(p, x - 30, belt_y + 70 + 30 * k, f"Push {self.n('O', 2, k + 1)}")
            self._label(p, x - 30, belt_y + 84 + 30 * k, f"At {self.n('I', 1, 5 + k)}")
            bin_r = QRectF(x - 30, 20, 60, 60)
            p.setPen(QPen(theme.color("sim-steel"), 2))
            p.setBrush(theme.color("surface"))
            p.drawRect(bin_r)
            p.setPen(theme.color("text"))
            p.setFont(theme.font("sans", "sm"))
            got = m.bins[k + 1]
            p.drawText(bin_r, Qt.AlignCenter, f"{'SML'[k]}\n{len(got)}")
        self._label(p, -90, 310, f"Conveyor {self.n('O', 2, 0)}   Wrong bin {m.wrong}   Fell off {m.fallen}")
        p.end()


class SorterView(_Panel):
    def __init__(self, model: O.SorterModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Start", "start_pressed")
        self.button(1, 1, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 4, "Run", "lamp-green")
        self.finish(SorterCanvas(model, io_name, analog_name))


# -- pick and place --------------------------------------------------------------------------------------------
class PickPlaceCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(660, 320))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        steel = theme.color("sim-steel")
        pick_x, place_x, top, bottom = 110.0, 410.0, 70.0, 230.0
        x = pick_x + (place_x - pick_x) * m.x / 100.0
        z = top + (bottom - 30 - top) * m.z / 100.0
        p.setPen(QPen(steel, 6))
        p.drawLine(QPointF(60, 50), QPointF(460, 50))            # rail
        _box(p, QRectF(x - 20, 40, 40, 20), m.out(0))
        p.setPen(QPen(steel, 6))
        p.drawLine(QPointF(x, 60), QPointF(x, z))                # vertical rod
        _box(p, QRectF(x - 16, z, 32, 14), m.out(2), "")         # vacuum cup
        if m.held:
            p.setBrush(theme.color("warning"))
            p.drawRect(QRectF(x - 14, z + 14, 28, 18))
        # infeed and tray
        p.setPen(QPen(steel, 3))
        p.setBrush(theme.color("surface"))
        p.drawRect(QRectF(pick_x - 40, bottom, 80, 14))
        p.drawRect(QRectF(place_x - 60, bottom, 120, 14))
        if m.part_waiting:
            p.setBrush(theme.color("warning"))
            p.drawRect(QRectF(pick_x - 14, bottom - 18, 28, 18))
        p.setPen(theme.color("text"))
        p.setFont(theme.font("sans", "md"))
        p.drawText(QRectF(place_x - 60, bottom + 18, 120, 20), Qt.AlignCenter, f"Placed {m.placed}")
        for at, on, label in ((QPointF(pick_x, 30), m.x <= 0, f"Pick side {self.n('I', 1, 2)}"),
                              (QPointF(place_x, 30), m.x >= 100, f"Place side {self.n('I', 1, 3)}")):
            self.switch(p, at, on)
            self._label(p, at.x() - 50, 20, label)
        self._label(p, 470, 80, f"Up {self.n('I', 1, 4)}")
        self._label(p, 470, 96, f"Down {self.n('I', 1, 5)}")
        self._label(p, 470, 112, f"Part {self.n('I', 1, 6)}")
        self._label(p, 470, 128, f"Vacuum OK {self.n('I', 1, 7)}")
        self._label(p, 4, 290, f"Extend {self.n('O', 2, 0)}  Down {self.n('O', 2, 1)}  Vacuum {self.n('O', 2, 2)}")
        self._label(p, 4, 306, f"Dropped {m.dropped}")
        p.end()


class PickPlaceView(_Panel):
    def __init__(self, model: K.PickPlaceModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Start", "start_pressed")
        self.button(1, 1, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 3, "Cycle", "lamp-green")
        self.finish(PickPlaceCanvas(model, io_name, analog_name))


# -- parking garage --------------------------------------------------------------------------------------------
class ParkingCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(640, 300))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        p.translate(20, 0)
        steel = theme.color("sim-steel")
        lot = QRectF(160, 40, 280, 200)
        p.setPen(QPen(steel, 3))
        p.setBrush(theme.color("surface"))
        p.drawRect(lot)
        for k in range(P.CAPACITY):                             # spaces, filled ones with a car
            r = QRectF(lot.left() + 12 + (k % 5) * 52, lot.top() + 16 + (k // 5) * 96, 44, 72)
            p.setPen(QPen(steel, 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            if k < m.parked:
                p.setPen(QPen(theme.color("text"), 1.5))
                p.setBrush(theme.color("accent-soft"))
                p.drawRoundedRect(r.adjusted(6, 8, -6, -8), 6, 6)
        for y, pos, bit, name, queue, passing in ((90.0, m.entry_barrier, 0, "Entry", m.entry_queue, m._entry_pass >= 0),
                                                  (190.0, m.exit_barrier, 1, "Exit", m.exit_queue, m._exit_pass >= 0)):
            ang = math.radians(80 * pos / 100.0)
            p.setPen(QPen(theme.color("danger"), 5))
            pivot = QPointF(130, y)
            p.drawLine(pivot, QPointF(130 - 70 * math.cos(ang), y - 70 * math.sin(ang)))
            p.setPen(QPen(steel, 2))
            p.setBrush(theme.color("energized") if m.out(bit) else theme.color("bg"))
            p.drawRect(QRectF(124, y - 6, 12, 18))
            self._label(p, 4, y - 26, f"{name} {self.n('O', 2, bit)}")
            self._label(p, 4, y + 30, f"Up {self.n('I', 1, 4 + bit)}")
            for k in range(min(queue, 3)):
                p.setPen(QPen(theme.color("text"), 1.5))
                p.setBrush(theme.color("warning"))
                p.drawRoundedRect(QRectF(20 + k * 30 if name == "Entry" else 20 + k * 30, y - 2, 26, 16), 5, 5)
            if passing:
                p.setBrush(theme.color("accent"))
                p.drawRoundedRect(QRectF(118, y + 14, 26, 16), 5, 5)
        self._label(p, 4, 260, f"Waiting entry {self.n('I', 1, 0)}  passed {self.n('I', 1, 1)}")
        self._label(p, 4, 276, f"Waiting exit {self.n('I', 1, 2)}  passed {self.n('I', 1, 3)}")
        p.setPen(QPen(steel, 2))
        p.setBrush(theme.color("display-bg"))
        sign = QRectF(460, 50, 120, 60)
        p.drawRect(sign)
        p.setPen(theme.color("lamp-red") if m.out(2) else theme.color("lamp-green"))
        p.setFont(theme.font("mono", "xl"))
        p.drawText(sign, Qt.AlignCenter, "FULL" if m.out(2) else (str(m.display) if m.display >= 0 else "--"))
        self._label(p, 460, 130, f"Sign {self.n('O', 2, 2)}")
        self._label(p, 460, 146, f"Display {self.n('O', 6)}")
        p.setPen(theme.color("text"))
        p.setFont(theme.font("sans", "sm"))
        p.drawText(QPointF(460, 190), f"Parked {m.parked}/{P.CAPACITY}")
        p.end()


class ParkingView(_Panel):
    def __init__(self, model: P.ParkingModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        arrive, leave = QPushButton("Car arrives"), QPushButton("Car leaves")
        arrive.clicked.connect(model.car_arrives)
        leave.clicked.connect(model.car_leaves)
        self.grid.addWidget(arrive, 0, 0)
        self.grid.addWidget(leave, 0, 1)
        _check(self, 1, "Traffic (cars come and go by themselves)", "traffic")
        self.lamp(0, 2, "FULL", "lamp-red")
        self.finish(ParkingCanvas(model, io_name, analog_name))

    def refresh(self) -> None:
        _sync_checks(self)
        super().refresh()


# -- pump station ----------------------------------------------------------------------------------------------
class PumpCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(720, 320))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        p.translate(70, 0)
        sump = QRectF(150, 60, 160, 220)
        water = theme.color("sim-product")
        p.setPen(QPen(water if m.inflow > 0 else theme.color("sim-steel"), 6))
        p.drawLine(QPointF(20, 30), QPointF(sump.left() + 20, 30))
        p.drawLine(QPointF(sump.left() + 20, 30), QPointF(sump.left() + 20, sump.top() + 10))
        self._label(p, 20, 20, f"Inflow {m.inflow:.0f} %")
        self.tank(p, sump, m.level, water)
        for k in range(2):
            x = sump.right() + 60 + k * 160
            on = m.running(k)
            p.setPen(QPen(water if on else theme.color("sim-steel"), 6))
            p.drawLine(QPointF(sump.right() - 20 - k * 40, sump.bottom() - 10), QPointF(sump.right() - 20 - k * 40, 30))
            p.drawLine(QPointF(sump.right() - 20 - k * 40, 30), QPointF(x, 30))
            p.setPen(QPen(theme.color("sim-steel"), 2))
            p.setBrush(theme.color("danger") if m.fault[k] else (theme.color("energized") if on else theme.color("bg")))
            p.drawEllipse(QPointF(x, 120), 22, 22)
            p.setPen(theme.color("text"))
            p.setFont(theme.font("sans", "sm"))
            p.drawText(QRectF(x - 22, 109, 44, 22), Qt.AlignCenter, f"P{k + 1}")
            self._label(p, x - 30, 160, f"Run {self.n('O', 2, k)}")
            self._label(p, x - 30, 176, f"Fault {self.n('I', 1, 6 + k)}")
            p.setFont(theme.font("mono", "xs"))
            p.setPen(theme.color("text"))
            p.drawText(QPointF(x - 30, 196), f"{m.run_s[k]:.0f} s, {m.starts[k]} starts")
        for lvl, bit, name in ((S.ALARM, 5, "Alarm"), (S.HIGH, 4, "High"), (S.START, 3, "Start"), (S.LOW, 2, "Low")):
            y = sump.bottom() - sump.height() * lvl / 100.0
            self.switch(p, QPointF(sump.left() - 10, y), m.level >= lvl)
            p.setFont(theme.font("mono", "xs"))
            label = f"{name} {self.n('I', 1, bit)}"
            self._label(p, sump.left() - 16 - p.fontMetrics().horizontalAdvance(label), y + 4, label)
        p.setFont(theme.font("mono", "md"))
        p.setPen(theme.color("text"))
        p.drawText(QRectF(sump.left(), sump.top() + 4, sump.width(), 20), Qt.AlignCenter, f"{m.level:.1f} %")
        self._label(p, sump.left(), sump.bottom() + 20, f"Level {self.a('I', 0)}")
        p.end()


class PumpView(_Panel):
    def __init__(self, model: S.PumpStationModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Reset alarm", "reset_pressed")
        self.button(1, 1, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 2, "Alarm", "lamp-red")
        self.slider(2, "Inflow", "inflow")
        for k in range(2):
            box = QCheckBox(f"Pump {k + 1} fails")
            box.toggled.connect(lambda on, i=k: model.fault.__setitem__(i, on))
            self.grid.addWidget(box, 3, k * 2, 1, 2)
        self.finish(PumpCanvas(model, io_name, analog_name))


# -- room climate ----------------------------------------------------------------------------------------------
class HvacCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(560, 300))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        room = QRectF(140, 40, 260, 180)
        warm, cold = QColor(theme.color("lamp-red")), QColor(theme.color("accent"))
        t = min(max((m.temperature - 10.0) / 20.0, 0.0), 1.0)          # 10 °C blue … 30 °C red
        fill = QColor.fromRgbF(cold.redF() + (warm.redF() - cold.redF()) * t,
                               cold.greenF() + (warm.greenF() - cold.greenF()) * t,
                               cold.blueF() + (warm.blueF() - cold.blueF()) * t, 0.25)
        p.setPen(QPen(theme.color("sim-steel"), 4))
        p.setBrush(fill)
        p.drawRect(room)
        p.setBrush(theme.color("bg") if not m.window else theme.color("sim-bg"))
        p.drawRect(QRectF(room.right() - 4, room.top() + 40, 8, 60 if not m.window else 20))
        self._label(p, room.right() + 10, room.top() + 70, f"Window {self.n('I', 1, 2)}")
        p.setPen(theme.color("text"))
        p.setFont(theme.font("mono", "xl"))
        p.drawText(room, Qt.AlignCenter, f"{m.temperature:.1f} °C")
        p.setFont(theme.font("mono", "sm"))
        p.drawText(QRectF(room.left(), room.bottom() - 26, room.width(), 20), Qt.AlignCenter,
                   f"setpoint {m.setpoint_knob:.1f} °C   outside {m.outside:.0f} °C")
        # air handler: fan, heater coil, cooler coil
        ah = QRectF(20, 60, 90, 140)
        p.setPen(QPen(theme.color("sim-steel"), 2))
        p.setBrush(theme.color("surface"))
        p.drawRect(ah)
        p.setPen(QPen(theme.color("energized") if m.out(0) else theme.color("sim-steel"), 3))
        cx, cy = ah.center().x(), ah.top() + 30
        for k in range(3):
            a = math.radians(k * 120 + (m.time_s * 720 if m.out(0) else 0))
            p.drawLine(QPointF(cx, cy), QPointF(cx + 18 * math.cos(a), cy + 18 * math.sin(a)))
        p.setPen(QPen(theme.color("lamp-red"), 1 + 4 * m.heater / 100.0))
        p.drawLine(QPointF(ah.left() + 10, ah.top() + 75), QPointF(ah.right() - 10, ah.top() + 75))
        p.setPen(QPen(theme.color("accent"), 1 + 4 * m.cooler / 100.0))
        p.drawLine(QPointF(ah.left() + 10, ah.top() + 105), QPointF(ah.right() - 10, ah.top() + 105))
        p.setPen(QPen(theme.color("sim-steel"), 4))
        p.drawLine(QPointF(ah.right(), ah.center().y()), QPointF(room.left(), ah.center().y()))
        self._label(p, 4, 30, f"Fan {self.n('O', 2, 0)}   Airflow {self.n('I', 1, 3)}")
        self._label(p, 4, 248, f"Heater {m.heater:.0f} % {self.a('O', 0)}")
        self._label(p, 4, 264, f"Cooler {m.cooler:.0f} % {self.a('O', 1)}")
        self._label(p, 4, 280, f"Room {self.a('I', 0)}   Setpoint {self.a('I', 1)}")
        p.end()


class HvacView(_Panel):
    def __init__(self, model: H.HvacModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "On", "on_pressed")
        self.button(1, 1, "Off", "off_pressed", nc=True)
        self.lamp(0, 1, "Heating", "lamp-red")
        self.lamp(1, 2, "Cooling", "lamp-generic")
        self.slider(2, "Setpoint knob (°C)", "setpoint_knob")
        self.slider(3, "Outside (°C)", "outside")
        _check(self, 4, "Window open", "window")
        self.trend = TwoTankTrend(model)
        self.trend.SERIES = ((1, "text-muted", "Setpoint ×2", Qt.DashLine), (2, "sim-product", "Room ×2", Qt.SolidLine),
                             (3, "lamp-red", "Heater", Qt.SolidLine), (4, "accent", "Cooler", Qt.SolidLine))
        self.finish(HvacCanvas(model, io_name, analog_name), self.trend)

    def refresh(self) -> None:
        _sync_checks(self)
        super().refresh()
        self.trend.update()


# -- washing machine -------------------------------------------------------------------------------------------
class WasherCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(560, 300))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        body = QRectF(170, 56, 210, 236)
        p.setPen(QPen(theme.color("sim-steel"), 3))
        p.setBrush(theme.color("surface"))
        p.drawRoundedRect(body, 10, 10)
        c = QPointF(body.center().x(), body.center().y() + 20)
        drum = QRectF(c.x() - 80, c.y() - 80, 160, 160)
        p.setBrush(theme.color("bg"))
        p.drawEllipse(drum)
        h = drum.height() * min(m.water, 100.0) / 100.0               # water in the drum
        p.save()
        p.setClipRect(QRectF(drum.left(), drum.bottom() - h, drum.width(), h))
        p.setBrush(theme.color("sim-product"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(drum)
        p.restore()
        p.setPen(QPen(theme.color("text"), 3))
        for k in range(3):                                              # paddles turn with the drum
            a = math.radians(m.angle + k * 120)
            p.drawLine(QPointF(c.x() + 40 * math.cos(a), c.y() + 40 * math.sin(a)),
                       QPointF(c.x() + 75 * math.cos(a), c.y() + 75 * math.sin(a)))
        p.setPen(QPen(theme.color("energized") if m.locked else theme.color("sim-steel"), 4))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(drum.adjusted(-8, -8, 8, 8) if m.door_closed else drum.adjusted(-8, -8, -150, 8))
        p.setFont(theme.font("mono", "sm"))
        p.setPen(theme.color("text"))
        p.drawText(QPointF(body.left() + 10, body.top() + 20), f"{abs(m.rpm):.0f} rpm  water {m.water:.0f} %")
        self._label(p, 4, 30, f"Lock {self.n('O', 2, 0)}  Locked {self.n('I', 1, 3)}")
        self._label(p, 4, 46, f"Door closed {self.n('I', 1, 2)}")
        self._label(p, 4, 70, f"Fill {self.n('O', 2, 1)}")
        self._label(p, 4, 86, f"Left {self.n('O', 2, 2)}")
        self._label(p, 4, 102, f"Right {self.n('O', 2, 3)}")
        self._label(p, 4, 118, f"Spin {self.n('O', 2, 4)}")
        self._label(p, 4, 134, f"Drain {self.n('O', 2, 5)}")
        self._label(p, 400, 70, f"Water {self.n('I', 1, 4)}")
        self._label(p, 400, 86, f"Full {self.n('I', 1, 5)}")
        self._label(p, 400, 102, f"Stopped {self.n('I', 1, 6)}")
        p.setPen(theme.color("text"))
        p.drawText(QPointF(400, 140), f"Washed L {m.washed_left_s:.0f} s")
        p.drawText(QPointF(400, 156), f"Washed R {m.washed_right_s:.0f} s")
        p.drawText(QPointF(400, 172), f"Spun {m.spun_s:.0f} s")
        p.drawText(QPointF(400, 196), f"Cycles {m.cycles}")
        p.end()


class WasherView(_Panel):
    def __init__(self, model: M.WasherModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Start", "start_pressed")
        self.button(1, 1, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 6, "Done", "lamp-green")
        _check(self, 2, "Door closed", "door_closed")
        self.finish(WasherCanvas(model, io_name, analog_name))

    def refresh(self) -> None:
        _sync_checks(self)
        super().refresh()


VIEWS = {"elevator": ElevatorView, "bottles": BottleView, "sorter": SorterView, "pick_place": PickPlaceView,
         "parking": ParkingView, "pumps": PumpView, "hvac": HvacView, "washer": WasherView}
