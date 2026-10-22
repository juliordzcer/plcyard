"""The instruction set. Every box passes power on as its output (Q, DN or ENO), so a coil can follow a
timer, a compare or a math box on the same rung. Integer math wraps to the destination type and sets
the Overflow flag; division by zero stores nothing, sets Overflow and passes no power.

Mnemonics are the canonical names files store; the editor shows them in the chosen notation (see
ui/notation.py)."""

from __future__ import annotations

import math as _m

from .. import isa, pid
from ..profiles.base import parse_param
from .memory import PlcMemoryError, parse_time

SPECS = isa.SPECS


def instruction(*a, **k):
    return isa.instruction(*a, **k)


def literal(op: str):
    """A number, TRUE/FALSE or a time like T#2s; None for a reference."""
    op = op.strip()
    t = parse_time(op)
    if t is not None:
        return t
    low = op.lower()
    if low in ("true", "false"):
        return int(low == "true")
    return isa.parse_literal(op)


def unused(op: str | None) -> bool:
    return op is None or op.strip() in ("", "?")


class Context:
    def __init__(self, mem):
        self.dt = mem
        self.now_ms = 0.0
        self.timer_marks: dict[str, float] = {}
        self.pid_state: dict[str, dict] = {}
        self.call = lambda target, inputs=None: {}

    def bit(self, op: str) -> bool:
        lit = literal(op)
        return bool(lit) if lit is not None else self.dt.read_bit(op)

    def set_bit(self, op: str, on: bool) -> None:
        self.dt.write_bit(op, on)

    def value(self, op: str):
        lit = literal(op)
        return lit if lit is not None else self.dt.read_word(op)

    def word(self, op: str) -> int:
        return int(self.value(op))

    def store(self, dest: str, value) -> bool:
        """Store converted to the destination's type; on integer overflow set Overflow, return False."""
        if self.dt.write_word(dest, value):
            self.dt.write_bit("Overflow", True)
            return False
        return True

    def element(self, op: str) -> dict:
        return self.dt.element(op)

    def is_real(self, op: str) -> bool:
        lit = literal(op)
        return isinstance(lit, float) if lit is not None else self.dt.type_of(op) == "REAL"


# -- contacts and coils ------------------------------------------------------------------------
@instruction("XIC", "Examine if closed (normally open contact)", "Bit", ["bool"], ["Bit"])
def xic(ctx, ops, cond):
    return cond and ctx.bit(ops[0])


@instruction("XIO", "Examine if open (normally closed contact)", "Bit", ["bool"], ["Bit"])
def xio(ctx, ops, cond):
    return cond and not ctx.bit(ops[0])


@instruction("OTE", "Output energize (coil)", "Bit", ["bool"], ["Bit"], output=True)
def ote(ctx, ops, cond):
    ctx.set_bit(ops[0], cond)
    return cond


@instruction("OTL", "Output latch (set coil)", "Bit", ["bool"], ["Bit"], output=True)
def otl(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], True)
    return cond


@instruction("OTU", "Output unlatch (reset coil)", "Bit", ["bool"], ["Bit"], output=True)
def otu(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], False)
    return cond


def _storage_on(ctx, ops):
    ctx.set_bit(ops[0], True)      # prescan: no false trigger on the first scan


@instruction("ONS", "One shot (rising edge of the rung)", "Bit", ["bool"], ["Storage bit"], on_prescan=_storage_on,
             shape="small", letter="ONS")
def ons(ctx, ops, cond):
    prev = ctx.bit(ops[0])
    ctx.set_bit(ops[0], cond)
    return cond and not prev


@instruction("OSR", "One shot rising", "Bit", ["bool", "bool"], ["Storage bit", "Output bit"],
             output=True, on_prescan=_storage_on)
def osr(ctx, ops, cond):
    prev = ctx.bit(ops[0])
    ctx.set_bit(ops[0], cond)
    ctx.set_bit(ops[1], cond and not prev)
    return cond


