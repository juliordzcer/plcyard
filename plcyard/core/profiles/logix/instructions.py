"""Logix ladder instructions (Rockwell 1756-RM003), the subset a learner meets first.

Timers count in milliseconds (PRE and ACC are DINT ms). Integer math wraps to the destination
type and sets S:V; divide by zero stores the largest value with the sign of the dividend and sets
S:V (a minor fault on a real controller, not a stop).
"""

from __future__ import annotations

from ... import isa
from .tags import TagError, TagTable

SPECS: dict[str, isa.Spec] = {}


def instruction(*a, **k):
    return isa.instruction(*a, into=SPECS, **k)


def literal(op: str):
    return isa.parse_literal(op)


class LogixContext:
    def __init__(self, tags: TagTable):
        self.dt = tags
        self.now_ms = 0.0
        self.timer_marks: dict[str, float] = {}
        self.call = lambda n: None

    def bit(self, op: str) -> bool:
        return self.dt.read_bit(op)

    def set_bit(self, op: str, on: bool) -> None:
        self.dt.write_bit(op, on)

    def value(self, op: str):
        lit = literal(op)
        return lit if lit is not None else self.dt.read_word(op)

    def store(self, dest: str, value) -> None:
        if self.dt.write_word(dest, value):
            self.dt.write_bit("S:V", True)

    def element(self, op: str) -> dict:
        return self.dt.element(op)


# -- bit ---------------------------------------------------------------------------------------
@instruction("XIC", "Examine if closed", "Bit", ["bool"], ["Bit"])
def xic(ctx, ops, cond):
    return cond and ctx.bit(ops[0])


@instruction("XIO", "Examine if open", "Bit", ["bool"], ["Bit"])
def xio(ctx, ops, cond):
    return cond and not ctx.bit(ops[0])


@instruction("OTE", "Output energize", "Bit", ["bool"], ["Bit"], output=True)
def ote(ctx, ops, cond):
    ctx.set_bit(ops[0], cond)
    return cond


@instruction("OTL", "Output latch", "Bit", ["bool"], ["Bit"], output=True)
def otl(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], True)
    return cond


@instruction("OTU", "Output unlatch", "Bit", ["bool"], ["Bit"], output=True)
def otu(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], False)
    return cond


def _storage_on(ctx, ops):
    ctx.set_bit(ops[0], True)      # prescan: no false trigger on the first scan


