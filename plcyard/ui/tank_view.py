"""View for the tank level simulation: the tank, its controls and a trend of setpoint, level and
valve output. Own vector drawing, colours from tokens."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from ..sims import tank as K
from . import theme
from .io_drag import Hotspots, attach
from .primitives import Lamp, SimSwitch
from .sim_views import _EventBar, _mono, slc_name


def slc_analog(direction: str, channel: int) -> str:
    return {("I", 0): "I:7", ("I", 1): "I:6", ("O", 0): "O:7"}[(direction, channel)]


class TankCanvas(Hotspots, QWidget):
    def __init__(self, model: K.TankModel, io_name=slc_name, analog_name=slc_analog):
        super().__init__()
        self.model, self.n, self.a = model, io_name, analog_name
        self.setMinimumSize(320, 220)
        self.setAccessibleName("Tank level process")
        self.setMouseTracking(True)

    def paintEvent(self, _):
        self._hotspots_reset()
        m = self.model
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("sim-bg"))
        s = min(self.width() / 460, self.height() / 300)
        p.scale(s, s)
        steel, water = theme.color("sim-steel"), theme.color("sim-product")
        tank = QRectF(120, 80, 120, 170)
        # inlet pipe with pump and valve; labels on their own lines above the tank
        pipe_on = m.pump or m.valve > 0.5
        p.setPen(QPen(water if pipe_on else steel, 6))
        p.drawLine(QPointF(10, 60), QPointF(180, 60))
        p.drawLine(QPointF(180, 60), QPointF(180, 84))
        p.setPen(QPen(steel, 2))
        p.setBrush(theme.color("energized") if m.pump else theme.color("bg"))
        p.drawEllipse(QPointF(36, 60), 10, 10)
        p.setBrush(theme.color("bg"))
        p.drawPolygon([QPointF(96, 52), QPointF(96, 68), QPointF(112, 60)])
        p.drawPolygon([QPointF(128, 52), QPointF(128, 68), QPointF(112, 60)])
        self._label(p, 10, 16, f"Pump {self.n('O', 2, 0)}")
        self._label(p, 10, 32, f"Valve {m.valve:.0f} %  {self.a('O', 0)}")
        # level
        h = tank.height() * m.level / 100.0
        p.setPen(Qt.NoPen)
        p.setBrush(water)
        p.drawRect(QRectF(tank.left(), tank.bottom() - h, tank.width(), h))
        sp_y = tank.bottom() - tank.height() * m.setpoint_knob / 100.0
        p.setPen(QPen(theme.color("text-muted"), 1.5, Qt.DashLine))
        p.drawLine(QPointF(tank.left() - 10, sp_y), QPointF(tank.right() + 10, sp_y))
        p.setPen(QPen(steel, 4))
        p.setBrush(Qt.NoBrush)
        path = QPainterPath(QPointF(tank.left(), tank.top()))
        path.lineTo(tank.left(), tank.bottom())
        path.lineTo(tank.right(), tank.bottom())
        path.lineTo(tank.right(), tank.top())
        p.drawPath(path)
        p.setFont(theme.font("mono", "md"))
        p.setPen(theme.color("text"))
        p.drawText(QRectF(tank.left(), tank.top() + 4, tank.width(), 20), Qt.AlignCenter, f"{m.level:.1f} %")
        # level switches on the right wall
        for lvl, on, label in ((K.HIGH, m.level >= K.HIGH, f"High {self.n('I', 1, 2)}"),
                               (K.LOW, m.level <= K.LOW, f"Low {self.n('I', 1, 3)}")):
            y = tank.bottom() - tank.height() * lvl / 100.0
            p.setPen(QPen(steel, 2))
            p.setBrush(theme.color("energized") if on else theme.color("bg"))
            p.drawEllipse(QPointF(tank.right() + 10, y), 5, 5)
            self._label(p, tank.right() + 20, y + 4, label)
        # outlet
        p.setPen(QPen(water if m.outlet > 0 and m.level > 0 else steel, 6))
        p.drawLine(QPointF(tank.right(), tank.bottom() - 8), QPointF(450, tank.bottom() - 8))
        self._label(p, 350, tank.bottom() + 12, f"Outlet {m.outlet:.0f} %")
        self._label(p, tank.left(), tank.bottom() + 20, f"Level {self.a('I', 0)}")
        self._label(p, tank.left(), tank.bottom() + 36, f"Setpoint knob {self.a('I', 1)} (dashed line)")
        p.end()

    def _label(self, p, x, y, text):
        p.setFont(theme.font("mono", "xs"))
        p.setPen(theme.color("text-muted"))
        self.label(p, QPointF(x, y), text)


class TrendChart(QWidget):
    """Last minute of setpoint (dashed), level and valve output, 0-100 %."""
    WINDOW_S = 60.0

    def __init__(self, model: K.TankModel):
        super().__init__()
        self.model = model
        self.setMinimumHeight(140)
        self.setAccessibleName("Trend of setpoint, level and valve output")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("bg"))
        r = QRectF(self.rect()).adjusted(36, 8, -8, -22)
        p.setPen(QPen(theme.color("border"), 1))
        p.setFont(theme.font("mono", "xs"))
        for v in (0, 50, 100):
            y = r.bottom() - r.height() * v / 100
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(theme.color("text-muted"))
            p.drawText(QRectF(0, y - 7, 32, 14), Qt.AlignRight | Qt.AlignVCenter, f"{v}")
            p.setPen(QPen(theme.color("border"), 1))
        pts = list(self.model.trend)
        if len(pts) >= 2:
            t1 = pts[-1][0]
            t0 = t1 - self.WINDOW_S
            pts = [q for q in pts if q[0] >= t0]
            series = ((1, theme.color("text-muted"), Qt.DashLine), (3, theme.color("warning"), Qt.SolidLine),
                      (2, theme.color("sim-product"), Qt.SolidLine))
            for idx, colour, style in series:
                path = QPainterPath()
                for k, q in enumerate(pts):
                    x = r.left() + r.width() * (q[0] - t0) / self.WINDOW_S
                    y = r.bottom() - r.height() * min(max(q[idx], 0), 100) / 100
                    path.moveTo(x, y) if k == 0 else path.lineTo(x, y)
                p.setPen(QPen(colour, 2, style))
                p.setBrush(Qt.NoBrush)
                p.drawPath(path)
        x = r.left()
        for name, colour in (("Setpoint", "text-muted"), ("Level", "sim-product"), ("Valve", "warning")):
            p.setPen(QPen(theme.color(colour), 3))
            p.drawLine(QPointF(x, r.bottom() + 14), QPointF(x + 14, r.bottom() + 14))
            p.setPen(theme.color("text"))
            p.drawText(QPointF(x + 18, r.bottom() + 18), name)
            x += 90
        p.end()


class TankView(QWidget):
    reset_requested = Signal()

    def __init__(self, model: K.TankModel, io_name=slc_name, analog_name=slc_analog):
        super().__init__()
        self.model, self.n, self.a = model, io_name, analog_name
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        panel = QFrame()
        panel.setFrameShape(QFrame.StyledPanel)
        g = QGridLayout(panel)
        self.start = SimSwitch(normally_closed=False, momentary=True)
        self.stop = SimSwitch(normally_closed=True, momentary=True)
        self.start.changed.connect(lambda _s: setattr(model, "start_pressed", self.start.pressed))
        self.stop.changed.connect(lambda _s: setattr(model, "stop_pressed", self.stop.pressed))
        for row, (w, t) in enumerate(((self.start, f"Start {self.n('I', 1, 0)}"),
                                      (self.stop, f"Stop {self.n('I', 1, 1)} (NC)"))):
            w.setToolTip(t)
            w.setAccessibleName(t)
            w.address = self.n("I", 1, row)
            g.addWidget(w, row, 0)
            g.addWidget(attach(_mono(t), w.address), row, 1)
        self.lamps = {}
        for row, (bit, name, tone) in enumerate(((1, f"Run {self.n('O', 2, 1)}", "lamp-green"),
                                                  (2, f"High alarm {self.n('O', 2, 2)}", "lamp-red"))):
            lamp = attach(Lamp(tone), self.n("O", 2, bit))
            self.lamps[bit] = lamp
            g.addWidget(lamp, row, 2)
            g.addWidget(attach(_mono(name), self.n("O", 2, bit)), row, 3)
        self.sp = self._slider(g, 2, f"Setpoint knob {self.a('I', 1)}", model.setpoint_knob,
                               lambda v: setattr(model, "setpoint_knob", float(v)))
        self.outlet = self._slider(g, 3, "Outlet opening (disturbance)", model.outlet,
                                   lambda v: setattr(model, "outlet", float(v)))
        top = QHBoxLayout()
        top.addWidget(panel)
        top.addStretch(1)
        lay.addLayout(top)
        self.canvas = TankCanvas(model, io_name, analog_name)
        lay.addWidget(self.canvas, 1)
        self.trend = TrendChart(model)
        lay.addWidget(self.trend)
        self.events = _EventBar()
        self.events.reset.connect(self.reset_requested.emit)
        lay.addWidget(self.events)

    def _slider(self, g, row, text, value, on_change) -> QSlider:
        s = QSlider(Qt.Horizontal)
        s.setRange(0, 100)
        s.setValue(int(value))
        s.setAccessibleName(text)
        s.setToolTip(text)
        label = _mono(f"{text}: {int(value)} %")
        s.valueChanged.connect(on_change)
        s.valueChanged.connect(lambda v, l=label, t=text: l.setText(f"{t}: {v} %"))
        g.addWidget(label, row, 0, 1, 2)
        g.addWidget(s, row, 2, 1, 2)
        return s

    def refresh(self) -> None:
        for slider, value in ((self.sp, self.model.setpoint_knob), (self.outlet, self.model.outlet)):
            if slider.value() != int(value) and not slider.isSliderDown():
                slider.setValue(int(value))
        for bit, lamp in self.lamps.items():
            if lamp.on != self.model.lamp(bit):
                lamp.set_on(self.model.lamp(bit))
        self.events.show_events(["The tank overflowed"] if self.model.overflowed > 0 else [])
        self.canvas.update()
        self.trend.update()