def _osf_prescan(ctx, ops):
    ctx.set_bit(ops[0], False)


@instruction("OSF", "One shot falling", "Bit", ["bool", "bool"], ["Storage bit", "Output bit"],
             output=True, on_prescan=_osf_prescan)
def osf(ctx, ops, cond):
    prev = ctx.bit(ops[0])
    ctx.set_bit(ops[0], cond)
    ctx.set_bit(ops[1], prev and not cond)
    return cond


def _edge(rising: bool):
    def run(ctx, ops, cond):
        now, before = ctx.bit(ops[0]), ctx.bit(ops[1])
        ctx.set_bit(ops[1], now)
        return cond and ((now and not before) if rising else (before and not now))
    return run


def _edge_prescan(ctx, ops):
    ctx.set_bit(ops[1], ctx.bit(ops[0]))      # no edge on the first scan


instruction("P", "Positive edge of an operand", "Bit", ["bool", "bool"], ["Operand", "Edge memory bit"],
            on_prescan=_edge_prescan, shape="small", letter="P")(_edge(True))
instruction("N", "Negative edge of an operand", "Bit", ["bool", "bool"], ["Operand", "Edge memory bit"],
            on_prescan=_edge_prescan, shape="small", letter="N")(_edge(False))


# -- timers and counters (milliseconds) -----------------------------------------------------------
def _key(op: str) -> str:
    return op.lower()


def _elapsed(ctx, key) -> int:
    """Whole ms since this timer was last evaluated; first evaluation returns 0."""
    mark = ctx.timer_marks.get(key)
    ctx.timer_marks[key] = ctx.now_ms
    return 0 if mark is None else int(ctx.now_ms - mark)


def _preset(ctx, ops, el) -> int:
    el["PRE"] = int(ctx.value(ops[1]))
    if el["PRE"] < 0 or el["ACC"] < 0:
        raise isa.PlcFault(0x0422, f"{ops[0]}: negative preset or accumulator")
    return el["PRE"]


def _timer_off(ctx, ops):
    ctx.element(ops[0]).update(EN=False, TT=False, DN=False, ACC=0)
    ctx.timer_marks.pop(_key(ops[0]), None)


def _accumulate(ctx, el, key, pre):
    dt = _elapsed(ctx, key) if el["EN"] else (ctx.timer_marks.__setitem__(key, ctx.now_ms) or 0)
    if not el["DN"]:
        el["ACC"] = min(el["ACC"] + dt, max(pre, el["ACC"]))


TIMER_OPS, TIMER_LABELS = ["timer", "time", "value_opt"], ["Timer", "Preset", "Accum"]


def _accum_start(ctx, ops):
    """An accumulator operand (third, optional) is the start value set on download."""
    if len(ops) > 2 and not unused(ops[2]):
        ctx.element(ops[0])["ACC"] = int(ctx.value(ops[2]))


@instruction("TON", "Timer on delay", "Timer/Counter", TIMER_OPS, TIMER_LABELS, optional=1, on_download=_accum_start,
             on_prescan=_timer_off)
def ton(ctx, ops, cond):
    el = ctx.element(ops[0])
    pre = _preset(ctx, ops, el)
    if not cond:
        _timer_off(ctx, ops)
        return False
    _accumulate(ctx, el, _key(ops[0]), pre)
    el["EN"] = True
    el["DN"] = el["ACC"] >= pre
    el["TT"] = not el["DN"]
    return el["DN"]


def _tof_prescan(ctx, ops):
    el = ctx.element(ops[0])
    el.update(EN=False, TT=False, DN=False, ACC=el["PRE"])
    ctx.timer_marks.pop(_key(ops[0]), None)


@instruction("TOF", "Timer off delay", "Timer/Counter", TIMER_OPS, TIMER_LABELS, optional=1, on_download=_accum_start,
             on_prescan=_tof_prescan)
