"""Ladder editor: display with live highlighting, selection, keyboard, context menu,
operand editing, drag and drop. Edits go through `edit` (pure model functions) and are
undoable as program snapshots."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from PySide6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QFontMetrics, QKeySequence, QPainter, QPen, QUndoCommand, QUndoStack
from PySide6.QtWidgets import (QCompleter, QFormLayout, QFrame, QInputDialog, QLabel, QLineEdit,
                               QMenu, QScrollArea, QVBoxLayout, QWidget)

from ..core import edit, profiles
from ..core.profiles.base import parse_param
from . import io_drag, notation
from ..core.program import Instr, Parallel, Program, ProgramFile, walk
from . import theme
from .ladder_layout import RungGeometry, is_block, layout_rung, natural_width
from .primitives import paint_instruction

MARGIN = 12
RUNG_GAP = 18
MIME = "application/x-plcyard-instr"


@dataclass
class Row:
    rung: int            # index in file.rungs; len(rungs) is the END rung
    top: float           # y of the comment (or of the rung if no comment)
    rung_y: float
    height: float
    geom: RungGeometry | None


class Snapshot(QUndoCommand):
    """Undo/redo by swapping whole program copies (programs are small)."""

    def __init__(self, canvas: "LadderCanvas", before: Program, after: Program, text: str):
        super().__init__(text)
        self.canvas, self.before, self.after = canvas, before, after
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
            return
        self.canvas._restore(self.after)

    def undo(self):
        self.canvas._restore(self.before)


class OperandEditor(QFrame):
    """Inline editor: one field per operand, live validation, Enter commits, Esc cancels."""

    def __init__(self, canvas: "LadderCanvas", rung: int, path: tuple, ins: Instr, at: QPointF):
        super().__init__(canvas)
        self.canvas, self.rung, self.path, self.ins = canvas, rung, path, ins
        self.setFrameShape(QFrame.StyledPanel)
        self.setAutoFillBackground(True)
        spec = canvas.specs[ins.mnemonic]
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        title = QLabel(f"{ins.mnemonic} — {spec.title}")
        title.setFont(theme.font("sans", "md"))
        lay.addWidget(title)
        form = QFormLayout()
        self.fields: list[QLineEdit] = []
        known = sorted(canvas.known_addresses())
        for k, (kind, label) in enumerate(zip(spec.operands, spec.labels)):
            val = notation.show(ins.operands[k], canvas.program) if k < len(ins.operands) else ""
            f = QLineEdit("" if val == "?" else val)
            f.setFont(theme.font("mono", "base"))
            f.setPlaceholderText(canvas.profile.kinds.get(kind, ""))
            f.setCompleter(QCompleter(known, f))
            f.textChanged.connect(self._validate)
            f.returnPressed.connect(self.commit)
            f.setAccessibleName(label)
            form.addRow(label, f)
            self.fields.append(f)
        lay.addLayout(form)
        self.error = QLabel()
        self.error.setProperty("status", "danger")
        self.error.setWordWrap(True)
        lay.addWidget(self.error)
        hint = QLabel("Enter to apply · Esc to cancel")
        hint.setProperty("muted", "true")
        lay.addWidget(hint)
        self.adjustSize()
        vis = canvas.visibleRegion().boundingRect()
        x = max(vis.left() + 4, min(int(at.x()), vis.right() - self.width() - 4))
        y = int(at.y()) if at.y() + self.height() < vis.bottom() else int(at.y()) - self.height() - 100
        self.move(x, max(vis.top() + 4, y))
        self.show()
        if self.fields:
            self.fields[0].setFocus()
            self.fields[0].selectAll()
        self._validate()

    def _values(self) -> list[str]:
        spec = self.canvas.specs[self.ins.mnemonic]
        vals = [notation.store(f.text(), self.canvas.program) if f.text().strip() else "" for f in self.fields]
        need = len(spec.operands) - spec.optional
        while len(vals) > need and not vals[-1]:
            vals.pop()
        return [v or "?" for v in vals]

    def _validate(self) -> None:
        problems = self.canvas.profile.validate(self.ins.mnemonic, self._values(), self.canvas.program,
                                                self.canvas.file_no)
        self.error.setText("\n".join(problems))
        self.error.setVisible(bool(problems))
        for f in self.fields:
            f.setProperty("invalid", "false")
            f.style().unpolish(f)
            f.style().polish(f)
        self.adjustSize()

    def commit(self) -> None:
        self.canvas.apply_edit("Edit operands",
                               lambda body: edit.set_operands(body, self.path, self._values(), self.canvas.profile,
                                                                 self.canvas.program, self.canvas.file_no),
                               self.rung, select=self.path)
        self.close_editor()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close_editor()
        else:
            super().keyPressEvent(e)

    def close_editor(self) -> None:
        self.canvas.editor = None
        self.canvas.setFocus()
        self.deleteLater()


class LadderCanvas(QWidget):
    changed = Signal()          # program edited
    selectionChanged = Signal()

    def __init__(self):
        super().__init__()
        self.program: Program | None = None
        self.file_no = 2
        self.dt = None                       # the PLC memory while live
        self.trace: dict = {}
        self.live = False
        self.undo = QUndoStack(self)
        self.sel: tuple | None = None        # ("rung", n) or ("instr", n, path)
        self.clipboard = None                # ("rung", Rung) or ("node", node)
        self.rows: list[Row] = []
        self.editor: OperandEditor | None = None
        self._press = None
        self._drop: tuple | None = None      # (rung, Slot) or ("newrung", index)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)
        self.setMouseTracking(False)

    # -- data -------------------------------------------------------------
    @property
    def file(self) -> ProgramFile | None:
        return self.program.files.get(self.file_no) if self.program else None

    @property
    def profile(self):
        return profiles.get(self.program.profile if self.program else profiles.DEFAULT)

    @property
    def specs(self):
        return self.profile.specs

    def set_program(self, program: Program | None) -> None:
        self.program = program
        self.sel = None
        self.undo.clear()
        self._relayout()

    def set_file(self, number: int) -> None:
        self.file_no = number
        self.sel = None
        self._relayout()

    def set_live(self, dt, live: bool, trace: dict | None = None) -> None:
        """live: highlight from the PLC; trace only when the PLC runs this exact program."""
        self.dt, self.live, self.trace = dt, live, trace or {}
        self.update()

    def known_addresses(self) -> set[str]:
        out = set(self.program.symbols) if self.program else set()
        if self.program:
            out.update(self.program.tags)
            out.update(f.title for n, f in self.program.files.items() if n != 2 and f.title)
            f = self.file
            if f is not None:
                out.update("#" + n
                           for sec in f.interface.values() for n in sec)
            for f in self.program.files.values():
                for r in f.rungs:
                    for ins in walk(r.body):
                        out.update(o for o in ins.operands if ":" in o)
        return out

    # -- editing ----------------------------------------------------------
    def apply_edit(self, text: str, fn, rung: int | None = None, select=None) -> bool:
        """Run fn on the rung body (or on the file when rung is None) as one undo step."""
        if self.program is None:
            return False
        before = copy.deepcopy(self.program)
        try:
            target = self.file.rungs[rung].body if rung is not None else self.file
            result = fn(target)
        except (edit.EditError, IndexError) as e:
            self.window().statusBar().showMessage(str(e), 4000)
            return False
        if select is not None:
            self.sel = select(result) if callable(select) else (("instr", rung, select) if rung is not None else select)
        self.undo.push(Snapshot(self, before, copy.deepcopy(self.program), text))
        self._relayout()
        self.changed.emit()
        return True

    def _restore(self, program: Program) -> None:
        """Undo and redo touch only this routine (and the symbols), not the other open ones."""
        if self.file_no in program.files:
            self.program.files[self.file_no] = copy.deepcopy(program.files[self.file_no])
        self.program.symbols = copy.deepcopy(program.symbols)
        self.sel = None
        self._relayout()
        self.changed.emit()

    def selected_instr(self) -> Instr | None:
        if self.sel and self.sel[0] == "instr":
            try:
                node = edit.node_at(self.file.rungs[self.sel[1]].body, self.sel[2])
            except (edit.EditError, IndexError):
                return None
            return node if isinstance(node, Instr) else None
        return None

    def insert_mnemonic(self, mnemonic: str) -> None:
        """Instruction bar click: right of the selected instruction, or into the selected rung."""
        if self.file is None:
            return
        if mnemonic == "RUNG":
            return self.new_rung()
        if mnemonic == "BRANCH":
            return self.add_branch()
        if self.sel is None or self.sel[1] >= len(self.file.rungs):
            self.new_rung()
        kind, n = self.sel[0], self.sel[1]
        node = edit.new_instr(mnemonic, self.specs)
        if kind == "instr":
            sp, k = edit.parent_slot(self.sel[2])
            slot = edit.Slot(sp, k + 1)
        else:
            slot = edit.default_slot(self.file.rungs[n].body, mnemonic, self.specs)
        self.apply_edit(f"Add {mnemonic}", lambda body: edit.insert(body, slot, node), n,
                        select=lambda path: ("instr", n, path))

    def new_rung(self) -> None:
        idx = self.sel[1] + 1 if self.sel else len(self.file.rungs)
        idx = min(idx, len(self.file.rungs))
        self.apply_edit("New rung", lambda f: edit.new_rung(f, idx), None,
                        select=lambda n: ("rung", n))

    def add_branch(self) -> None:
        if not (self.sel and self.sel[0] == "instr"):
            self.window().statusBar().showMessage("Select the instruction to put in a branch.", 4000)
            return
        n, path = self.sel[1], self.sel[2]
        self.apply_edit("Add branch", lambda body: edit.wrap_in_branch(body, path), n,
                        select=lambda par: ("instr", n, par + (0, 0)))

    def add_leg(self) -> None:
        par = self._enclosing_parallel()
        if par is None:
            return
        n = self.sel[1]
        self.apply_edit("Add branch leg", lambda body: edit.add_leg(body, par), n,
                        select=lambda leg: ("rung", n))

    def _enclosing_parallel(self) -> tuple | None:
        if not (self.sel and self.sel[0] == "instr"):
            return None
        body = self.file.rungs[self.sel[1]].body
        path = self.sel[2]
        while len(path) >= 2:
            path = path[:-2]
            if isinstance(edit.node_at(body, path), Parallel):
                return path
        return None

    def delete_selection(self) -> None:
        if not self.sel:
            return
        n = self.sel[1]
        if n >= len(self.file.rungs):
            return
        if self.sel[0] == "rung":
            self.apply_edit("Delete rung", lambda f: f.rungs.pop(n), None,
                            select=lambda _: ("rung", min(n, len(self.file.rungs))) if self.file.rungs else None)
        else:
            path = self.sel[2]
            self.apply_edit("Delete instruction", lambda body: edit.remove(body, path), n,
                            select=lambda _: ("rung", n))

    def delete_leg(self) -> None:
        if not (self.sel and self.sel[0] == "instr"):
            return
        par = self._enclosing_parallel()
        if par is None:
            return
        n, leg = self.sel[1], self.sel[2][:len(par) + 1]
        self.apply_edit("Delete branch leg", lambda body: edit.remove(body, leg), n,
                        select=lambda _: ("rung", n))

    def copy_selection(self, cut: bool = False) -> None:
        if not self.sel or self.sel[1] >= len(self.file.rungs):
            return
        if self.sel[0] == "rung":
            self.clipboard = ("rung", copy.deepcopy(self.file.rungs[self.sel[1]]))
        else:
            self.clipboard = ("node", copy.deepcopy(edit.node_at(self.file.rungs[self.sel[1]].body, self.sel[2])))
        if cut:
            self.delete_selection()

    def paste(self, before: bool = False) -> None:
        if not self.clipboard:
            return
        kind, item = self.clipboard
        if kind == "rung":
            idx = (self.sel[1] + (0 if before else 1)) if self.sel else len(self.file.rungs)
            idx = min(idx, len(self.file.rungs))
            self.apply_edit("Paste rung", lambda f: f.rungs.insert(idx, copy.deepcopy(item)) or idx, None,
                            select=lambda i: ("rung", i))
            return
        if not self.sel or self.sel[1] >= len(self.file.rungs):
            return
        n = self.sel[1]
        if self.sel[0] == "instr":
            sp, k = edit.parent_slot(self.sel[2])
            slot = edit.Slot(sp, k if before else k + 1)
        else:
            slot = edit.Slot((), 0 if before else len(self.file.rungs[n].body.items))
        self.apply_edit("Paste", lambda body: edit.insert(body, slot, copy.deepcopy(item)), n,
                        select=lambda p: ("instr", n, p))

    def toggle_contact(self) -> None:
        ins = self.selected_instr()
        if ins and ins.mnemonic in ("XIC", "XIO"):
            n, path = self.sel[1], self.sel[2]
            self.apply_edit("Toggle contact", lambda body: edit.toggle_contact(body, path), n, select=path)

    def edit_comment(self) -> None:
        if not self.sel or self.sel[1] >= len(self.file.rungs):
            return
        n = self.sel[1]
        old = self.file.rungs[n].comment
        text, ok = QInputDialog.getMultiLineText(self, "Rung comment", f"Comment for rung {n}:", old)
        if ok and text != old:
            def set_comment(f):
                f.rungs[n].comment = text.replace("\r", " ").replace("\n", " ")
            self.apply_edit("Edit comment", set_comment, None, select=("rung", n))

    def edit_symbol(self) -> None:
        ins = self.selected_instr()
        if not ins or not ins.operands or ins.operands[0] == "?":
            return
        addr = ins.operands[0]
        old = self.program.symbols.get(addr, "")
        text, ok = QInputDialog.getText(self, "Symbol", f"Description for {addr}:", text=old)
        if ok and text != old:
            def set_symbol(_f):
                if text.strip():
                    self.program.symbols[addr] = text.strip()
                else:
                    self.program.symbols.pop(addr, None)
            self.apply_edit("Edit symbol", set_symbol, None, select=self.sel)

    def open_operand_editor(self) -> None:
        ins = self.selected_instr()
        if ins is None or not self.specs.get(ins.mnemonic) or not self.specs[ins.mnemonic].operands:
            return
        rect = self._instr_rect(self.sel[1], self.sel[2])
        if self.editor:
            self.editor.close_editor()
        self.editor = OperandEditor(self, self.sel[1], self.sel[2], ins,
                                    QPointF(rect.left(), rect.bottom() + 2) if rect else QPointF(40, 40))

    # -- geometry ---------------------------------------------------------
    def _gutter(self) -> int:
        return theme.layout("rung-gutter-w")

    def _left(self) -> float:
        return MARGIN + self._gutter()

    def _comment_h(self, text: str, width: float) -> int:
        if not text:
            return 0
        fm = QFontMetrics(theme.font("sans", "sm"))
        r = fm.boundingRect(0, 0, int(width), 10000, Qt.AlignLeft | Qt.TextWordWrap, text)
        return r.height() + 4

    def _rails_width(self) -> float:
        scroll = self.parentWidget()
        avail = scroll.width() if scroll else 800
        w = avail - self._gutter() - 2 * MARGIN
        f = self.file
        if f:
            for r in f.rungs:
                w = max(w, natural_width(r.body, self.specs))
        return max(w, 300)

    def _compute_rows(self) -> float:
        f = self.file
        rails = self._rails_width()
        self.rows = []
        y = MARGIN
        for n, r in enumerate(f.rungs if f else []):
            ch = self._comment_h(r.comment, rails)
            g = layout_rung(r.body, rails, self.specs)
            self.rows.append(Row(n, y, y + ch, g.height, g))
            y += ch + g.height + RUNG_GAP
        self.rows.append(Row(len(f.rungs) if f else 0, y, y, 52, None))
        return y + 52 + MARGIN

    def _relayout(self) -> None:
        h = self._compute_rows()
        self.setMinimumSize(QSize(int(self._rails_width() + self._gutter() + 2 * MARGIN), int(h)))
        self.selectionChanged.emit()
        self.update()

    def _instr_rect(self, rung: int, path: tuple) -> QRectF | None:
        for row in self.rows:
            if row.rung == rung and row.geom:
                for pl in row.geom.instrs:
                    if pl.path == path:
                        return QRectF(self._left() + pl.x, row.rung_y + pl.y, pl.w, pl.h)
        return None

    def _hit(self, pos: QPointF):
        """("instr", rung, path) / ("rung", rung) / None for a point."""
        for row in self.rows:
            if row.top <= pos.y() < row.rung_y + row.height + RUNG_GAP / 2:
                if row.geom and pos.x() >= self._left():
                    for pl in row.geom.instrs:
                        r = QRectF(self._left() + pl.x, row.rung_y + pl.y, pl.w, pl.h)
                        if r.contains(pos):
                            return ("instr", row.rung, pl.path)
                return ("rung", row.rung)
        return None

    def _drop_target(self, pos: QPointF):
        hit = self._hit(pos)
        if hit is None:
            return ("newrung", len(self.file.rungs))
        n = hit[1]
        if n >= len(self.file.rungs) or pos.x() < self._left():
            return ("newrung", n)
        if hit[0] == "instr":
            rect = self._instr_rect(n, hit[2])
            sp, k = edit.parent_slot(hit[2])
            return (n, edit.Slot(sp, k + (1 if pos.x() > rect.center().x() else 0)), rect, pos.x() > rect.center().x())
        return (n, None, None, None)

    # -- painting ---------------------------------------------------------
    def _energized(self, spec, operands: list[str]) -> bool:
        if not (self.live and self.dt and operands and spec) or spec.shape not in ("contact", "contact_nc", "coil"):
            return False
        try:
            on = self.dt.read_bit(operands[0])
        except Exception:
            return False
        return not on if spec.shape == "contact_nc" else on

    def _wire_on(self, rung_no: int, tag) -> bool:
        if not self.live:
            return False
        hit = self.trace.get((self.file_no, rung_no) + tag[0])
        return bool(hit and hit[0 if tag[1] == "in" else 1])

    def _block_extras(self, ins):
        """Live rows (Accum) and status pins, as the controller profile reports them."""
        if not self.dt or not ins.operands:
            return [], []
        try:
            return self.profile.live(self.dt, ins)
        except Exception:
            return [], []

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), theme.color("bg"))
        if not self.rows:
            self._compute_rows()
        rails = self._rails_width()
        left = self._left()
        symbols = self.program.symbols if self.program else {}
        f = self.file
        for row in self.rows:
            n = row.rung
            selected_rung = self.sel is not None and self.sel[0] == "rung" and self.sel[1] == n
            if selected_rung:
                p.fillRect(QRectF(MARGIN / 2, row.top - 4, rails + self._gutter() + MARGIN,
                                  row.rung_y - row.top + row.height + 8), theme.color("accent-soft"))
            if row.geom is None:      # END rung
                self._paint_rung(p, left, row.rung_y, rails, row.height, n, selected_rung)
                p.setPen(QPen(theme.color("wire"), 2))
                p.drawLine(QPointF(left, row.rung_y + 26), QPointF(left + rails, row.rung_y + 26))
                p.setFont(theme.font("mono", "sm"))
                p.setPen(theme.color("text-muted"))
                box = QRectF(left + rails / 2 - 30, row.rung_y + 18, 60, 16)
                p.fillRect(box, theme.color("accent-soft") if selected_rung else theme.color("bg"))
                p.drawText(box, Qt.AlignCenter, "END")
                if f is not None and not f.rungs:
                    p.setFont(theme.font("sans", "sm"))
                    p.drawText(QRectF(left, row.rung_y + 40, rails, 20), Qt.AlignCenter,
                               "Empty program. Press Insert or click a rung button to start.")
                continue
            rung = f.rungs[n]
            if rung.comment:
                p.setFont(theme.font("sans", "sm"))
                p.setPen(theme.color("comment-text"))
                p.drawText(QRectF(left, row.top, rails, row.rung_y - row.top),
                           Qt.AlignLeft | Qt.TextWordWrap, notation.show_comment(rung.comment))
            self._paint_rung(p, left, row.rung_y, rails, row.height, n, selected_rung)
            off, on = QPen(theme.color("wire"), 2), QPen(theme.color("energized"), 3)
            for w in sorted(row.geom.wires, key=lambda w: self._wire_on(n, w.tag)):
                p.setPen(on if self._wire_on(n, w.tag) else off)
                p.drawLine(QPointF(left + w.x1, row.rung_y + w.y1), QPointF(left + w.x2, row.rung_y + w.y2))
            for pl in row.geom.instrs:
                ins = pl.instr
                extra, pins = self._block_extras(ins)
                hit = self.trace.get((self.file_no, n) + pl.path) if self.live else None
                spec = self.specs.get(ins.mnemonic)
                on_ = bool(hit and hit[1]) if is_block(ins, self.specs) else self._energized(spec, ins.operands)
                sel = self.sel is not None and self.sel[0] == "instr" and self.sel[1] == n and self.sel[2] == pl.path
                title = notation.mnemonic(ins.mnemonic)
                ops = [notation.show(o, self.program) for o in ins.operands]
                labels = notation.labels(ins.mnemonic, list(spec.labels)) if spec else None
                if ins.mnemonic == "CALL" and ops:          # the block (or its instance) heads the box
                    params = [parse_param(o) or ("", "", o) for o in ins.operands[1:]]
                    title, labels = ops[0], [f"{n} {'→' if arrow == '=>' else '←'}" if n else "" for n, arrow, _ in params]
                    ops = [notation.show(v, self.program) for _, _, v in params]
                extra = [(notation.live_label(k, ins.mnemonic), v) for k, v in extra]
                pins = [(notation.pin(k), on) for k, on in pins if notation.pin(k)]
                paint_instruction(
                    p, QRectF(left + pl.x, row.rung_y + pl.y, pl.w, pl.h), title, ops,
                    symbols.get(ins.operands[0], "") if ins.operands else "",
                    energized=on_, selected=sel,
                    labels=labels,
                    extra=extra, pins=pins, shape=spec.shape if spec else "block",
                    letter=notation.letter(ins.mnemonic, spec.letter) if spec else "")
        self._paint_drop(p)

    def _paint_drop(self, p: QPainter) -> None:
        if not self._drop:
            return
        pen = QPen(theme.color("drop-target"), 4)
        p.setPen(pen)
        if self._drop[0] == "operand":
            p.drawRoundedRect(self._drop[3].adjusted(-3, -3, 3, 3), 6, 6)
            return
        if self._drop[0] == "newrung":
            idx = self._drop[1]
            row = self.rows[min(idx, len(self.rows) - 1)]
            y = row.top - RUNG_GAP / 2
            p.drawLine(QPointF(MARGIN, y), QPointF(self.width() - MARGIN, y))
            return
        n, slot, rect, after = self._drop
        if rect is not None:
            x = rect.right() if after else rect.left()
            p.drawLine(QPointF(x, rect.top() + 6), QPointF(x, rect.top() + 46))
        else:
            row = self.rows[n]
            p.drawRect(QRectF(self._left(), row.rung_y, self._rails_width(), row.height))

    def _paint_rung(self, p, left, y, rails, h, n, selected):
        p.setFont(theme.font("mono", "sm"))
        p.setPen(theme.color("accent") if selected else theme.color("text-muted"))
        p.drawText(QRectF(MARGIN, y + 18, self._gutter() - 8, 16), Qt.AlignRight | Qt.AlignVCenter, f"{n:03d}")
        p.setPen(QPen(theme.color("rail"), 3))
        p.drawLine(QPointF(left, y), QPointF(left, y + h))
        p.drawLine(QPointF(left + rails, y), QPointF(left + rails, y + h))

    # -- mouse ------------------------------------------------------------
    def mousePressEvent(self, e):
        self.setFocus()
        hit = self._hit(e.position())
        self.sel = hit
        self._press = (e.position(), hit) if hit and hit[0] == "instr" else None
        self.selectionChanged.emit()
        self.update()
        if e.button() == Qt.RightButton:
            self._context_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if not self._press or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position() - self._press[0]).manhattanLength() < 8:
            return
        _, (kind, n, path) = self._press
        self._press = None
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME, f"move:{n}:{','.join(map(str, path))}".encode())
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def mouseDoubleClickEvent(self, e):
        hit = self._hit(e.position())
        if hit and hit[0] == "instr":
            self.sel = hit
            self.open_operand_editor()
        elif hit and hit[0] == "rung" and hit[1] < len(self.file.rungs):
            self.sel = hit
            self.edit_comment()

    def _context_menu(self, at) -> None:
        menu = QMenu(self)
        has_rung = self.sel and self.sel[1] < len(self.file.rungs)
        ins = self.selected_instr()

        def add(text, slot, enabled=True, shortcut=None):
            a = menu.addAction(text)
            a.triggered.connect(slot)
            a.setEnabled(bool(enabled))
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            return a

        if ins:
            add("Edit operands…", self.open_operand_editor, self.specs.get(ins.mnemonic) and self.specs[ins.mnemonic].operands, "F2")
            add("Edit symbol…", self.edit_symbol, ins.operands and ins.operands[0] != "?")
            if ins.mnemonic in ("XIC", "XIO"):
                add(f"Change to {'XIO' if ins.mnemonic == 'XIC' else 'XIC'}", self.toggle_contact)
            menu.addSeparator()
            add("Put in a branch", self.add_branch)
            add("Add branch leg", self.add_leg, self._enclosing_parallel() is not None)
            add("Delete branch leg", self.delete_leg, self._enclosing_parallel() is not None)
            menu.addSeparator()
        add("Cut", lambda: self.copy_selection(cut=True), has_rung, QKeySequence.Cut)
        add("Copy", self.copy_selection, has_rung, QKeySequence.Copy)
        add("Paste left" if ins else "Paste above", lambda: self.paste(before=True), self.clipboard)
        add("Paste right" if ins else "Paste below", self.paste, self.clipboard, QKeySequence.Paste)
        add("Delete", self.delete_selection, has_rung, QKeySequence.Delete)
        menu.addSeparator()
        add("Insert rung below", self.new_rung, True, "Ins")
        add("Edit rung comment…", self.edit_comment, has_rung)
        win = self.window()
        if ins and ins.mnemonic == "PID" and ins.operands and ins.operands[0] != "?" and hasattr(win, "pid_setup"):
            menu.addSeparator()
            add("PID Setup…", lambda: win.pid_setup(ins.operands[0]))
        if ins and ins.mnemonic in ("JSR", "CALL") and ins.operands and hasattr(win, "open_routine_named"):
            menu.addSeparator()
            add(f"Go to {ins.operands[0]}", lambda: win.open_routine_named(ins.operands[0]))
        if ins and self.specs.get(ins.mnemonic) and self.specs[ins.mnemonic].shape in ("contact", "contact_nc", "coil") \
                and ins.operands and ins.operands[0] != "?" and hasattr(win, "force"):
            menu.addSeparator()
            op = ins.operands[0]
            add("Force On", lambda: win.force(op, True))
            add("Force Off", lambda: win.force(op, False))
            add("Remove Force", lambda: win.force(op, None))
        menu.exec(at)

    # -- keyboard ---------------------------------------------------------
    def keyPressEvent(self, e):
        k, mods = e.key(), e.modifiers()
        if e.matches(QKeySequence.Undo):
            return self.undo.undo()
        if e.matches(QKeySequence.Redo):
            return self.undo.redo()
        if e.matches(QKeySequence.Copy):
            return self.copy_selection()
        if e.matches(QKeySequence.Cut):
            return self.copy_selection(cut=True)
        if e.matches(QKeySequence.Paste):
            return self.paste()
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            return self.delete_selection()
        if k == Qt.Key_Insert:
            return self.new_rung()
        if k in (Qt.Key_F2, Qt.Key_Return, Qt.Key_Enter):
            return self.open_operand_editor()
        if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            return self._navigate(k)
        super().keyPressEvent(e)

    def _navigate(self, key) -> None:
        f = self.file
        if f is None:
            return
        if self.sel is None:
            self.sel = ("rung", 0)
        n = self.sel[1]
        if key in (Qt.Key_Up, Qt.Key_Down):
            n = max(0, min(len(f.rungs), n + (1 if key == Qt.Key_Down else -1)))
            self.sel = ("rung", n)
        elif n < len(f.rungs):
            order = edit.instructions_in_order(f.rungs[n].body)
            if order:
                if self.sel[0] == "rung":
                    i = 0 if key == Qt.Key_Right else len(order) - 1
                else:
                    i = order.index(self.sel[2]) + (1 if key == Qt.Key_Right else -1)
                if 0 <= i < len(order):
                    self.sel = ("instr", n, order[i])
                else:
                    self.sel = ("rung", n)
        self.selectionChanged.emit()
        self.update()
        rect = self._instr_rect(self.sel[1], self.sel[2]) if self.sel[0] == "instr" else None
        row = next((r for r in self.rows if r.rung == self.sel[1]), None)
        scroll = self.parentWidget().parentWidget() if self.parentWidget() else None
        if isinstance(scroll, QScrollArea):
            target = rect.center() if rect else QPointF(0, row.rung_y if row else 0)
            scroll.ensureVisible(int(target.x()), int(target.y()), 60, 80)

    # -- drag and drop ----------------------------------------------------
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME) or e.mimeData().hasFormat(io_drag.MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        md = e.mimeData()
        if md.hasFormat(io_drag.MIME):
            self._drop = self._address_target(e.position(), bytes(md.data(io_drag.MIME)).decode())
        elif md.hasFormat(MIME):
            self._drop = self._drop_target(e.position())
        else:
            return
        e.acceptProposedAction()
        self.update()

    def dragLeaveEvent(self, e):
        self._drop = None
        self.update()

    def dropEvent(self, e):
        if e.mimeData().hasFormat(io_drag.MIME):
            address = bytes(e.mimeData().data(io_drag.MIME)).decode()
            target = self._address_target(e.position(), address)
            self._drop = None
            e.acceptProposedAction()
            self.drop_address(address, target)
            self.update()
            return
        target = self._drop_target(e.position())
        self._drop = None
        data = bytes(e.mimeData().data(MIME)).decode()
        e.acceptProposedAction()
        if data.startswith("move:"):
            _, n, path = data.split(":")
            src = tuple(int(x) for x in path.split(",")) if path else ()
            self._drop_move(int(n), src, target)
        else:
            self._drop_new(data, target)
        self.update()

    # -- I/O dragged from a simulation ---------------------------------------------------
    BIT_KINDS = ("bit", "bool", "bool_opt")
    WORD_KINDS = ("value", "word", "value_opt")
    OUT_KINDS = ("dest", "word", "dest_opt")

    def _operand_for(self, ins: Instr, address: str) -> int | None:
        """Which operand of an instruction a dropped address fills."""
        spec = self.specs.get(ins.mnemonic)
        if spec is None:
            return None
        if io_drag.is_bit(address):
            kinds = self.BIT_KINDS
        else:
            kinds = self.OUT_KINDS if io_drag.direction_of(address) == "O" else self.WORD_KINDS
        free = [k for k, kind in enumerate(spec.operands) if kind in kinds]
        unset = [k for k in free if k >= len(ins.operands) or ins.operands[k] in ("", "?")]
        return (unset or free or [None])[0]

    def _address_target(self, pos: QPointF, address: str):
        """("operand", rung, path, rect) over an instruction that can take it, else where a new
        contact or coil would go."""
        if self.file is None:
            return None
        hit = self._hit(pos)
        if hit and hit[0] == "instr" and hit[1] < len(self.file.rungs):
            node = edit.node_at(self.file.rungs[hit[1]].body, hit[2])
            if isinstance(node, Instr) and self._operand_for(node, address) is not None:
                return ("operand", hit[1], hit[2], self._instr_rect(hit[1], hit[2]))
        return self._drop_target(pos) if io_drag.is_bit(address) else None

    def drop_address(self, address: str, target) -> None:
        if target is None:
            self.window().statusBar().showMessage(f"Drop {address} on an instruction that takes a value", 4000)
            return
        if target[0] == "operand":
            _, n, path, _ = target
            node = edit.node_at(self.file.rungs[n].body, path)
            k = self._operand_for(node, address)
            ops = list(node.operands) + ["?"] * (k + 1 - len(node.operands))
            ops[k] = address
            self.apply_edit(f"Set {address}", lambda body: edit.set_operands(
                body, path, ops, self.profile, self.program, self.file_no), n, select=path)
            return
        mnemonic = "OTE" if io_drag.direction_of(address) == "O" else "XIC"
        if target[0] == "newrung":
            idx = target[1]
            self.apply_edit("New rung", lambda f: edit.new_rung(f, idx), None, select=lambda m: ("rung", m))
            n, slot = idx, None
        else:
            n, slot = target[0], target[1]
        node = edit.new_instr(mnemonic, self.specs)
        node.operands = [self.profile.normalize(address)]
        if slot is None:
            slot = edit.default_slot(self.file.rungs[n].body, mnemonic, self.specs)
        self.apply_edit(f"Add {mnemonic} {address}", lambda body: edit.insert(body, slot, node), n,
                        select=lambda p: ("instr", n, p))

    def _drop_new(self, mnemonic: str, target) -> None:
        if mnemonic in ("RUNG", "BRANCH") or target[0] == "newrung":
            if mnemonic == "BRANCH":
                return self.add_branch()
            idx = target[1] if target[0] == "newrung" else target[0] + 1
            self.sel = ("rung", idx - 1) if idx > 0 else None
            self.apply_edit("New rung", lambda f: edit.new_rung(f, idx), None, select=lambda n: ("rung", n))
            if mnemonic == "RUNG":
                return
        n, slot = (self.sel[1], None) if target[0] == "newrung" else (target[0], target[1])
        node = edit.new_instr(mnemonic, self.specs)
        if slot is None:
            slot = edit.default_slot(self.file.rungs[n].body, mnemonic, self.specs)
        self.apply_edit(f"Add {mnemonic}", lambda body: edit.insert(body, slot, node), n,
                        select=lambda p: ("instr", n, p))

    def _drop_move(self, n: int, src: tuple, target) -> None:
        if target[0] == "newrung":
            return
        tn, slot = target[0], target[1]
        if slot is None:
            node = edit.node_at(self.file.rungs[n].body, src)
            slot = edit.default_slot(self.file.rungs[tn].body, node.mnemonic if isinstance(node, Instr) else "XIC", self.specs)
        if tn == n:
            self.apply_edit("Move", lambda body: edit.move(body, src, slot), n,
                            select=lambda p: ("instr", n, p))
            return

        def across(f):
            node = edit.remove(f.rungs[n].body, src)
            return edit.insert(f.rungs[tn].body, slot, node)
        self.apply_edit("Move", across, None, select=lambda p: ("instr", tn, p))


class LadderView(QScrollArea):
    def __init__(self):
        super().__init__()
        self.canvas = LadderCanvas()
        self.setWidget(self.canvas)
        self.setWidgetResizable(True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.canvas._relayout()


def start_new_drag(source: QWidget, mnemonic: str) -> None:
    drag = QDrag(source)
    mime = QMimeData()
    mime.setData(MIME, mnemonic.encode())
    drag.setMimeData(mime)
    drag.exec(Qt.CopyAction)
