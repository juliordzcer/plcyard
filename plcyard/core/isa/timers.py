"""Timers and counters (manual chapter 2). Time base fixed at 0.1 s.

Element layout (3 words): word 0 status bits, word 1 PRE, word 2 ACC.
Timers accumulate simulated time between evaluations, so a timer inside a
subroutine that is not called every scan still keeps correct time.
"""

from . import PlcFault, instruction, to_int16

TIME_BASE_MS = 100.0
EN, TT, DN = 15, 14, 13
CU, CD, OV, UN = 15, 14, 12, 11
PRE, ACC = 1, 2


def _bit(words, i, b):
    return bool((words[i] >> b) & 1)


def _set(words, i, b, on):
    w = words[i] & 0xFFFF
    words[i] = to_int16((w | (1 << b)) if on else (w & ~(1 << b)))


def _write_preset(ctx, ops):
    words, i = ctx.element_base(ops[0])
    words[i + PRE] = to_int16(int(ctx.value(ops[1])))


def _accumulate(ctx, key, words, i, cap=True):
    """Advance ACC by whole time-base intervals since the last mark."""
    mark = ctx.timer_marks.get(key)
    if mark is None:
        ctx.timer_marks[key] = ctx.now_ms
        return
    ticks = int((ctx.now_ms - mark) // TIME_BASE_MS)
    if ticks:
        ctx.timer_marks[key] = mark + ticks * TIME_BASE_MS
        acc = words[i + ACC] + ticks
        words[i + ACC] = min(acc, words[i + PRE]) if cap else to_int16(acc)


def _check_preset(words, i, op):
    if words[i + PRE] < 0 or words[i + ACC] < 0:
        raise PlcFault(0x0034, f"{op}: negative preset or accumulator")


def _ton_prescan(ctx, ops):
    words, i = ctx.element_base(ops[0])
    if _bit(words, i, TT):          # was timing when RUN was left: start over
        words[i + ACC] = 0
    ctx.timer_marks.pop(ops[0], None)


@instruction("TON", "Timer on delay", "Timer/Counter", ["timer", "value"], ["Timer", "Preset"],
             output=True, on_download=_write_preset, on_prescan=_ton_prescan)
def ton(ctx, ops, cond):
    words, i = ctx.element_base(ops[0])
    _check_preset(words, i, ops[0])
    if cond:
        if not _bit(words, i, EN):
            ctx.timer_marks[ops[0]] = ctx.now_ms
        elif words[i + ACC] < words[i + PRE]:
            _accumulate(ctx, ops[0], words, i)
        _set(words, i, EN, True)
        done = words[i + ACC] >= words[i + PRE]
        _set(words, i, DN, done)
        _set(words, i, TT, not done)
    else:
        words[i + ACC] = 0
        for b in (EN, TT, DN):
            _set(words, i, b, False)
        ctx.timer_marks.pop(ops[0], None)
    return cond


def _tof_prescan(ctx, ops):
    words, i = ctx.element_base(ops[0])
    # Rung false on return: DN off and ACC = PRE; rung true: normal true evaluation resets ACC.
    _set(words, i, TT, False)
    _set(words, i, DN, False)
    words[i + ACC] = words[i + PRE]
    ctx.timer_marks.pop(ops[0], None)


@instruction("TOF", "Timer off delay", "Timer/Counter", ["timer", "value"], ["Timer", "Preset"],
             output=True, on_download=_write_preset, on_prescan=_tof_prescan)
def tof(ctx, ops, cond):
    words, i = ctx.element_base(ops[0])
    _check_preset(words, i, ops[0])
    if cond:
        words[i + ACC] = 0
        _set(words, i, EN, True)
        _set(words, i, TT, False)
        _set(words, i, DN, True)
        ctx.timer_marks.pop(ops[0], None)
    else:
        if _bit(words, i, EN):       # true-to-false: start timing
            ctx.timer_marks[ops[0]] = ctx.now_ms
            _set(words, i, EN, False)
        if _bit(words, i, DN):
            _accumulate(ctx, ops[0], words, i)
            if words[i + ACC] >= words[i + PRE]:
                _set(words, i, DN, False)
                _set(words, i, TT, False)
            else:
                _set(words, i, TT, True)
    return cond


@instruction("RTO", "Retentive timer on", "Timer/Counter", ["timer", "value"], ["Timer", "Preset"],
             output=True, on_download=_write_preset,
             on_prescan=lambda ctx, ops: ctx.timer_marks.pop(ops[0], None))
def rto(ctx, ops, cond):
    words, i = ctx.element_base(ops[0])
    _check_preset(words, i, ops[0])
    if cond:
        if not _bit(words, i, EN):
            ctx.timer_marks[ops[0]] = ctx.now_ms
        elif words[i + ACC] < words[i + PRE]:
            _accumulate(ctx, ops[0], words, i)
        _set(words, i, EN, True)
        done = words[i + ACC] >= words[i + PRE]
        _set(words, i, DN, done)
        _set(words, i, TT, not done)
    else:
        _set(words, i, EN, False)
        _set(words, i, TT, False)
        ctx.timer_marks.pop(ops[0], None)
    return cond


def _counter_prescan(bit):
    def prescan(ctx, ops):
        words, i = ctx.element_base(ops[0])
        _set(words, i, bit, True)    # manual: CU/CD set before entering RUN, so no count on first scan
    return prescan


def _count(ctx, ops, cond, edge_bit, step):
    words, i = ctx.element_base(ops[0])
    if cond and not _bit(words, i, edge_bit):
        acc = words[i + ACC] + step
        if acc > 32767:
            acc -= 65536
            _set(words, i, OV, True)
        elif acc < -32768:
            acc += 65536
            _set(words, i, UN, True)
        words[i + ACC] = acc
    _set(words, i, edge_bit, cond)
    _set(words, i, DN, words[i + ACC] >= words[i + PRE])
    return cond


@instruction("CTU", "Count up", "Timer/Counter", ["counter", "value"], ["Counter", "Preset"],
             output=True, on_download=_write_preset, on_prescan=_counter_prescan(CU))
def ctu(ctx, ops, cond):
    return _count(ctx, ops, cond, CU, +1)


@instruction("CTD", "Count down", "Timer/Counter", ["counter", "value"], ["Counter", "Preset"],
             output=True, on_download=_write_preset, on_prescan=_counter_prescan(CD))
def ctd(ctx, ops, cond):
    return _count(ctx, ops, cond, CD, -1)


@instruction("RES", "Reset", "Timer/Counter", ["element"], ["Element"], output=True)
def res(ctx, ops, cond):
    if cond:
        words, i = ctx.element_base(ops[0])
        t = ctx.dt.addr(ops[0]).type
        if t == "R":
            fd = _bit(words, i, 8)
            words[i] = 0
            _set(words, i, 8, fd)        # manual: all control bits except FD reset
            words[i + 2] = 0             # POS
        else:
            words[i] = 0
            words[i + ACC] = 0
            ctx.timer_marks.pop(ops[0], None)
    return cond