def tof(ctx, ops, cond):
    el, key = ctx.element(ops[0]), _key(ops[0])
    pre = _preset(ctx, ops, el)
    if cond:
        el.update(EN=True, TT=False, DN=True, ACC=0)
        ctx.timer_marks.pop(key, None)
        return True
    if el["EN"]:                                   # falling edge: start timing
        el["EN"] = False
        ctx.timer_marks[key] = ctx.now_ms
    if el["DN"]:
        el["ACC"] = min(el["ACC"] + _elapsed(ctx, key), pre)
        done = el["ACC"] >= pre
        el["TT"] = not done
        el["DN"] = not done
    return el["DN"]


def _rto_prescan(ctx, ops):
    ctx.element(ops[0]).update(EN=False, TT=False)
    ctx.timer_marks.pop(_key(ops[0]), None)


@instruction("RTO", "Retentive timer on", "Timer/Counter", TIMER_OPS, TIMER_LABELS, optional=1, on_download=_accum_start,
             on_prescan=_rto_prescan)
def rto(ctx, ops, cond):
    el, key = ctx.element(ops[0]), _key(ops[0])
    pre = _preset(ctx, ops, el)
    if not cond:
        el.update(EN=False, TT=False)
        ctx.timer_marks.pop(key, None)
        return el["DN"]
    _accumulate(ctx, el, key, pre)
    el["EN"] = True
    el["DN"] = el["ACC"] >= pre
    el["TT"] = not el["DN"]
    return el["DN"]


@instruction("TP", "Pulse timer", "Timer/Counter", TIMER_OPS, TIMER_LABELS, optional=1, on_download=_accum_start,
             on_prescan=_timer_off)
def tp(ctx, ops, cond):
    el, key = ctx.element(ops[0]), _key(ops[0])
    pre = _preset(ctx, ops, el)
    if el["TT"]:                                   # pulsing: runs to the end whatever the input does
        el["ACC"] = min(el["ACC"] + _elapsed(ctx, key), pre)
        if el["ACC"] >= pre:
            el["TT"] = False
    elif cond and not el["EN"]:                    # rising edge starts a pulse
        el.update(TT=pre > 0, ACC=0)
        ctx.timer_marks[key] = ctx.now_ms
    elif not cond and el["ACC"] >= pre:
        el["ACC"] = 0
    el["EN"] = cond
    el["DN"] = el["TT"]
    return el["TT"]


def _counter_prescan(edge):
    def fn(ctx, ops):
        ctx.element(ops[0])[edge] = True          # no false count on the first scan
    return fn


def _count(edge, step):
    def run(ctx, ops, cond):
        el = ctx.element(ops[0])
        el["PRE"] = int(ctx.value(ops[1]))
        if cond and not el[edge]:
            acc = el["ACC"] + step
            if acc > 2147483647:
                acc, el["OV"] = -2147483648, True
            elif acc < -2147483648:
                acc, el["UN"] = 2147483647, True
            el["ACC"] = acc
        el[edge] = cond
        if len(ops) > 2 and not unused(ops[2]) and ctx.bit(ops[2]):
            if edge == "CU":                       # R: back to zero
                el.update(ACC=0, OV=False, UN=False)
            else:                                  # LD: load the preset
                el["ACC"] = el["PRE"]
        el["DN"] = el["ACC"] >= el["PRE"] if edge == "CU" else el["ACC"] <= 0
        return el["DN"]
    return run


instruction("CTU", "Count up", "Timer/Counter", ["counter", "value", "bool_opt"], ["Counter", "Preset", "Reset"],
            optional=1, on_prescan=_counter_prescan("CU"))(_count("CU", 1))
instruction("CTD", "Count down", "Timer/Counter", ["counter", "value", "bool_opt"], ["Counter", "Preset", "Load"],
            optional=1, on_prescan=_counter_prescan("CD"))(_count("CD", -1))


