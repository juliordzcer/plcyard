"""Structured text editor: syntax colours, line numbers, problems as you type and a watch list of
the variables the routine uses, with live values while the PLC runs it."""

from __future__ import annotations

import re

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextFormat
from PySide6.QtWidgets import (QHeaderView, QLabel, QPlainTextEdit, QSplitter, QTableWidget, QTableWidgetItem,
                               QTextEdit, QVBoxLayout, QWidget)

from ..core import profiles, st
from . import theme


class Highlighter(QSyntaxHighlighter):
    RULES = [
        (re.compile(r"\b(" + "|".join(sorted(st.KEYWORDS)) + r")\b", re.I), "accent", True),
        (re.compile(r"\b(" + "|".join(st.FUNCS) + r"|\w+_TO_\w+)\s*(?=\()", re.I), "accent", False),
        (re.compile(r"\b(?:T|TIME)#[0-9A-Za-z_.]+|\b\d+#[0-9A-Fa-f_]+|\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b"), "success", False),
        (re.compile(r'"[^"\n]*"|%[IQM][BWD]?\d+(?:\.\d)?', re.I), "text", True),
    ]
    COMMENT = re.compile(r"//[^\n]*")
    OPEN, CLOSE = re.compile(r"\(\*|/\*"), re.compile(r"\*\)|\*/")

    def highlightBlock(self, text: str) -> None:
        for rx, colour, bold in self.RULES:
            fmt = QTextCharFormat()
            fmt.setForeground(theme.color(colour))
            if bold:
                fmt.setFontWeight(600)
            for m in rx.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
        muted = QTextCharFormat()
        muted.setForeground(theme.color("comment-text"))
        muted.setFontItalic(True)
        for m in self.COMMENT.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), muted)
        # (* … *) and /* … */ may span lines: block state 1 = still inside a block comment
        inside, pos, start = self.previousBlockState() == 1, 0, 0
        self.setCurrentBlockState(0)
        while True:
            if not inside:
                m = self.OPEN.search(text, pos)
                if not m:
                    break
                start, pos, inside = m.start(), m.end(), True
            m = self.CLOSE.search(text, pos)
            if m is None:
                self.setFormat(start, len(text) - start, muted)
                self.setCurrentBlockState(1)
                break
            self.setFormat(start, m.end() - start, muted)
            pos, inside = m.end(), False


class _Gutter(QWidget):
    def __init__(self, editor: "CodeEdit"):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, e):
        self.editor.paint_gutter(e)


class CodeEdit(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setFont(theme.font("mono", "base"))
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.gutter = _Gutter(self)
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.gutter_width(), 0, 0, 0))
        self.updateRequest.connect(self._scroll_gutter)
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        self.error_lines: set[int] = set()

    def gutter_width(self) -> int:
        return 14 + self.fontMetrics().horizontalAdvance("9") * max(3, len(str(self.blockCount())))

    def _scroll_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.gutter.setGeometry(QRect(cr.left(), cr.top(), self.gutter_width(), cr.height()))

    def paint_gutter(self, e):
        p = QPainter(self.gutter)
        p.fillRect(e.rect(), theme.color("surface"))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        h = round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible():
                bad = (n + 1) in self.error_lines
                p.setPen(theme.color("danger") if bad else theme.color("text-muted"))
                p.drawText(0, top, self.gutter.width() - 6, h, Qt.AlignRight, ("● " if bad else "") + str(n + 1))
            block = block.next()
            top += h
            n += 1

    def mark_errors(self, lines: set[int]) -> None:
        self.error_lines = lines
        sels = []
        colour = QColor(theme.color("danger"))
        colour.setAlpha(40)
        for ln in sorted(lines):
            block = self.document().findBlockByNumber(ln - 1)
            if not block.isValid():
                continue
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(colour)
            sel.format.setProperty(QTextFormat.FullWidthSelection, True)
            sel.cursor = self.textCursor()
            sel.cursor.setPosition(block.position())
            sel.cursor.clearSelection()
            sels.append(sel)
        self.setExtraSelections(sels)
        self.gutter.update()


