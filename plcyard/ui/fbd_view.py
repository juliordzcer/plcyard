"""Function block diagram editor: blocks from the palette, wires from an output pin to an input pin,
operands on unwired pins (double-click a pin, or drop an I/O point from the simulation), live values
and energized BOOL wires while the PLC runs."""

from __future__ import annotations

import copy

from PySide6.QtCore import QMimeData, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QDrag, QKeySequence, QPainter, QPainterPath, QPen, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QInputDialog, QMenu, QScrollArea, QTabBar, QToolButton,
                               QVBoxLayout, QWidget)

from ..core import fbd
from . import io_drag, notation, theme

GRID = 20.0
BLOCK_W = 110.0
HEAD = 30.0
ROW = 24.0
STUB = 14.0
MIME = "application/x-plcyard-fbd-block"


def block_height(b: fbd.Block) -> float:
    return HEAD + max(len(b.input_pins()), len(b.output_pins()), 1) * ROW + 8


def block_rect(b: fbd.Block) -> QRectF:
    return QRectF(b.x, b.y, BLOCK_W, block_height(b))


def pin_point(b: fbd.Block, pin: str, output: bool) -> QPointF:
    pins = b.output_pins() if output else b.input_pins()
    k = next((i for i, p in enumerate(pins) if p.name == pin), 0)
    y = b.y + HEAD + k * ROW + ROW / 2
    return QPointF(b.x + BLOCK_W + STUB if output else b.x - STUB, y)


class _Snapshot(QUndoCommand):
    def __init__(self, view: "FbdCanvas", before: dict, after: dict, text: str):
        super().__init__(text)
        self.view, self.before, self.after, self._first = view, before, after, True

    def redo(self):
        if self._first:
            self._first = False
            return
        self.view._restore(self.after)

    def undo(self):
        self.view._restore(self.before)


