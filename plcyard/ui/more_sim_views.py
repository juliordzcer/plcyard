"""Views for the two-tank process, the garage door and the batch mixer: controls on top, an animated
drawing below (labels with an address can be dragged onto the program), what went wrong at the
bottom."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QCheckBox, QFrame, QGridLayout, QHBoxLayout, QSlider, QVBoxLayout, QWidget

from ..sims import garage as G
from ..sims import mixer as X
from ..sims import two_tanks as W
from . import theme
from .io_drag import Hotspots, attach
from .primitives import Lamp, SimSwitch
from .sim_views import _EventBar, _mono, default_name
from .tank_view import default_analog


class _Canvas(Hotspots, QWidget):
    def __init__(self, model, io_name, analog_name, size=(460, 300)):
        super().__init__()
        self.model, self.n, self.a = model, io_name, analog_name
        self.base = size
        self.setMinimumSize(320, 220)
        self.setMouseTracking(True)

    def begin(self) -> QPainter:
        self._hotspots_reset()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("sim-bg"))
        s = min(self.width() / self.base[0], self.height() / self.base[1])
        p.scale(s, s)
        self._scale = s
        return p

    def _label(self, p, x, y, text):
        p.setFont(theme.font("mono", "xs"))
        p.setPen(theme.color("text-muted"))
        self.label(p, QPointF(x, y), text)

    def label(self, p, at, text):
        """Hotspots are kept in widget coordinates; the drawing is scaled (and maybe shifted)."""
        p.drawText(at, text)
        r = p.fontMetrics().boundingRect(text)
        box = p.transform().mapRect(QRectF(at.x() + r.x(), at.y() + r.y(), r.width(), r.height()))
        self.add_hotspot(box, text)

    @staticmethod
    def tank(p, r: QRectF, level: float, colour) -> None:
        h = r.height() * min(max(level, 0.0), 100.0) / 100.0
        p.setPen(Qt.NoPen)
        p.setBrush(colour)
        p.drawRect(QRectF(r.left(), r.bottom() - h, r.width(), h))
        p.setPen(QPen(theme.color("sim-steel"), 4))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(r.left(), r.top()))
        path.lineTo(r.left(), r.bottom())
        path.lineTo(r.right(), r.bottom())
        path.lineTo(r.right(), r.top())
        p.drawPath(path)

    @staticmethod
    def valve(p, at: QPointF, opening: float) -> None:
        p.setPen(QPen(theme.color("sim-steel"), 2))
        p.setBrush(theme.color("energized") if opening > 0.5 else theme.color("bg"))
        x, y = at.x(), at.y()
        p.drawPolygon([QPointF(x - 9, y - 7), QPointF(x - 9, y + 7), QPointF(x, y)])
        p.drawPolygon([QPointF(x + 9, y - 7), QPointF(x + 9, y + 7), QPointF(x, y)])

    @staticmethod
    def switch(p, at: QPointF, on: bool) -> None:
        p.setPen(QPen(theme.color("sim-steel"), 2))
        p.setBrush(theme.color("energized") if on else theme.color("bg"))
        p.drawEllipse(at, 5, 5)


class _Panel(QWidget):
    """Buttons, lamps and sliders of a simulation, with draggable addresses."""
    reset_requested = Signal()

    def __init__(self, model, io_name, analog_name):
        super().__init__()
        self.model, self.n, self.a = model, io_name, analog_name
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(12, 12, 12, 12)
        self.panel = QFrame()
        self.panel.setFrameShape(QFrame.StyledPanel)
        self.grid = QGridLayout(self.panel)
        top = QHBoxLayout()
        top.addWidget(self.panel)
        top.addStretch(1)
        self.lay.addLayout(top)
        self.lamps: dict[int, Lamp] = {}
        self.sliders: list[tuple[QSlider, str]] = []
        self.events = _EventBar()
        self.events.reset.connect(self.reset_requested.emit)

    def button(self, row, bit, text, attr, nc=False):
        w = SimSwitch(normally_closed=nc, momentary=True)
        w.changed.connect(lambda _s, a=attr, sw=w: setattr(self.model, a, sw.pressed))
        label = f"{text} {self.n('I', 1, bit)}" + (" (NC)" if nc else "")
        w.setToolTip(label)
        w.setAccessibleName(label)
        w.address = self.n("I", 1, bit)
        self.grid.addWidget(w, row, 0)
        self.grid.addWidget(attach(_mono(label), w.address), row, 1)

    def lamp(self, row, bit, text, tone):
        lamp = attach(Lamp(tone), self.n("O", 2, bit))
        self.lamps[bit] = lamp
        self.grid.addWidget(lamp, row, 2)
        self.grid.addWidget(attach(_mono(f"{text} {self.n('O', 2, bit)}"), self.n("O", 2, bit)), row, 3)

    def slider(self, row, text, attr):
        s = QSlider(Qt.Horizontal)
        s.setRange(0, 100)
        s.setValue(int(getattr(self.model, attr)))
        s.setAccessibleName(text)
        label = _mono(f"{text}: {int(getattr(self.model, attr))} %")
        s.valueChanged.connect(lambda v, a=attr: setattr(self.model, a, float(v)))
        s.valueChanged.connect(lambda v, l=label, t=text: l.setText(f"{t}: {v} %"))
        self.grid.addWidget(label, row, 0, 1, 2)
        self.grid.addWidget(s, row, 2, 1, 2)
        self.sliders.append((s, attr))

    def finish(self, canvas: QWidget, *extra: QWidget) -> None:
        self.canvas = canvas
        self.lay.addWidget(canvas, 1)
        for w in extra:
            self.lay.addWidget(w)
        self.lay.addWidget(self.events)

    def refresh(self) -> None:
        for s, attr in self.sliders:
            v = int(getattr(self.model, attr))
            if s.value() != v and not s.isSliderDown():
                s.setValue(v)
        for bit, lamp in self.lamps.items():
            on = self.model.lamp(bit)
            if lamp.on != on:
                lamp.set_on(on)
        self.events.show_events(self.model.events)
        self.canvas.update()


# -- two tanks --------------------------------------------------------------------------------------------
class TwoTankCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(600, 400))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        steel, water = theme.color("sim-steel"), theme.color("sim-product")
        t1, t2 = QRectF(70, 90, 110, 120), QRectF(280, 210, 120, 120)
        flowing = m.pump or m.inlet > 0.5
        p.setPen(QPen(water if flowing else steel, 6))
        p.drawLine(QPointF(10, 60), QPointF(125, 60))
        p.drawLine(QPointF(125, 60), QPointF(125, 94))
        self.valve(p, QPointF(80, 60), m.inlet)
        p.setPen(QPen(steel, 2))
        p.setBrush(theme.color("energized") if m.pump else theme.color("bg"))
        p.drawEllipse(QPointF(30, 60), 9, 9)
        self._label(p, 8, 20, f"Pump {self.n('O', 2, 0)}")
        self._label(p, 8, 36, f"Inlet {m.inlet:.0f} %  {self.a('O', 0)}")
        self.tank(p, t1, m.level1, water)
        self.tank(p, t2, m.level2, water)
        sp_y = t2.bottom() - t2.height() * m.setpoint_knob / 100.0
        p.setPen(QPen(theme.color("text-muted"), 1.5, Qt.DashLine))
        p.drawLine(QPointF(t2.left() - 8, sp_y), QPointF(t2.right() + 8, sp_y))
        # transfer pipe from the bottom of tank 1 into the top of tank 2
        between = m.transfer > 0.5 and m.level1 > 0
        p.setPen(QPen(water if between else steel, 6))
        y = t1.bottom() - 8
        p.drawLine(QPointF(t1.right(), y), QPointF(320, y))
        p.drawLine(QPointF(320, y), QPointF(320, t2.top() + 4))
        self.valve(p, QPointF(240, y), m.transfer)
        self._label(p, 196, y - 14, f"Transfer {m.transfer:.0f} %")
        self._label(p, 196, y - 28, self.a("O", 1))
        # outlet of tank 2: down from the bottom, then right
        p.setPen(QPen(water if m.outlet > 0 and m.level2 > 0 else steel, 6))
        p.drawLine(QPointF(t2.left() + 30, t2.bottom()), QPointF(t2.left() + 30, 370))
        p.drawLine(QPointF(t2.left() + 30, 370), QPointF(590, 370))
        self._label(p, 470, 362, f"Outlet {m.outlet:.0f} %")
        p.setFont(theme.font("mono", "md"))
        p.setPen(theme.color("text"))
        for r, lv in ((t1, m.level1), (t2, m.level2)):
            p.drawText(QRectF(r.left(), r.top() + 4, r.width(), 20), Qt.AlignCenter, f"{lv:.1f} %")
        for r, lvl, on, label in ((t1, W.HIGH, m.level1 >= W.HIGH, f"High {self.n('I', 1, 2)}"),
                                  (t2, W.HIGH, m.level2 >= W.HIGH, f"High {self.n('I', 1, 3)}"),
                                  (t2, W.LOW, m.level2 <= W.LOW, f"Low {self.n('I', 1, 4)}")):
            yy = r.bottom() - r.height() * lvl / 100.0
            self.switch(p, QPointF(r.right() + 10, yy), on)
            self._label(p, r.right() + 20, yy + 4, label)
        self._label(p, t1.left(), t1.bottom() + 40, f"Tank 1  {self.a('I', 0)}")
        self._label(p, t2.right() + 20, t2.top() + 50, f"Tank 2  {self.a('I', 1)}")
        self._label(p, t2.right() + 20, t2.top() + 66, f"Setpoint {self.a('I', 2)}")
        self._label(p, t2.right() + 20, t2.top() + 80, "(dashed line)")
        p.end()


class TwoTankTrend(QWidget):
    WINDOW_S = 60.0
    SERIES = ((1, "text-muted", "Setpoint", Qt.DashLine), (2, "accent", "Tank 1", Qt.SolidLine),
              (3, "sim-product", "Tank 2", Qt.SolidLine), (4, "warning", "Inlet", Qt.SolidLine),
              (5, "success", "Transfer", Qt.SolidLine))

    def __init__(self, model):
        super().__init__()
        self.model = model
        self.setMinimumHeight(140)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("bg"))
        r = QRectF(self.rect()).adjusted(36, 8, -8, -22)
        p.setFont(theme.font("mono", "xs"))
        for v in (0, 50, 100):
            y = r.bottom() - r.height() * v / 100
            p.setPen(QPen(theme.color("border"), 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(theme.color("text-muted"))
            p.drawText(QRectF(0, y - 7, 32, 14), Qt.AlignRight | Qt.AlignVCenter, f"{v}")
        pts = list(self.model.trend)
        if len(pts) >= 2:
            t0 = pts[-1][0] - self.WINDOW_S
            pts = [q for q in pts if q[0] >= t0]
            for idx, colour, _, style in self.SERIES:
                path = QPainterPath()
                for k, q in enumerate(pts):
                    x = r.left() + r.width() * (q[0] - t0) / self.WINDOW_S
                    y = r.bottom() - r.height() * min(max(q[idx], 0), 100) / 100
                    path.moveTo(x, y) if k == 0 else path.lineTo(x, y)
                p.setPen(QPen(theme.color(colour), 2, style))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
        x = r.left()
        for _, colour, name, _s in self.SERIES:
            p.setPen(QPen(theme.color(colour), 3))
            p.drawLine(QPointF(x, r.bottom() + 14), QPointF(x + 14, r.bottom() + 14))
            p.setPen(theme.color("text"))
            p.drawText(QPointF(x + 18, r.bottom() + 18), name)
            x += 80
        p.end()


class TwoTankView(_Panel):
    def __init__(self, model: W.TwoTankModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Start", "start_pressed")
        self.button(1, 1, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 1, "Run", "lamp-green")
        self.lamp(1, 2, "Alarm", "lamp-red")
        self.slider(2, f"Setpoint knob {self.a('I', 2)}", "setpoint_knob")
        self.slider(3, "Outlet of tank 2 (disturbance)", "outlet")
        self.trend = TwoTankTrend(model)
        self.finish(TwoTankCanvas(model, io_name, analog_name), self.trend)

    def refresh(self) -> None:
        super().refresh()
        self.trend.update()


# -- garage door ---------------------------------------------------------------------------------------------
class GarageCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(620, 300))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        p.translate(70, 0)
        steel = theme.color("sim-steel")
        frame = QRectF(110, 60, 240, 190)
        # building and the opening
        p.setPen(QPen(steel, 3))
        p.setBrush(theme.color("surface"))
        p.drawRect(QRectF(80, 30, 300, 220))
        p.setBrush(theme.color("bg"))
        p.drawRect(frame)
        if m.car:                                       # a car in the doorway
            body = QRectF(150, 190, 160, 40)
            p.setPen(QPen(theme.color("text"), 2))
            p.setBrush(theme.color("accent-soft"))
            p.drawRoundedRect(body, 10, 10)
            p.drawRoundedRect(QRectF(185, 168, 90, 28), 8, 8)
            p.setBrush(theme.color("text"))
            p.drawEllipse(QPointF(180, 232), 11, 11)
            p.drawEllipse(QPointF(280, 232), 11, 11)
        # the door: panels that roll up into the ceiling
        bottom = frame.top() + frame.height() * (100.0 - m.position) / 100.0
        ph = frame.height() / 5
        p.setPen(QPen(steel, 1.5))
        p.setBrush(QColor(theme.color("sim-steel")).lighter(160))
        for k in range(5):
            r_bottom = bottom - k * ph
            if r_bottom <= frame.top():
                break
            p.drawRect(QRectF(frame.left() + 2, max(frame.top(), r_bottom - ph), frame.width() - 4,
                              r_bottom - max(frame.top(), r_bottom - ph)))
        # photo-eye beam across the doorway, low
        beam_y = frame.bottom() - 18
        p.setPen(QPen(theme.color("danger") if m.car else theme.color("success"), 2, Qt.DashLine))
        p.drawLine(QPointF(frame.left() + 4, beam_y), QPointF(frame.right() - 4, beam_y))
        self._label(p, -66, beam_y - 6, "Photo-eye")
        self._label(p, -66, beam_y + 8, self.n("I", 1, 5))
        # limit switches
        self.switch(p, QPointF(frame.right() + 14, frame.top() + 6), m.position >= 100.0)
        self._label(p, frame.right() + 24, frame.top() + 10, f"Open {self.n('I', 1, 3)}")
        self.switch(p, QPointF(frame.right() + 14, frame.bottom() - 6), m.position <= 0.0)
        self._label(p, frame.right() + 24, frame.bottom() - 2, f"Closed {self.n('I', 1, 4)}")
        # motor and warning light
        p.setPen(QPen(steel, 2))
        p.setBrush(theme.color("energized") if m.up or m.down else theme.color("bg"))
        p.drawRect(QRectF(200, 36, 60, 18))
        arrow = "▲" if m.up else ("▼" if m.down else "■")
        p.setPen(theme.color("text"))
        p.setFont(theme.font("sans", "sm"))
        p.drawText(QRectF(200, 36, 60, 18), Qt.AlignCenter, arrow)
        self._label(p, 120, 22, f"Up {self.n('O', 2, 0)}  Down {self.n('O', 2, 1)}")
        p.setPen(QPen(steel, 2))
        p.setBrush(theme.color("lamp-amber") if m.lamp(2) else theme.color("lamp-off"))
        p.drawEllipse(QPointF(-40, 50), 10, 10)
        self._label(p, -66, 76, f"Warn {self.n('O', 2, 2)}")
        p.setBrush(theme.color("lamp-generic") if m.lamp(3) else theme.color("lamp-off"))
        p.drawEllipse(QPointF(-40, 120), 10, 10)
        self._label(p, -66, 146, f"Light {self.n('O', 2, 3)}")
        p.setFont(theme.font("mono", "md"))
        p.setPen(theme.color("text"))
        p.drawText(QRectF(110, 254, 240, 20), Qt.AlignCenter, f"Door {m.position:.0f} % open")
        p.end()


class GarageView(_Panel):
    def __init__(self, model: G.GarageModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Open", "open_pressed")
        self.button(1, 1, "Close", "close_pressed")
        self.button(2, 2, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 2, "Warning", "lamp-amber")
        self.lamp(1, 3, "Light", "lamp-generic")
        car = QCheckBox("Car in the doorway")
        car.toggled.connect(lambda on: setattr(model, "car", on))
        self.grid.addWidget(car, 3, 0, 1, 4)
        self.car_box = car
        self.finish(GarageCanvas(model, io_name, analog_name))

    def refresh(self) -> None:
        if self.car_box.isChecked() != self.model.car:
            self.car_box.setChecked(self.model.car)
        super().refresh()


# -- batch mixer ---------------------------------------------------------------------------------------------
class MixerCanvas(_Canvas):
    def __init__(self, *a):
        super().__init__(*a, size=(600, 330))

    def paintEvent(self, _):
        m = self.model
        p = self.begin()
        steel = theme.color("sim-steel")
        tank = QRectF(150, 80, 150, 170)
        col_a, col_b = QColor(theme.color("accent")), QColor(theme.color("warning"))
        level = m.level
        if level > 0:                                    # the colour shows the mix
            share = m.a / level
            mix = QColor.fromRgbF(col_a.redF() * share + col_b.redF() * (1 - share),
                                  col_a.greenF() * share + col_b.greenF() * (1 - share),
                                  col_a.blueF() * share + col_b.blueF() * (1 - share), 0.85)
        else:
            mix = col_a
        self.tank(p, tank, level, mix)
        for k, (on, colour, x, text) in enumerate(((m.out(0), col_a, 175, f"A {self.n('O', 2, 0)}"),
                                                   (m.out(1), col_b, 275, f"B {self.n('O', 2, 1)}"))):
            p.setPen(QPen(colour if on else steel, 6))
            p.drawLine(QPointF(x, 30), QPointF(x, tank.top() + 4))
            self.valve(p, QPointF(x, 52), 100.0 if on else 0.0)
            self._label(p, 10 if k == 0 else x + 16, 20 if k == 0 else 26, text)
        # mixer shaft and blades
        cx = tank.center().x()
        p.setPen(QPen(steel, 3))
        p.drawLine(QPointF(cx, 60), QPointF(cx, tank.bottom() - 30))
        p.setBrush(theme.color("energized") if m.out(2) else theme.color("bg"))
        p.drawRect(QRectF(cx - 16, 48, 32, 16))
        a = math.radians(m.angle)
        dx = 34 * math.cos(a)
        p.setPen(QPen(steel, 4))
        p.drawLine(QPointF(cx - dx, tank.bottom() - 30), QPointF(cx + dx, tank.bottom() - 30))
        self._label(p, 10, 46, f"Mixer {self.n('O', 2, 2)}")
        # heater coil
        p.setPen(QPen(theme.color("lamp-red") if m.out(3) else steel, 3))
        path = QPainterPath(QPointF(tank.left() + 12, tank.bottom() - 10))
        for k in range(8):
            path.lineTo(tank.left() + 12 + 16 * k + 8, tank.bottom() - (4 if k % 2 else 16))
        p.drawPath(path)
        self._label(p, tank.left(), tank.bottom() + 16, f"Heater {self.n('O', 2, 3)}")
        # drain
        p.setPen(QPen(mix if m.out(4) and level > 0 else steel, 6))
        p.drawLine(QPointF(cx, tank.bottom()), QPointF(cx, 285))
        p.drawLine(QPointF(cx, 285), QPointF(440, 285))
        self.valve(p, QPointF(cx + 60, 285), 100.0 if m.out(4) else 0.0)
        self._label(p, cx + 80, 278, f"Drain {self.n('O', 2, 4)}")
        # level switches and thermometer
        for lvl, bit, name in ((X.HIGH, 4, "High"), (X.MID, 3, "Mid"), (X.LOW, 2, "Low")):
            y = tank.bottom() - tank.height() * lvl / 100.0
            self.switch(p, QPointF(tank.right() + 10, y), level >= lvl)
            self._label(p, tank.right() + 20, y + 4, f"{name} {self.n('I', 1, bit)}")
        th = QRectF(40, 100, 16, 130)
        p.setPen(QPen(steel, 2))
        p.setBrush(theme.color("bg"))
        p.drawRoundedRect(th, 8, 8)
        h = th.height() * min(max(m.temperature, 0.0), 100.0) / 100.0
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("lamp-red"))
        p.drawRoundedRect(QRectF(th.left() + 4, th.bottom() - h, th.width() - 8, h), 4, 4)
        p.setFont(theme.font("mono", "md"))
        p.setPen(theme.color("text"))
        p.drawText(QRectF(0, 236, 100, 20), Qt.AlignCenter, f"{m.temperature:.1f} °C")
        self._label(p, 4, 300, f"Temp {self.a('I', 0)}")
        p.drawText(QRectF(tank.left(), tank.top() + 4, tank.width(), 20), Qt.AlignCenter, f"{level:.0f} %")
        good = sum(b.good for b in m.batches)
        p.setFont(theme.font("mono", "sm"))
        p.setPen(theme.color("text"))
        p.drawText(QPointF(390, 320), f"Batches {len(m.batches)}, good {good}")
        p.end()


class MixerView(_Panel):
    def __init__(self, model: X.MixerModel, io_name=default_name, analog_name=default_analog):
        super().__init__(model, io_name, analog_name)
        self.button(0, 0, "Start", "start_pressed")
        self.button(1, 1, "Stop", "stop_pressed", nc=True)
        self.lamp(0, 5, "Batch done", "lamp-green")
        self.finish(MixerCanvas(model, io_name, analog_name))