@instruction("RES", "Reset a timer, counter or control", "Timer/Counter", ["element"], ["Timer or counter"],
             output=True, shape="coil", letter="RES")
def res(ctx, ops, cond):
    if cond:
        el = ctx.element(ops[0])
        for k in el:
            if k not in ("PRE", "LEN"):
                el[k] = False if isinstance(el[k], bool) else 0
        ctx.timer_marks.pop(_key(ops[0]), None)
    return cond


# -- compare -------------------------------------------------------------------------------------
def _cmp(m, title, test):
    @instruction(m, title, "Compare", ["value", "value"], ["Source A", "Source B"])
    def run(ctx, ops, cond):
        return cond and test(ctx.value(ops[0]), ctx.value(ops[1]))
    return run


_cmp("EQU", "Equal", lambda a, b: a == b)
_cmp("NEQ", "Not equal", lambda a, b: a != b)
_cmp("LES", "Less than", lambda a, b: a < b)
_cmp("LEQ", "Less than or equal", lambda a, b: a <= b)
_cmp("GRT", "Greater than", lambda a, b: a > b)
_cmp("GEQ", "Greater than or equal", lambda a, b: a >= b)


@instruction("LIM", "Limit test (value within range)", "Compare", ["value", "value", "value"],
             ["Low limit", "Test", "High limit"])
def lim(ctx, ops, cond):
    lo, t, hi = (ctx.value(o) for o in ops)
    return cond and ((lo <= t <= hi) if lo <= hi else (t >= lo or t <= hi))


@instruction("MEQ", "Masked equal", "Compare", ["value", "value", "value"], ["Source", "Mask", "Compare"])
def meq(ctx, ops, cond):
    src, mask, ref = (ctx.word(o) for o in ops)
    return cond and (src & mask) == (ref & mask)


# -- math and move ---------------------------------------------------------------------------------
def _int_div(a, b):
    q = abs(a) // abs(b)                     # integer division truncates toward zero
    return q if (a >= 0) == (b >= 0) else -q


def _math(m, title, fn):
    @instruction(m, title, "Math", ["value", "value", "dest"], ["Source A", "Source B", "Dest"])
    def run(ctx, ops, cond):
        if not cond:
            return False
        a, b = ctx.value(ops[0]), ctx.value(ops[1])
        real = isinstance(a, float) or isinstance(b, float) or ctx.dt.type_of(ops[2]) == "REAL"
        try:
            r = fn(a, b, real)
        except ZeroDivisionError:
            ctx.set_bit("Overflow", True)
            return False
        return ctx.store(ops[2], r)
    return run


def _div(a, b, real):
    if b == 0:
        raise ZeroDivisionError
    return a / b if real else _int_div(a, b)


def _mod(a, b, real):
    if b == 0:
        raise ZeroDivisionError
    return _m.fmod(a, b) if real else a - _int_div(a, b) * b


_math("ADD", "Add", lambda a, b, r: a + b)
_math("SUB", "Subtract", lambda a, b, r: a - b)
_math("MUL", "Multiply", lambda a, b, r: a * b)
_math("DIV", "Divide", _div)
_math("MOD", "Modulo", _mod)


def _unary(m, title, family, fn):
    @instruction(m, title, family, ["value", "dest"], ["Source", "Dest"])
    def run(ctx, ops, cond):
        if not cond:
            return False
        try:
            return ctx.store(ops[1], fn(ctx, ctx.value(ops[0]), ops))
        except ValueError:
            ctx.set_bit("Overflow", True)
            return False
    return run


def _sqrt(ctx, v, ops):
    r = _m.sqrt(abs(v))
    return r if ctx.dt.type_of(ops[1]) == "REAL" else int(r + 0.5)


def _tod(ctx, v, ops):
    v = int(v)
    if not 0 <= v <= 9999:
        raise ValueError
    return int(str(v), 16)


