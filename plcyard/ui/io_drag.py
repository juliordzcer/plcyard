"""Drag an input or output from a simulation onto the ladder: dropped on an
instruction it becomes the operand, dropped on a rung it adds a contact (input) or a coil (output)."""

from __future__ import annotations

import re

from PySide6.QtCore import QEvent, QMimeData, QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QApplication, QWidget

MIME = "application/x-plcyard-address"
_ADDRESS = re.compile(r"^(?:[IO]:\d+(?:/\d+)?|Local:\d+:[IO]\.(?:Data\.\d+|Ch\d+Data)|%[IQ]W?\d+(?:\.\d)?)$")


def direction_of(address: str) -> str:
    """"I" for an input, "O" for an output, in any controller's address style."""
    a = address.upper()
    if a.startswith("%Q") or a.startswith("O:") or ":O." in a:
        return "O"
    return "I"


def is_bit(address: str) -> bool:
    return "/" in address or ".DATA." in address.upper() or bool(re.match(r"^%[IQ]\d+\.\d$", address))


def is_address(text: str) -> bool:
    return bool(_ADDRESS.match(text))


def start_drag(source: QWidget, address: str) -> None:
    drag = QDrag(source)
    mime = QMimeData()
    mime.setData(MIME, address.encode())
    mime.setText(address)
    drag.setMimeData(mime)
    drag.exec(Qt.CopyAction)


class Draggable(QObject):
    """Makes a label or a lamp draggable as its I/O address."""

    def __init__(self, widget: QWidget, address: str):
        super().__init__(widget)
        self.address, self._press = address, None
        widget.installEventFilter(self)
        widget.setCursor(Qt.OpenHandCursor)
        tip = widget.toolTip()
        widget.setToolTip((tip + "\n" if tip else "") + f"Drag {address} onto the ladder")

    def eventFilter(self, obj, e):
        if e.type() == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
            self._press = e.position()
        elif e.type() == QEvent.MouseMove and self._press is not None and e.buttons() & Qt.LeftButton:
            if (e.position() - self._press).manhattanLength() >= QApplication.startDragDistance():
                self._press = None
                start_drag(obj, self.address)
                return True
        elif e.type() == QEvent.MouseButtonRelease:
            self._press = None
        return False


def attach(widget: QWidget, address: str) -> QWidget:
    Draggable(widget, address)
    return widget


class Hotspots:
    """For simulation canvases that paint their labels: remember where each address label is and
    start a drag from it."""

    def _hotspots_reset(self) -> None:
        self._spots: list[tuple[QRectF, str]] = []

    def add_hotspot(self, rect: QRectF, text: str) -> None:
        if not hasattr(self, "_spots"):
            self._spots = []
        token = next((t for t in text.split() if is_address(t)), None)
        if token:
            self._spots.append((QRectF(rect), token))

    def hotspot_at(self, pos: QPointF) -> str | None:
        return next((a for r, a in getattr(self, "_spots", []) if r.contains(pos)), None)

    def label(self, p, at: QPointF, text: str) -> None:
        """Draw a label and make the address in it draggable."""
        p.drawText(at, text)
        r = p.fontMetrics().boundingRect(text)
        self.add_hotspot(QRectF(at.x() + r.x(), at.y() + r.y(), r.width(), r.height()), text)

    def mousePressEvent(self, e):
        self.hotspot_press(e)

    def mouseMoveEvent(self, e):
        self.hotspot_move(e)

    def hotspot_press(self, e) -> None:
        self._drag_from = e.position() if self.hotspot_at(e.position()) else None

    def hotspot_move(self, e) -> None:
        start = getattr(self, "_drag_from", None)
        if start is None:
            self.setCursor(Qt.OpenHandCursor if self.hotspot_at(e.position()) else Qt.ArrowCursor)
            return
        if e.buttons() & Qt.LeftButton and (e.position() - start).manhattanLength() >= QApplication.startDragDistance():
            self._drag_from = None
            start_drag(self, self.hotspot_at(start))
