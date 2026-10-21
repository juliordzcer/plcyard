"""Reusable painted widgets: ladder glyphs, lamps, sim switches, BCD digits."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from . import theme

CONTACTS = {"XIC", "XIO"}
COILS = {"OTE", "OTL", "OTU"}


def paint_instruction(p: QPainter, rect: QRectF, mnemonic: str, operands: list[str],
                      symbol: str = "", *, energized: bool = False,
                      selected: bool = False, labels: list[str] | None = None,
                      extra: list[tuple[str, str]] | None = None,
                      pins: list[tuple[str, bool]] | None = None,
                      shape: str | None = None, letter: str | None = None) -> None:
    """Draw one instruction centred on the rung wire that crosses rect vertically centred.
    `shape`/`letter` come from the instruction's spec; by default they follow the SLC mnemonic."""
    from ..core.isa import SHAPES
    if shape is None:
        shape, default_letter = SHAPES.get(mnemonic, ("block", ""))
        letter = default_letter if letter is None else letter
    letter = letter or ""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    wire = theme.color("energized") if energized else theme.color("wire")
    pen = QPen(wire, 2)
    unset = any(o in ("", "?") for o in operands) or not operands
    mid_y = rect.top() + 26

    if selected:
        p.setPen(QPen(theme.color("accent"), 2))
        p.setBrush(theme.color("accent-soft"))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), theme.radius("sm"), theme.radius("sm"))

    if shape != "block":
        cx = rect.center().x()
        p.setPen(pen)
        p.drawLine(QPointF(rect.left(), mid_y), QPointF(cx - 9, mid_y))
        p.drawLine(QPointF(cx + 9, mid_y), QPointF(rect.right(), mid_y))
        if energized:
            p.setBrush(theme.color("energized-fill"))
            p.setPen(Qt.NoPen)
            p.drawRect(QRectF(cx - 8, mid_y - 9, 16, 18))
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if shape in ("contact", "contact_nc"):
            p.drawLine(QPointF(cx - 8, mid_y - 9), QPointF(cx - 8, mid_y + 9))
            p.drawLine(QPointF(cx + 8, mid_y - 9), QPointF(cx + 8, mid_y + 9))
            if shape == "contact_nc":
                p.drawLine(QPointF(cx - 6, mid_y + 8), QPointF(cx + 6, mid_y - 8))
            elif letter:
                p.setFont(theme.font("sans", "xs"))
                p.setPen(theme.color("text"))
                p.drawText(QRectF(cx - 6, mid_y - 9, 12, 18), Qt.AlignCenter, letter)
        elif shape == "coil":
            p.drawArc(QRectF(cx - 12, mid_y - 9, 10, 18), 90 * 16, 180 * 16)
            p.drawArc(QRectF(cx + 2, mid_y - 9, 10, 18), -90 * 16, 180 * 16)
            tag = letter
            if tag:
                p.setFont(theme.font("sans", "xs"))
                p.setPen(theme.color("text"))
                p.drawText(QRectF(cx - 6, mid_y - 9, 12, 18), Qt.AlignCenter, tag)
        else:
            p.drawRect(QRectF(cx - 14, mid_y - 9, 28, 18))
            p.setFont(theme.font("sans", "xs"))
            p.setPen(theme.color("text"))
            p.drawText(QRectF(cx - 14, mid_y - 9, 28, 18), Qt.AlignCenter, letter or mnemonic)
        addr = operands[0] if operands else "?"
        p.setFont(theme.font("mono", "sm"))
        p.setPen(theme.color("unset") if unset else theme.color("text"))
        p.drawText(QRectF(rect.left(), rect.top(), rect.width(), 16), Qt.AlignCenter, addr)
        if symbol:
            f = theme.font("sans", "xs")
            p.setFont(f)
            p.setPen(theme.color("text-muted"))
            r = QRectF(rect.left() + 2, mid_y + 11, rect.width() - 4, 14)
            p.drawText(r, Qt.AlignCenter, QFontMetrics(f).elidedText(symbol, Qt.ElideRight, int(r.width())))
    else:
        box = QRectF(rect.left() + 8, rect.top() + 4, rect.width() - 16, rect.height() - 8)
        p.setPen(pen)
        p.drawLine(QPointF(rect.left(), mid_y), QPointF(box.left(), mid_y))
        p.drawLine(QPointF(box.right(), mid_y), QPointF(rect.right(), mid_y))
        p.setBrush(theme.color("energized-fill") if energized else theme.color("bg"))
        p.drawRoundedRect(box, theme.radius("sm"), theme.radius("sm"))
        p.setPen(theme.color("text"))
        p.setFont(theme.font("sans", "md"))
        p.drawText(QRectF(box.left() + 8, box.top() + 4, box.width() - 16, 18),
                   Qt.AlignLeft | Qt.AlignVCenter, mnemonic)
        y = box.top() + 26
        rows = [(labels[i] if labels and i < len(labels) else "", op, False) for i, op in enumerate(operands)]
        for lab, val in (extra or []):
            k = next((i for i, r in enumerate(rows) if r[0] == lab), None)
            if k is None:
                rows.append((lab, val, True))
            else:
                rows[k] = (lab, val, True)      # the operand shows its live value (Logix Accum)
        for lab, op, live in rows:
            p.setFont(theme.font("sans", "sm"))
            p.setPen(theme.color("text-muted"))
            p.drawText(QRectF(box.left() + 8, y, 70, 16), Qt.AlignLeft | Qt.AlignVCenter, lab)
            p.setFont(theme.font("mono", "sm"))
            colour = "unset" if op in ("", "?") else ("energized" if live else "text")
            p.setPen(theme.color(colour))
            beside_pins = bool(pins) and y < box.top() + 4 + 16 * len(pins)     # only rows next to a pin give way
            value_w = box.width() - 86 - (34 if beside_pins else 0)
            p.drawText(QRectF(box.left() + 70, y, value_w + 8, 16),
                       Qt.AlignLeft | Qt.AlignVCenter, op or "?")
            y += 17
        py = box.top() + 4
        for name, on in pins or []:
            r = QRectF(box.right() - 30, py, 26, 14)
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("energized") if on else Qt.transparent)
            p.drawRoundedRect(r, 3, 3)
            p.setFont(theme.font("mono", "xs"))
            p.setPen(theme.color("bg") if on else theme.color("text-muted"))
            p.drawText(r, Qt.AlignCenter, name)
            py += 16
    p.restore()