class StEditor(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.program = None
        self.file_no = 2
        self.memory = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Vertical)
        self.edit = CodeEdit()
        self.edit.setAccessibleName("Structured text")
        self.highlighter = Highlighter(self.edit.document())
        split.addWidget(self.edit)
        bottom = QWidget()
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(8, 4, 8, 4)
        self.problems = QLabel()
        self.problems.setWordWrap(True)
        self.problems.setProperty("status", "danger")
        bl.addWidget(self.problems)
        self.watch = QTableWidget(0, 2)
        self.watch.setHorizontalHeaderLabels(["Variable", "Value"])
        self.watch.verticalHeader().hide()
        self.watch.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.watch.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.watch.setFont(theme.font("mono", "sm"))
        self.watch.setEditTriggers(QTableWidget.NoEditTriggers)
        self.watch.setAccessibleName("Watch: variables used by the routine")
        bl.addWidget(self.watch, 1)
        split.addWidget(bottom)
        split.setSizes([500, 200])
        lay.addWidget(split)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self.check)
        self._loading = False
        self.edit.textChanged.connect(self._text_changed)

    @property
    def file(self):
        return self.program.files.get(self.file_no) if self.program else None

    def set_program(self, program, file_no: int = 2) -> None:
        self.program, self.file_no = program, file_no
        self._loading = True
        self.edit.setPlainText(self.file.source if self.file else "")
        self._loading = False
        self.check()

    def _text_changed(self) -> None:
        if self._loading or not self.file:
            return
        self.file.source = self.edit.toPlainText()
        self.changed.emit()
        self._timer.start()

    def check(self) -> list[str]:
        """Parse and check the routine against the program's tags; show problems and the watch list."""
        if not self.file:
            return []
        prof = profiles.get(self.program.profile)
        msgs, lines, names = [], set(), []
        try:
            body = st.parse(self.file.source)
        except st.StError as e:
            msgs, lines = [str(e)], {e.line}
        else:
            names = list(dict.fromkeys(n.ref.replace('"', "") for n in st.walk(body)
                                       if isinstance(n, st.Var) and not n.index))
            names += [c.instance.replace('"', "") for c in st.calls(body)
                      if not c.index and c.instance.replace('"', "") not in names]
            try:
                mem = prof.new_memory()
                prof.load(self.program, mem)
            except Exception as e:                       # the tag list itself is wrong
                msgs = [f"Tags: {e}"]
            else:
                for d in prof.check_st(self.program, mem):
                    if d.file == self.file_no:
                        msgs.append(f"line {d.line}: {d.message}")
                        lines.add(d.line or 1)
        self.problems.setText("\n".join(msgs[:6]) + (f"\n…and {len(msgs) - 6} more" if len(msgs) > 6 else ""))
        self.problems.setVisible(bool(msgs))
        self.edit.mark_errors(lines)
        self._set_watch(names)
        return msgs

    def _set_watch(self, names: list[str]) -> None:
        if [self.watch.item(r, 0).text() for r in range(self.watch.rowCount())] == names:
            return
        self.watch.setRowCount(len(names))
        for r, n in enumerate(names):
            self.watch.setItem(r, 0, QTableWidgetItem(n))
            self.watch.setItem(r, 1, QTableWidgetItem(""))
        self.refresh()

    def set_live(self, memory) -> None:
        self.memory = memory
        self.refresh()

    def refresh(self) -> None:
        prof = profiles.get(self.program.profile) if self.program else None
        for r in range(self.watch.rowCount()):
            name = self.watch.item(r, 0).text()
            text = ""
            if self.memory is not None and prof is not None:
                try:
                    t = self.memory.ref(name).type.lower()
                    if t in ("timer", "counter", "pid", "iec_timer", "iec_counter", "pid_compact"):
                        text = prof.tag_value(self.memory, name)
                    elif t == "bool":
                        text = "TRUE" if self.memory.read_bit(name) else "FALSE"
                    else:
                        v = self.memory.read_word(name)
                        text = f"{v:g}" if isinstance(v, float) else str(v)
                except Exception:
                    text = "?"
            self.watch.item(r, 1).setText(text)