def _frd(ctx, v, ops):
    digits = f"{int(v) & 0xFFFF:04X}"
    if not digits.isdigit():
        raise ValueError
    return int(digits)


_unary("MOV", "Move", "Move/Logical", lambda ctx, v, ops: v)
_unary("NEG", "Negate", "Math", lambda ctx, v, ops: -v)
_unary("SQR", "Square root", "Math", _sqrt)
_unary("NOT", "Bitwise NOT", "Move/Logical", lambda ctx, v, ops: ~int(v))
_unary("TOD", "Convert to BCD", "Move/Logical", _tod)
_unary("FRD", "Convert from BCD", "Move/Logical", _frd)


def _logic(m, title, op):
    @instruction(m, title, "Move/Logical", ["value", "value", "dest"], ["Source A", "Source B", "Dest"])
    def run(ctx, ops, cond):
        if cond:
            return ctx.store(ops[2], op(ctx.word(ops[0]), ctx.word(ops[1])))
        return False
    return run


_logic("AND", "Bitwise AND", lambda a, b: a & b)
_logic("OR", "Bitwise OR", lambda a, b: a | b)
_logic("XOR", "Bitwise XOR", lambda a, b: a ^ b)


@instruction("MVM", "Masked move", "Move/Logical", ["value", "value", "dest"], ["Source", "Mask", "Dest"])
def mvm(ctx, ops, cond):
    if cond:
        src, mask, dst = ctx.word(ops[0]), ctx.word(ops[1]), ctx.word(ops[2])
        return ctx.store(ops[2], (dst & ~mask) | (src & mask))
    return False


@instruction("CLR", "Clear", "Move/Logical", ["dest"], ["Dest"], output=True)
def clr(ctx, ops, cond):
    if cond:
        ctx.store(ops[0], 0)
    return cond


@instruction("SCP", "Scale with parameters", "Math",
             ["value", "value", "value", "value", "value", "dest"],
             ["Input", "Input min", "Input max", "Scaled min", "Scaled max", "Output"])
def scp(ctx, ops, cond):
    if not cond:
        return False
    x, x0, x1, y0, y1 = (float(ctx.value(o)) for o in ops[:5])
    if x1 == x0:
        ctx.set_bit("Overflow", True)
        return False
    return ctx.store(ops[5], y0 + (x - x0) * (y1 - y0) / (x1 - x0))


@instruction("NORM_X", "Normalize to 0.0-1.0", "Math", ["value", "value", "value", "dest"], ["Min", "Value", "Max", "Out"])
def norm_x(ctx, ops, cond):
    if not cond:
        return False
    lo, v, hi = (float(ctx.value(o)) for o in ops[:3])
    if hi == lo:
        return False
    return ctx.store(ops[3], (v - lo) / (hi - lo))


@instruction("SCALE_X", "Scale 0.0-1.0 to a range", "Math", ["value", "value", "value", "dest"],
             ["Min", "Value", "Max", "Out"])
def scale_x(ctx, ops, cond):
    if not cond:
        return False
    lo, v, hi = (float(ctx.value(o)) for o in ops[:3])
    return ctx.store(ops[3], v * (hi - lo) + lo)


# -- arrays: bit shift and sequencers (CONTROL holds LEN and POS) ----------------------------------------
def _control_init(ctl, length, position=None):
    def on_download(ctx, ops):
        el = ctx.element(ops[ctl])
        el["LEN"] = int(ctx.value(ops[length]))
        if position is not None and position < len(ops) and not unused(ops[position]):
            el["POS"] = int(ctx.value(ops[position]))
    return on_download


def _array_at(ctx, op):
    items, start, t = ctx.dt.array(op)
    if t not in ("SINT", "INT", "DINT", "BOOL"):
        raise PlcMemoryError(f"{op}: needs an array of integers")
    return items, start, t