class InstructionDemo(QWidget):
    def __init__(self, mnemonic, operands, symbol="", labels=None, **state):
        super().__init__()
        self.args = (mnemonic, operands, symbol)
        self.labels = labels
        self.state = state
        block = mnemonic not in CONTACTS | COILS | {"OSR"}
        w = theme.layout("block-w") if block else theme.layout("instr-w") + 40
        h = 42 + 17 * len(operands) if block else 64
        self.setFixedSize(QSize(w, max(h, 52)))

    def paintEvent(self, _):
        p = QPainter(self)
        paint_instruction(p, QRectF(self.rect()), *self.args, labels=self.labels, **self.state)


class Lamp(QWidget):
    def __init__(self, colour: str = "lamp-generic", on: bool = False, diameter: int = 22):
        super().__init__()
        self.colour, self.on = colour, on
        self.setFixedSize(diameter + 8, diameter + 8)
        self.setToolTip(f"{colour} — {'on' if on else 'off'}")

    def set_on(self, on: bool) -> None:
        self.on = on
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        if self.on:
            base = theme.color(self.colour)
            glow = QRadialGradient(r.center(), r.width())
            g = QColor(base)
            g.setAlpha(90)
            glow.setColorAt(0, g)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawEllipse(QRectF(self.rect()))
            p.setBrush(base)
        else:
            p.setBrush(theme.color("lamp-off"))
        p.setPen(QPen(theme.color("rail"), 1.5))
        p.drawEllipse(r)