class FbdCanvas(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.program = None
        self.number = 2
        self.undo = QUndoStack(self)
        self.sel: tuple | None = None            # ("block", id) or ("wire", index)
        self.memory = None
        self.live = False
        self.values: dict = {}
        self._drag = None                        # ("move", id, offset) | ("wire", id, pin, is_output, point)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumSize(900, 600)

    # -- data -----------------------------------------------------------------------------------------
    @property
    def diagram(self) -> fbd.Diagram:
        f = self.program.files[self.number]
        if f.diagram is None:
            f.diagram = fbd.Diagram()
        return f.diagram

    def set_routine(self, program, number: int) -> None:
        self.program, self.number = program, number
        self.sel = None
        self.undo.clear()
        self._resize()
        self.update()

    def set_live(self, memory, live: bool, values: dict | None) -> None:
        self.memory, self.live, self.values = memory, live, values or {}
        self.update()

    def edit(self, text: str, fn) -> None:
        """Run fn on the diagram as one undo step."""
        before = copy.deepcopy(self.diagram.to_dict())
        fn(self.diagram)
        after = copy.deepcopy(self.diagram.to_dict())
        if before != after:
            self.undo.push(_Snapshot(self, before, after, text))
            self._resize()
            self.update()
            self.changed.emit()

    def _restore(self, d: dict) -> None:
        self.program.files[self.number].diagram = fbd.Diagram.from_dict(copy.deepcopy(d))
        self.sel = None
        self._resize()
        self.update()
        self.changed.emit()

    def _resize(self) -> None:
        if self.program is None:
            return
        w = max((b.x + BLOCK_W + 200 for b in self.diagram.blocks), default=0)
        h = max((b.y + block_height(b) + 120 for b in self.diagram.blocks), default=0)
        self.setMinimumSize(int(max(900, w)), int(max(600, h)))

    # -- editing ------------------------------------------------------------------------------------
    def free_spot(self) -> QPointF:
        y = max((b.y + block_height(b) for b in self.diagram.blocks), default=0.0) + GRID * 2
        return QPointF(GRID * 12, y)

    def add_block(self, kind: str, at: QPointF | None = None) -> int:
        at = at or self.free_spot()
        bid = self.diagram.next_id()

        def fn(d):
            d.blocks.append(fbd.Block(bid, kind, _snap(at.x()), _snap(at.y())))
        self.edit(f"Add {kind}", fn)
        self.sel = ("block", bid)
        if fbd.LIBRARY[kind].instance:
            self.edit_instance(bid)
        return bid

    def delete_selection(self) -> None:
        if not self.sel:
            return
        if self.sel[0] == "block":
            bid = self.sel[1]

            def fn(d):
                d.blocks = [b for b in d.blocks if b.id != bid]
                d.wires = [w for w in d.wires if w.src != bid and w.dst != bid]
            self.edit("Delete block", fn)
        else:
            k = self.sel[1]
            self.edit("Delete wire", lambda d: d.wires.pop(k) if k < len(d.wires) else None)
        self.sel = None

    def connect(self, src: int, src_pin: str, dst: int, dst_pin: str) -> None:
        def fn(d):
            d.wires = [w for w in d.wires if not (w.dst == dst and w.dst_pin == dst_pin)]
            d.wires.append(fbd.Wire(src, src_pin, dst, dst_pin))
            b = d.block(dst)
            if b is not None:
                b.operands.pop(dst_pin, None)        # a wired input takes no operand
        self.edit("Connect", fn)

    def set_operand(self, bid: int, pin: str, text: str) -> None:
        def fn(d):
            b = d.block(bid)
            if text.strip():
                b.operands[pin] = notation.store(text, self.program)
                d.wires = [w for w in d.wires if not (w.dst == bid and w.dst_pin == pin)]
            else:
                b.operands.pop(pin, None)
        self.edit(f"Set {pin}", fn)

    def edit_operand(self, bid: int, pin: str) -> None:
        b = self.diagram.block(bid)
        cur = notation.show(b.operands.get(pin, ""), self.program)
        text, ok = QInputDialog.getText(self, f"{b.type} {pin}", "Tag, address or constant (empty: none):", text=cur)
        if ok:
            self.set_operand(bid, pin, text)

    def edit_instance(self, bid: int) -> None:
        b = self.diagram.block(bid)
        kind = b.type_().instance
        text, ok = QInputDialog.getText(self, f"{b.type} instance", f"{kind} tag:", text=b.instance)
        if ok:
            self.edit("Set instance", lambda d: setattr(d.block(bid), "instance", text.strip()))

    def set_inputs(self, bid: int, n: int) -> None:
        def fn(d):
            b = d.block(bid)
            b.inputs = max(2, n)
            names = {p.name for p in b.input_pins()}
            d.wires = [w for w in d.wires if w.dst != bid or w.dst_pin in names]
            b.operands = {k: v for k, v in b.operands.items() if k in names or k in {p.name for p in b.output_pins()}}
        self.edit("Inputs", fn)

    # -- hit testing ------------------------------------------------------------------------------------
    def pin_at(self, pos: QPointF):
        """(block id, pin, is_output) near pos."""
        for b in reversed(self.diagram.blocks):
            for out, pins in ((False, b.input_pins()), (True, b.output_pins())):
                for p in pins:
                    pt = pin_point(b, p.name, out)
                    if abs(pt.x() - pos.x()) <= STUB + 4 and abs(pt.y() - pos.y()) <= ROW / 2:
                        return b.id, p.name, out
        return None

    def block_at(self, pos: QPointF) -> fbd.Block | None:
        return next((b for b in reversed(self.diagram.blocks) if block_rect(b).contains(pos)), None)

    def wire_at(self, pos: QPointF) -> int | None:
        for k, w in enumerate(self.diagram.wires):
            path = self._wire_path(w)
            if path is not None:
                stroker = QPainterPath(path)
                for i in range(stroker.elementCount() - 1):
                    a, c = stroker.elementAt(i), stroker.elementAt(i + 1)
                    r = QRectF(QPointF(min(a.x, c.x) - 4, min(a.y, c.y) - 4), QPointF(max(a.x, c.x) + 4, max(a.y, c.y) + 4))
                    if r.contains(pos):
                        return k
        return None

    def _wire_path(self, w: fbd.Wire) -> QPainterPath | None:
        s, d = self.diagram.block(w.src), self.diagram.block(w.dst)
        if s is None or d is None:
            return None
        a, b = pin_point(s, w.src_pin, True), pin_point(d, w.dst_pin, False)
        mid = a.x() + max(GRID, (b.x() - a.x()) / 2) if b.x() > a.x() else a.x() + GRID
        path = QPainterPath(a)
        if b.x() > a.x():
            path.lineTo(mid, a.y())
            path.lineTo(mid, b.y())
        else:                                   # back to an earlier block: go around below
            low = max(block_rect(s).bottom(), block_rect(d).bottom()) + GRID
            path.lineTo(mid, a.y())
            path.lineTo(mid, low)
            path.lineTo(b.x() - GRID, low)
            path.lineTo(b.x() - GRID, b.y())
        path.lineTo(b)
        return path

    # -- painting --------------------------------------------------------------------------------------
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("bg"))
        if self.program is None:
            return
        p.setPen(QPen(theme.color("border"), 1, Qt.DotLine))
        d = self.diagram
        if not d.blocks:
            p.setPen(theme.color("text-muted"))
            p.drawText(self.rect(), Qt.AlignCenter, "Empty diagram. Click a block in the bar above, or drag it here.")
        for k, w in enumerate(d.wires):
            path = self._wire_path(w)
            if path is None:
                continue
            v = self.values.get((w.src, w.src_pin)) if self.live else None
            on = v is True
            sel = self.sel == ("wire", k)
            p.setPen(QPen(theme.color("accent") if sel else (theme.color("energized") if on else theme.color("wire")),
                          3 if on or sel else 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        for b in d.blocks:
            self._paint_block(p, b)
        if self._drag and self._drag[0] == "wire":
            _, bid, pin, out, pt = self._drag
            start = pin_point(d.block(bid), pin, out)
            p.setPen(QPen(theme.color("drop-target"), 2, Qt.DashLine))
            p.drawLine(start, pt)

    def _paint_block(self, p: QPainter, b: fbd.Block) -> None:
        r = block_rect(b)
        sel = self.sel == ("block", b.id)
        p.setPen(QPen(theme.color("accent") if sel else theme.color("text"), 2 if sel else 1.5))
        p.setBrush(theme.color("bg"))
        p.drawRoundedRect(r, 4, 4)
        p.setFont(theme.font("sans", "md"))
        p.setPen(theme.color("text"))
        p.drawText(QRectF(r.left(), r.top() + 4, r.width(), 20), Qt.AlignCenter, b.type)
        if b.type_().instance:
            p.setFont(theme.font("mono", "sm"))
            p.setPen(theme.color("unset") if not b.instance else theme.color("text"))
            p.drawText(QRectF(r.left() - 40, r.top() - 18, r.width() + 80, 16), Qt.AlignCenter,
                       notation.show(b.instance, self.program) or "?")
        p.setFont(theme.font("mono", "sm"))
        for out, pins in ((False, b.input_pins()), (True, b.output_pins())):
            for k, pin in enumerate(pins):
                y = r.top() + HEAD + k * ROW + ROW / 2
                x0, x1 = (r.right(), r.right() + STUB) if out else (r.left() - STUB, r.left())
                v = self.values.get((b.id, pin.name)) if self.live else None
                p.setPen(QPen(theme.color("energized") if v is True else theme.color("wire"), 2))
                p.drawLine(QPointF(x0, y), QPointF(x1, y))
                p.setPen(theme.color("text-muted"))
                lab = QRectF(r.left() + 4, y - 7, r.width() - 8, 18)
                p.drawText(lab, (Qt.AlignRight if out else Qt.AlignLeft) | Qt.AlignVCenter, pin.name)
                op = b.operands.get(pin.name, "")
                text = notation.show(op, self.program) if op else ""
                if v is not None and not isinstance(v, bool):
                    text = (text + " = " if text else "") + (f"{v:.2f}" if isinstance(v, float) else str(v))
                if text:                                 # above the pin line, clear of the wires
                    p.setFont(theme.font("mono", "xs"))
                    p.setPen(theme.color("energized") if v is True else theme.color("text"))
                    if out:
                        p.drawText(QRectF(x0 + 2, y - 16, 220, 14), Qt.AlignLeft | Qt.AlignBottom, text)
                    else:
                        p.drawText(QRectF(x1 - 222, y - 16, 220, 14), Qt.AlignRight | Qt.AlignBottom, text)
                    p.setFont(theme.font("mono", "sm"))

    # -- mouse and keys --------------------------------------------------------------------------------
    def mousePressEvent(self, e):
        self.setFocus()
        pos = e.position()
        hit = self.pin_at(pos)
        if hit and e.button() == Qt.LeftButton:
            self._drag = ("wire", hit[0], hit[1], hit[2], pos)
            return
        b = self.block_at(pos)
        if b is not None:
            self.sel = ("block", b.id)
            if e.button() == Qt.LeftButton:
                self._drag = ("move", b.id, pos - QPointF(b.x, b.y), copy.deepcopy(self.diagram.to_dict()))
        else:
            k = self.wire_at(pos)
            self.sel = ("wire", k) if k is not None else None
        self.update()

    def mouseMoveEvent(self, e):
        if not self._drag:
            return
        pos = e.position()
        if self._drag[0] == "move":
            b = self.diagram.block(self._drag[1])
            off = self._drag[2]
            b.x, b.y = max(GRID * 12, _snap(pos.x() - off.x())), max(GRID, _snap(pos.y() - off.y()))
        else:
            self._drag = self._drag[:4] + (pos,)
        self.update()

    def mouseReleaseEvent(self, e):
        drag, self._drag = self._drag, None
        if not drag:
            return
        if drag[0] == "move":
            before = drag[3]
            after = copy.deepcopy(self.diagram.to_dict())
            if before != after:
                self.undo.push(_Snapshot(self, before, after, "Move block"))
                self._resize()
                self.changed.emit()
        else:
            _, bid, pin, out, _ = drag
            target = self.pin_at(e.position())
            if target and target[2] != out and target[0] != bid:
                src, dst = ((bid, pin), target[:2]) if out else (target[:2], (bid, pin))
                self.connect(src[0], src[1], dst[0], dst[1])
        self.update()

    def mouseDoubleClickEvent(self, e):
        hit = self.pin_at(e.position())
        if hit:
            return self.edit_operand(hit[0], hit[1])
        b = self.block_at(e.position())
        if b is not None and b.type_().instance:
            self.edit_instance(b.id)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            return self.delete_selection()
        if e.matches(QKeySequence.Undo):
            return self.undo.undo()
        if e.matches(QKeySequence.Redo):
            return self.undo.redo()
        super().keyPressEvent(e)

    def contextMenuEvent(self, e):
        pos = QPointF(e.pos())
        hit = self.pin_at(pos)
        b = self.block_at(pos)
        m = QMenu(self)
        if hit:
            m.addAction(f"Operand of {hit[1]}…", lambda: self.edit_operand(hit[0], hit[1]))
        if b is not None:
            self.sel = ("block", b.id)
            if b.type_().instance:
                m.addAction("Instance tag…", lambda: self.edit_instance(b.id))
            if b.type_().variable_inputs:
                n = len(b.input_pins())
                m.addAction("Add input", lambda: self.set_inputs(b.id, n + 1))
                if n > 2:
                    m.addAction("Remove last input", lambda: self.set_inputs(b.id, n - 1))
            if b.type == "PID" and b.instance and hasattr(self.window(), "pid_setup"):
                m.addAction("PID Setup…", lambda: self.window().pid_setup(b.instance))
            m.addAction("Delete block", self.delete_selection)
        elif self.wire_at(pos) is not None:
            self.sel = ("wire", self.wire_at(pos))
            m.addAction("Delete wire", self.delete_selection)
        if not m.isEmpty():
            m.exec(e.globalPos())
        self.update()

    # -- drops: blocks from the palette, I/O from the simulations -------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME) or e.mimeData().hasFormat(io_drag.MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(MIME):
            self.add_block(bytes(md.data(MIME)).decode(), e.position())
        elif md.hasFormat(io_drag.MIME):
            hit = self.pin_at(e.position())
            if hit:
                self.set_operand(hit[0], hit[1], bytes(md.data(io_drag.MIME)).decode())
        e.acceptProposedAction()


def _snap(v: float) -> float:
    return round(v / GRID) * GRID


class _BlockButton(QToolButton):
    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind
        self.setText(kind)
        bt = fbd.LIBRARY[kind]
        self.setToolTip(f"{kind} — {bt.title}")
        self.setAutoRaise(True)
        self._press = None

    def mousePressEvent(self, e):
        self._press = e.position()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._press is not None and (e.position() - self._press).manhattanLength() >= QApplication.startDragDistance():
            self._press = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(MIME, self.kind.encode())
            drag.setMimeData(mime)
            drag.exec(Qt.CopyAction)


class FbdView(QWidget):
    """Palette above the diagram."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.tabs = QTabBar()
        for f in fbd.FAMILIES:
            self.tabs.addTab(f)
        self.row = QHBoxLayout()
        self.row.setContentsMargins(8, 2, 8, 2)
        lay.addWidget(self.tabs)
        lay.addLayout(self.row)
        self.canvas = FbdCanvas()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)
        lay.addWidget(self.scroll, 1)
        self.tabs.currentChanged.connect(self._show)
        self._show(0)

    def _show(self, index: int) -> None:
        while self.row.count():
            item = self.row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        family = fbd.FAMILIES[index]
        for kind, bt in fbd.LIBRARY.items():
            if bt.family == family:
                b = _BlockButton(kind)
                b.clicked.connect(lambda _=False, k=kind: self.canvas.add_block(k))
                self.row.addWidget(b)
        self.row.addStretch(1)