def _shift(ctx, ops, cond, left: bool):
    arr, ctl, src = ops[:3]
    el = ctx.element(ctl)
    rising = cond and not el["EN"]
    el["EN"] = cond
    if not cond:
        el["DN"] = False
        return False
    if not rising:
        return True
    n = el["LEN"]
    items, start, t = _array_at(ctx, arr)
    width = {"SINT": 8, "INT": 16, "DINT": 32, "BOOL": 1}[t]
    if n <= 0 or start + (n + width - 1) // width > len(items):
        el["ER"] = True
        raise isa.PlcFault(0x0044, f"{arr}: length {n} does not fit the array")
    mask = (1 << width) - 1

    def get(k):
        return (int(items[start + k // width]) >> (k % width)) & 1

    def put(k, v):
        w = int(items[start + k // width]) & mask
        w = (w | (1 << (k % width))) if v else (w & ~(1 << (k % width)))
        if t == "BOOL":
            items[start + k] = bool(w)
        else:
            items[start + k // width] = w - (1 << width) if w >> (width - 1) else w
    incoming = 1 if ctx.bit(src) else 0
    order = range(n - 1, 0, -1) if left else range(n - 1)
    out = get(n - 1) if left else get(0)
    for k in order:
        put(k, get(k - 1) if left else get(k + 1))
    put(0 if left else n - 1, incoming)
    el["UL"] = bool(out)
    el["DN"] = True
    return True


SHIFT_OPS = ["array", "control", "bool", "value"]
SHIFT_LABELS = ["Array", "Control", "Source bit", "Length"]


@instruction("BSL", "Bit shift left", "Array", SHIFT_OPS, SHIFT_LABELS, on_download=_control_init(1, 3))
def bsl(ctx, ops, cond):
    return _shift(ctx, ops, cond, left=True)


@instruction("BSR", "Bit shift right", "Array", SHIFT_OPS, SHIFT_LABELS, on_download=_control_init(1, 3))
def bsr(ctx, ops, cond):
    return _shift(ctx, ops, cond, left=False)


def _step(op, el):
    """Advance POS on a rising edge; wrap to 1 after LEN."""
    n, pos = el["LEN"], el["POS"]
    if n <= 0 or pos < 0 or pos > n:
        el["ER"] = True
        raise isa.PlcFault(0x0042, f"{op}: position {pos} / length {n} is invalid")
    pos = 1 if pos >= n else pos + 1
    el["POS"] = pos
    el["DN"] = pos == n


def _seq(ctx, arr, el):
    items, start, _ = _array_at(ctx, arr)
    k = start + el["POS"]
    if k >= len(items):
        el["ER"] = True
        raise isa.PlcFault(0x0042, f"{arr}: position points past the end of the array")
    return items, k


SEQ_OPS = ["array", "value", "dest", "control", "value", "value"]


@instruction("SQO", "Sequencer output", "Array", SEQ_OPS, ["Array", "Mask", "Dest", "Control", "Length", "Position"],
             on_download=_control_init(3, 4, 5), optional=1)
def sqo(ctx, ops, cond):
    arr, mask_op, dest, ctl = ops[:4]
    el = ctx.element(ctl)
    if cond and not el["EN"]:
        _step(arr, el)
    el["EN"] = cond
    if cond:
        items, k = _seq(ctx, arr, el)
        mask = ctx.word(mask_op)
        ctx.store(dest, (ctx.word(dest) & ~mask) | (int(items[k]) & mask))
    return cond


@instruction("SQC", "Sequencer compare", "Array", ["array", "value", "value", "control", "value", "value"],
             ["Array", "Mask", "Source", "Control", "Length", "Position"], on_download=_control_init(3, 4, 5), optional=1)
def sqc(ctx, ops, cond):
    arr, mask_op, src, ctl = ops[:4]
    el = ctx.element(ctl)
    if cond and not el["EN"]:
        _step(arr, el)
    el["EN"] = cond
    if cond:
        items, k = _seq(ctx, arr, el)
        mask = ctx.word(mask_op)
        el["FD"] = (ctx.word(src) & mask) == (int(items[k]) & mask)
    return cond and el["FD"]


@instruction("SQL", "Sequencer load", "Array", ["array", "value", "control", "value", "value"],
             ["Array", "Source", "Control", "Length", "Position"], on_download=_control_init(2, 3, 4), optional=1)
def sql(ctx, ops, cond):
    arr, src, ctl = ops[:3]
    el = ctx.element(ctl)
    if cond and not el["EN"]:
        _step(arr, el)
        items, k = _seq(ctx, arr, el)
        items[k] = ctx.word(src)
    el["EN"] = cond
    return cond


@instruction("COP", "Copy array elements", "Array", ["array", "array", "value"], ["Source", "Dest", "Length"])
def cop(ctx, ops, cond):
    if cond:
        src, s0, _ = ctx.dt.array(ops[0])
        dst, d0, _ = ctx.dt.array(ops[1])
        n = int(ctx.value(ops[2]))
        if s0 + n > len(src) or d0 + n > len(dst):
            raise isa.PlcFault(0x0044, f"COP: {n} elements do not fit the arrays")
        dst[d0:d0 + n] = [type(dst[d0])(v) if not isinstance(v, dict) else dict(v) for v in src[s0:s0 + n]]
    return cond


@instruction("FLL", "Fill array elements", "Array", ["value", "array", "value"], ["Source", "Dest", "Length"])
def fll(ctx, ops, cond):
    if cond:
        dst, d0, _ = ctx.dt.array(ops[1])
        n = int(ctx.value(ops[2]))
        if d0 + n > len(dst):
            raise isa.PlcFault(0x0044, f"FLL: {n} elements do not fit the array")
        v = ctx.value(ops[0])
        for k in range(d0, d0 + n):
            dst[k] = type(dst[k])(v)
    return cond


# -- routines and blocks -------------------------------------------------------------------------------
@instruction("JSR", "Jump to subroutine (call a routine)", "Program Control", ["routine"], ["Routine"], output=True)
def jsr(ctx, ops, cond):
    if cond:
        ctx.call(ops[0])
    return cond


@instruction("RET", "Return", "Program Control", [], [], output=True, shape="coil", letter="RET")
def ret(ctx, ops, cond):
    if cond:
        raise isa.ReturnFromSubroutine()
    return cond


MAX_PARAMS = 8


@instruction("CALL", "Call a function or function block", "Program Control",
             ["block", *["param"] * MAX_PARAMS], ["Block", *[f"Parameter {k + 1}" for k in range(MAX_PARAMS)]],
             optional=MAX_PARAMS)
def call(ctx, ops, cond):
    """A function by name, a function block by its instance (`Motor1`, or `#Inner` inside a block).
    Parameters: `Start:=Button` (input) or `Running=>Lamp` (output). EN → ENO."""
    if not cond:
        return False
    inputs, outputs = {}, []
    for p in ops[1:]:
        name, arrow, operand = parse_param(p)
        if arrow == ":=":
            inputs[name] = ctx.value(operand)
        else:
            outputs.append((name, operand))
    result = ctx.call(ops[0], inputs)
    for name, operand in outputs:
        ctx.dt.write_word(operand, result[name.upper()])
    return True


@instruction("NOP", "No operation", "Program Control", [], [])
def nop(ctx, ops, cond):
    return cond


# -- PID -------------------------------------------------------------------------------------------
def _pid_prescan(ctx, ops):
    ctx.timer_marks.pop("pid:" + ops[0].lower(), None)
    ctx.pid_state.pop(ops[0].lower(), None)


@instruction("PID", "PID controller", "Process",
             ["pid", "value", "dest", "value_opt", "value_opt", "pid_opt", "bool_opt", "value_opt"],
             ["PID", "Process variable", "Control variable", "Setpoint", "Tieback", "Master loop", "Inhold bit",
              "Inhold value"], optional=5, on_prescan=_pid_prescan)
def pid_(ctx, ops, cond):
    """Runs every scan the rung is true. Optional: a setpoint (else the PID's SP member), a tieback
    the output follows in manual, a master loop whose output is this loop's setpoint (cascade),
    and an inhold bit that holds the output at the inhold value."""
    if not cond:
        ctx.timer_marks.pop("pid:" + ops[0].lower(), None)
        return False
    el = ctx.element(ops[0])
    opt = lambda k: ops[k] if len(ops) > k and not unused(ops[k]) else None
    if opt(3):
        el["SP"] = float(ctx.value(ops[3]))
    if opt(5):
        el["SP"] = float(ctx.element(ops[5])["CV"])
    tieback = float(ctx.value(ops[4])) if opt(4) else None
    hold = float(ctx.value(ops[7])) if opt(6) and opt(7) and ctx.bit(ops[6]) else None
    ctx.store(ops[2], run_pid(ctx, ops[0], float(ctx.value(ops[1])), tieback, hold))
    return True


def run_pid(ctx, instance: str, pv: float, tieback: float | None = None, hold: float | None = None) -> float:
    """One evaluation of a PID tag; returns CV (also used from structured text)."""
    el, key = ctx.element(instance), instance.lower()
    mark_key = "pid:" + key
    last = ctx.timer_marks.get(mark_key)
    ctx.timer_marks[mark_key] = ctx.now_ms
    dt = 0.0 if last is None else (ctx.now_ms - last) / 1000.0
    el["PV"] = pv
    state = ctx.pid_state.setdefault(key, {"CV": el["CV"], "I": el["CV"]})
    if hold is not None:
        state.update(CV=hold, I=hold)
        el["CV"] = hold
        return hold
    el["CV"] = pid.step(state, el["SP"], pv, dt, kc=el["KP"], ti=el["TI"], td=el["TD"],
                        out_min=el["MINO"], out_max=el["MAXO"], manual=el["MO"],
                        manual_value=tieback if tieback is not None else el["SO"], reverse=el["CA"])
    return el["CV"]


# -- operand checks ----------------------------------------------------------------------------------
KINDS = {
    "bool": "a BOOL tag or an I/O point, like Start or %I0.0",
    "value": "a number, a time like T#2s, or a numeric tag",
    "time": "a time like T#5s or 5000 (ms), or a tag",
    "dest": "a numeric tag, like Result or %QW0",
    "out": "a tag or output to write, like Lamp or %Q0.0",
    "timer": "a TIMER tag, like Delay",
    "counter": "a COUNTER tag, like Parts",
    "control": "a CONTROL tag, like Seq",
    "element": "a TIMER, COUNTER or CONTROL tag",
    "pid": "a PID tag, like LevelPID",
    "array": "an array element, like Steps[0]",
    "routine": "the name of a routine in this program",
    "block": "a function name or a function block instance, like Scale or Motor1",
    "param": "a parameter like Start:=Button or Running=>Lamp",
    "value_opt": "a number or numeric tag (optional)",
    "bool_opt": "a BOOL tag (optional)",
    "pid_opt": "a PID tag (optional)",
}
NUMBERS = ("SINT", "INT", "DINT", "REAL", "TIME")
WANT = {"bool": ("BOOL",), "value": ("BOOL", *NUMBERS), "time": NUMBERS, "dest": NUMBERS, "out": ("BOOL", *NUMBERS),
        "timer": ("TIMER",), "counter": ("COUNTER",), "control": ("CONTROL",),
        "element": ("TIMER", "COUNTER", "CONTROL"), "pid": ("PID",), "value_opt": ("BOOL", *NUMBERS),
        "bool_opt": ("BOOL",), "pid_opt": ("PID",)}