class SimSwitch(QWidget):
    """Input device: NO/NC, maintained (toggle) or momentary (pushbutton)."""

    changed = Signal(bool)

    def __init__(self, normally_closed=False, momentary=False, pressed=False):
        super().__init__()
        self.nc, self.momentary, self.pressed = normally_closed, momentary, pressed
        self.setFixedSize(56, 34)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)

    @property
    def signal(self) -> bool:
        return self.pressed != self.nc

    def _set(self, v):
        if v != self.pressed:
            self.pressed = v
            self.changed.emit(self.signal)
            self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._set(True if self.momentary else not self.pressed)

    def mouseReleaseEvent(self, e):
        if self.momentary and e.button() == Qt.LeftButton:
            self._set(False)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._set(True if self.momentary else not self.pressed)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and self.momentary and not e.isAutoRepeat():
            self._set(False)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.hasFocus():
            p.setPen(QPen(theme.color("accent"), 2))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)
        y = 20
        pen = QPen(theme.color("rail"), 2)
        p.setPen(pen)
        p.drawLine(4, y, 14, y)
        p.drawLine(38, y, 44, y)
        p.setBrush(theme.color("rail"))
        p.drawEllipse(QPointF(14, y), 2.5, 2.5)
        p.drawEllipse(QPointF(38, y), 2.5, 2.5)
        if self.momentary:
            bar_y = y - 3 if self.pressed else y - 9
            p.drawLine(QPointF(12, bar_y), QPointF(40, bar_y))
            p.drawLine(QPointF(26, bar_y), QPointF(26, bar_y - 6))
        else:
            end = QPointF(38, y - 2) if self.pressed else QPointF(36, y - 12)
            p.drawLine(QPointF(14, y), end)
        p.setBrush(theme.color("energized") if self.signal else theme.color("lamp-off"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(50, y), 4, 4)
        p.setPen(theme.color("text-muted"))
        p.setFont(theme.font("sans", "xs"))
        p.drawText(QRectF(0, 0, 56, 12), Qt.AlignLeft, "NC" if self.nc else "NO")


_SEG = {0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg", 5: "acdfg",
        6: "acdefg", 7: "abc", 8: "abcdefg", 9: "abcdfg"}


class DigitDisplay(QWidget):
    """4-digit seven-segment display of a packed-BCD word (O:6)."""

    def __init__(self, word: int = 0, digits: int = 4):
        super().__init__()
        self.word, self.digits = word, digits
        self.setFixedSize(30 * digits + 12, 52)

    def set_word(self, word: int) -> None:
        self.word = word & 0xFFFF
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(theme.color("display-bg"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(self.rect()), 6, 6)
        on, off = theme.color("lamp-red"), QColor(theme.color("lamp-red"))
        off.setAlpha(40)
        for i in range(self.digits):
            nib = (self.word >> (4 * (self.digits - 1 - i))) & 0xF
            segs = _SEG.get(nib, "g")
            x0, y0, w, h = 10 + i * 30, 8, 18, 36
            pts = {"a": (x0, y0, x0 + w, y0), "b": (x0 + w, y0, x0 + w, y0 + h / 2),
                   "c": (x0 + w, y0 + h / 2, x0 + w, y0 + h), "d": (x0, y0 + h, x0 + w, y0 + h),
                   "e": (x0, y0 + h / 2, x0, y0 + h), "f": (x0, y0, x0, y0 + h / 2),
                   "g": (x0, y0 + h / 2, x0 + w, y0 + h / 2)}
            for s, (a, b, c, d) in pts.items():
                p.setPen(QPen(on if s in segs else off, 3.5, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(a, b), QPointF(c, d))


class ModeSelector(QWidget):
    """Segmented PGM | STEP | RUN control."""

    modeChanged = Signal(str)

    def __init__(self, current: str = "PGM"):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        for name in ("PGM", "STEP", "RUN"):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setChecked(name == current)
            b.setProperty("variant", "primary" if name == current else "")
            b.toggled.connect(lambda on, n=name, btn=b: self._toggled(on, n, btn))
            self.group.addButton(b)
            lay.addWidget(b)

    def set_mode(self, name: str) -> None:
        for b in self.group.buttons():
            if b.text() == name and not b.isChecked():
                b.setChecked(True)

    def _toggled(self, on, name, btn):
        btn.setProperty("variant", "primary" if on else "")
        btn.style().unpolish(btn)
        btn.style().polish(btn)
        if on:
            self.modeChanged.emit(name)