@instruction("ONS", "One shot", "Bit", ["bool"], ["Storage bit"], on_prescan=_storage_on,
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


# -- timers and counters -----------------------------------------------------------------------
def _init_element(ctx, ops):
    el = ctx.element(ops[0])
    el["PRE"] = int(ctx.value(ops[1]))
    if len(ops) > 2:
        el["ACC"] = int(ctx.value(ops[2]))


def _check(el, op):
    if el["PRE"] < 0 or el["ACC"] < 0:
        raise isa.PlcFault(0x0422, f"{op}: negative preset or accumulator")


def _elapsed(ctx, key) -> int:
    """Whole ms since this timer was last evaluated; first evaluation returns 0."""
    mark = ctx.timer_marks.get(key)
    ctx.timer_marks[key] = ctx.now_ms
    return 0 if mark is None else int(ctx.now_ms - mark)


def _timer_off(ctx, ops):
    el = ctx.element(ops[0])
    el.update(EN=False, TT=False, DN=False, ACC=0)
    ctx.timer_marks.pop(ops[0].lower(), None)


@instruction("TON", "Timer on delay", "Timer/Counter", ["timer", "value", "value"],
             ["Timer", "Preset", "Accum"], output=True, on_download=_init_element, on_prescan=_timer_off)
def ton(ctx, ops, cond):
    el = ctx.element(ops[0])
    _check(el, ops[0])
    key = ops[0].lower()
    if not cond:
        _timer_off(ctx, ops)
        return cond
    dt = _elapsed(ctx, key) if el["EN"] else (ctx.timer_marks.__setitem__(key, ctx.now_ms) or 0)
    if not el["DN"]:
        el["ACC"] = min(el["ACC"] + dt, max(el["PRE"], el["ACC"]))
    el["EN"] = True
    el["DN"] = el["ACC"] >= el["PRE"]
    el["TT"] = not el["DN"]
    return cond


def _tof_prescan(ctx, ops):
    el = ctx.element(ops[0])
    el.update(EN=False, TT=False, DN=False, ACC=el["PRE"])
    ctx.timer_marks.pop(ops[0].lower(), None)


@instruction("TOF", "Timer off delay", "Timer/Counter", ["timer", "value", "value"],
             ["Timer", "Preset", "Accum"], output=True, on_download=_init_element, on_prescan=_tof_prescan)
def tof(ctx, ops, cond):
    el = ctx.element(ops[0])
    _check(el, ops[0])
    key = ops[0].lower()
    if cond:
        el.update(EN=True, TT=False, DN=True, ACC=0)
        ctx.timer_marks.pop(key, None)
        return cond
    if el["EN"]:                                   # falling edge: start timing
        el["EN"] = False
        ctx.timer_marks[key] = ctx.now_ms
    if el["DN"]:
        el["ACC"] = min(el["ACC"] + _elapsed(ctx, key), el["PRE"])
        done = el["ACC"] >= el["PRE"]
        el["TT"] = not done
        el["DN"] = not done
    return cond


def _rto_prescan(ctx, ops):
    el = ctx.element(ops[0])
    el.update(EN=False, TT=False)
    ctx.timer_marks.pop(ops[0].lower(), None)


@instruction("RTO", "Retentive timer on", "Timer/Counter", ["timer", "value", "value"],
             ["Timer", "Preset", "Accum"], output=True, on_download=_init_element, on_prescan=_rto_prescan)
def rto(ctx, ops, cond):
    el = ctx.element(ops[0])
    _check(el, ops[0])
    key = ops[0].lower()
    if not cond:
        el.update(EN=False, TT=False)
        ctx.timer_marks.pop(key, None)
        return cond
    dt = _elapsed(ctx, key) if el["EN"] else (ctx.timer_marks.__setitem__(key, ctx.now_ms) or 0)
    if not el["DN"]:
        el["ACC"] = min(el["ACC"] + dt, max(el["PRE"], el["ACC"]))
    el["EN"] = True
    el["DN"] = el["ACC"] >= el["PRE"]
    el["TT"] = not el["DN"]
    return cond


def _counter_prescan(edge):
    def fn(ctx, ops):
        ctx.element(ops[0])[edge] = True          # no false count on the first scan
    return fn


def _count(edge, step):
    def run(ctx, ops, cond):
        el = ctx.element(ops[0])
        if cond and not el[edge]:
            acc = el["ACC"] + step
            if acc > 2147483647:
                acc, el["OV"] = -2147483648, True
            elif acc < -2147483648:
                acc, el["UN"] = 2147483647, True
            el["ACC"] = acc
        el[edge] = cond
        el["DN"] = el["ACC"] >= el["PRE"]
        return cond
    return run


instruction("CTU", "Count up", "Timer/Counter", ["counter", "value", "value"], ["Counter", "Preset", "Accum"],
            output=True, on_download=_init_element, on_prescan=_counter_prescan("CU"))(_count("CU", 1))
instruction("CTD", "Count down", "Timer/Counter", ["counter", "value", "value"], ["Counter", "Preset", "Accum"],
            output=True, on_download=_init_element, on_prescan=_counter_prescan("CD"))(_count("CD", -1))


@instruction("RES", "Reset", "Timer/Counter", ["element"], ["Timer or counter"], output=True)
def res(ctx, ops, cond):
    if cond:
        el = ctx.element(ops[0])
        for k in el:
            if k != "PRE":
                el[k] = False if isinstance(el[k], bool) else 0
        ctx.timer_marks.pop(ops[0].lower(), None)
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


@instruction("LIM", "Limit test", "Compare", ["value", "value", "value"], ["Low limit", "Test", "High limit"])
def lim(ctx, ops, cond):
    lo, t, hi = (ctx.value(o) for o in ops)
    return cond and ((lo <= t <= hi) if lo <= hi else (t >= lo or t <= hi))


# -- math and move ---------------------------------------------------------------------------------
def _math(m, title, fn):
    @instruction(m, title, "Math", ["value", "value", "dest"], ["Source A", "Source B", "Dest"], output=True)
    def run(ctx, ops, cond):
        if cond:
            ctx.store(ops[2], fn(ctx, ctx.value(ops[0]), ctx.value(ops[1]), ops[2]))
        return cond
    return run


def _div(ctx, a, b, dest):
    if b == 0:
        ctx.set_bit("S:V", True)
        if ctx.dt.ref(dest).type == "REAL":
            return float("inf") if a >= 0 else float("-inf")
        return 2147483647 if a >= 0 else -2147483648
    if isinstance(a, float) or isinstance(b, float) or ctx.dt.ref(dest).type == "REAL":
        return a / b
    q = abs(a) // abs(b)                     # integer division truncates toward zero
    return q if (a >= 0) == (b >= 0) else -q


_math("ADD", "Add", lambda ctx, a, b, d: a + b)
_math("SUB", "Subtract", lambda ctx, a, b, d: a - b)
_math("MUL", "Multiply", lambda ctx, a, b, d: a * b)
_math("DIV", "Divide", _div)


@instruction("MOV", "Move", "Move/Logical", ["value", "dest"], ["Source", "Dest"], output=True)
def mov(ctx, ops, cond):
    if cond:
        ctx.store(ops[1], ctx.value(ops[0]))
    return cond


@instruction("CLR", "Clear", "Move/Logical", ["dest"], ["Dest"], output=True)
def clr(ctx, ops, cond):
    if cond:
        ctx.store(ops[0], 0)
    return cond


@instruction("SCP", "Scale with parameters", "Math",
             ["value", "value", "value", "value", "value", "dest"],
             ["Input", "Input min", "Input max", "Scaled min", "Scaled max", "Output"], output=True)
def scp(ctx, ops, cond):
    if cond:
        x, x0, x1, y0, y1 = (float(ctx.value(o)) for o in ops[:5])
        if x1 == x0:
            ctx.set_bit("S:V", True)
        else:
            ctx.store(ops[5], y0 + (x - x0) * (y1 - y0) / (x1 - x0))
    return cond


@instruction("NOP", "No operation", "Program Control", [], [])
def nop(ctx, ops, cond):
    return cond


# -- operand checks ----------------------------------------------------------------------------------
KINDS = {
    "bool": "a BOOL tag or a bit, like Start or Local:1:I.Data.0",
    "value": "a number or a numeric tag, like 100 or Count",
    "dest": "a numeric tag, like Result",
    "timer": "a TIMER tag, like Delay",
    "counter": "a COUNTER tag, like Parts",
    "element": "a TIMER or COUNTER tag",
}
WANT = {"bool": ("BOOL",), "value": ("BOOL", "INT", "DINT", "REAL"), "dest": ("INT", "DINT", "REAL"),
        "timer": ("TIMER",), "counter": ("COUNTER",), "element": ("TIMER", "COUNTER")}


def check_operand(tags: TagTable, kind: str, op: str) -> str | None:
    if kind == "value" and literal(op) is not None:
        return None
    try:
        r = tags.ref(op)
    except TagError as e:
        return str(e)
    if r.type not in WANT[kind]:
        return f"{op} is a {r.type}; needs {KINDS[kind]}"
    if kind == "dest" and r.base in ("S:FS", "S:V"):
        return f"{op} is read-only"
    return None
