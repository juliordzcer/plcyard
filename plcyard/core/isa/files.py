"""Bit shift and sequencer instructions (manual chapter 7).

Control element words: 0 status (EN 15, EU 14, DN 13, EM 12, ER 11, UL 10, IN 9, FD 8),
1 LEN, 2 POS. Actions happen on the false-to-true transition, detected with EN.
"""

from __future__ import annotations

from ..address import Address
from . import PlcFault, instruction, to_int16

EN, DN, ER, UL, FD = 15, 13, 11, 10, 8
LEN, POS = 1, 2


def _bit(words, i, b):
    return bool((words[i] >> b) & 1)


def _set(words, i, b, on):
    w = words[i] & 0xFFFF
    words[i] = to_int16((w | (1 << b)) if on else (w & ~(1 << b)))


def _file_start(ctx, op):
    """(file words, start index) of a #file operand."""
    a = ctx.dt.addr(op)
    f, idx, _ = ctx.dt._locate(Address(a.type, a.file, a.element if a.element is not None else 0))
    return f, idx


def _write_len(ctl_index, len_index, pos_index=None):
    """On download, copy the instruction's length (and position) into the control element."""
    def on_download(ctx, ops):
        words, i = ctx.element_base(ops[ctl_index])
        words[i + LEN] = to_int16(int(ops[len_index]))
        if pos_index is not None and pos_index < len(ops):
            words[i + POS] = to_int16(int(ops[pos_index]))
    return on_download


def _shift(ctx, ops, cond, left: bool):
    file_op, ctl, src, _length = ops
    words, i = ctx.element_base(ctl)
    rising = cond and not _bit(words, i, EN)
    _set(words, i, EN, cond)
    if not cond:
        _set(words, i, DN, False)
        return cond
    if not rising:
        return cond
    n = words[i + LEN]
    f, start = _file_start(ctx, file_op)
    if n <= 0 or start + (n + 15) // 16 > len(f.words):
        _set(words, i, ER, True)
        raise PlcFault(0x0044, f"{ops[0]}: length {n} does not fit the file")
    get = lambda k: (f.words[start + k // 16] >> (k % 16)) & 1
    def put(k, v):
        w = f.words[start + k // 16] & 0xFFFF
        f.words[start + k // 16] = to_int16((w | (1 << (k % 16))) if v else (w & ~(1 << (k % 16))))
    incoming = 1 if ctx.bit(src) else 0
    if left:
        out = get(n - 1)
        for k in range(n - 1, 0, -1):
            put(k, get(k - 1))
        put(0, incoming)
    else:
        out = get(0)
        for k in range(n - 1):
            put(k, get(k + 1))
        put(n - 1, incoming)
    _set(words, i, UL, bool(out))
    _set(words, i, DN, True)
    return cond


SHIFT_OPS = ["file", "control", "bit", "int"]
SHIFT_LABELS = ["File", "Control", "Bit address", "Length"]


@instruction("BSL", "Bit shift left", "File/Shift", SHIFT_OPS, SHIFT_LABELS, output=True,
             on_download=_write_len(1, 3))
def bsl(ctx, ops, cond):
    return _shift(ctx, ops, cond, left=True)


@instruction("BSR", "Bit shift right", "File/Shift", SHIFT_OPS, SHIFT_LABELS, output=True,
             on_download=_write_len(1, 3))
def bsr(ctx, ops, cond):
    return _shift(ctx, ops, cond, left=False)


def _step(ctx, file_op, words, i):
    """Advance POS on a rising edge; wrap to 1 after LEN. Returns the file word index."""
    n, pos = words[i + LEN], words[i + POS]
    if n <= 0 or pos < 0 or pos > n:
        _set(words, i, ER, True)
        raise PlcFault(0x0042, f"{file_op}: position {pos} / length {n} is invalid")
    _set(words, i, DN, False)
    pos = 1 if pos >= n else pos + 1
    words[i + POS] = pos
    if pos == n:
        _set(words, i, DN, True)


def _seq_word(ctx, file_op, words, i):
    f, start = _file_start(ctx, file_op)
    k = start + words[i + POS]
    if k >= len(f.words):
        _set(words, i, ER, True)
        raise PlcFault(0x0042, f"{file_op}: position points past the end of the file")
    return f, k


SEQ_OPS = ["file", "value", "word", "control", "int", "int"]


@instruction("SQO", "Sequencer output", "Sequencer", SEQ_OPS,
             ["File", "Mask", "Dest", "Control", "Length", "Position"], output=True,
             on_download=_write_len(3, 4, 5), optional=1)
def sqo(ctx, ops, cond):
    file_op, mask_op, dest, ctl = ops[:4]
    words, i = ctx.element_base(ctl)
    if cond and not _bit(words, i, EN):
        _step(ctx, file_op, words, i)
    _set(words, i, EN, cond)
    if cond:
        f, k = _seq_word(ctx, file_op, words, i)
        mask = ctx.word(mask_op) & 0xFFFF
        cur = ctx.word(dest) & 0xFFFF
        ctx.store(dest, (cur & ~mask) | (int(f.words[k]) & mask))
    return cond


@instruction("SQC", "Sequencer compare", "Sequencer", SEQ_OPS,
             ["File", "Mask", "Source", "Control", "Length", "Position"], output=True,
             on_download=_write_len(3, 4, 5), optional=1)
def sqc(ctx, ops, cond):
    file_op, mask_op, src, ctl = ops[:4]
    words, i = ctx.element_base(ctl)
    if cond and not _bit(words, i, EN):
        _step(ctx, file_op, words, i)
    _set(words, i, EN, cond)
    if cond:
        f, k = _seq_word(ctx, file_op, words, i)
        mask = ctx.word(mask_op) & 0xFFFF
        _set(words, i, FD, (ctx.word(src) & mask) == (int(f.words[k]) & mask))
    return cond


@instruction("SQL", "Sequencer load", "Sequencer", ["file", "value", "control", "int", "int"],
             ["File", "Source", "Control", "Length", "Position"], output=True,
             on_download=_write_len(2, 3, 4), optional=1)
def sql(ctx, ops, cond):
    file_op, src, ctl = ops[:3]
    words, i = ctx.element_base(ctl)
    if cond and not _bit(words, i, EN):
        _step(ctx, file_op, words, i)
        f, k = _seq_word(ctx, file_op, words, i)
        f.words[k] = to_int16(ctx.word(src))
    _set(words, i, EN, cond)
    return cond
