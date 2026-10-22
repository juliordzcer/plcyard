"""S7-1200/1500 LAD instructions (TIA Portal), the set a learner meets first.

Contacts and coils keep the shared internal mnemonics (XIC, XIO, OTE, OTL/OTU drawn as S/R).
Boxes pass power on as ENO or Q, so a coil can follow a timer, compare or math box, as in TIA.
Math sets ENO false on overflow or divide by zero and leaves OUT unchanged on divide by zero.
IEC timers and counters keep their state in an instance tag (IEC_TIMER / IEC_COUNTER).
"""

from __future__ import annotations

import re

from ... import isa, pid
from ..base import parse_param
from .memory import STRUCTS, S7Error, S7Memory, parse_time

SPECS: dict[str, isa.Spec] = {}


def instruction(*a, **k):
    return isa.instruction(*a, into=SPECS, **k)


def literal(op: str):
    t = parse_time(op)
    if t is not None:
        return t
    low = op.strip().lower()
    if low in ("true", "false"):
        return int(low == "true")
    return isa.parse_literal(op)


class S7Context:
    def __init__(self, mem: S7Memory):
        self.dt = mem
        self.now_ms = 0.0
        self.timer_marks: dict[str, float] = {}
        self.pid_state: dict[str, dict] = {}
        self.call = lambda n: None

    def bit(self, op: str) -> bool:
        lit = literal(op)
        return bool(lit) if lit is not None else self.dt.read_bit(op)

    def set_bit(self, op: str, on: bool) -> None:
        self.dt.write_bit(op, on)

    def value(self, op: str):
        lit = literal(op)
        return lit if lit is not None else self.dt.read_word(op)

    def store(self, dest: str, value) -> bool:
        return self.dt.write_word(dest, value)

    def element(self, op: str) -> dict:
        return self.dt.element(op)


# -- contacts and coils ------------------------------------------------------------------------
@instruction("XIC", "Normally open contact", "Bit", ["bool"], ["Operand"])
def no(ctx, ops, cond):
    return cond and ctx.bit(ops[0])


@instruction("XIO", "Normally closed contact", "Bit", ["bool"], ["Operand"])
def nc(ctx, ops, cond):
    return cond and not ctx.bit(ops[0])


@instruction("OTE", "Assignment (coil)", "Bit", ["bool"], ["Operand"], output=True)
def coil(ctx, ops, cond):
    ctx.set_bit(ops[0], cond)
    return cond


@instruction("OTL", "Set output", "Bit", ["bool"], ["Operand"], output=True, letter="S")
def set_(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], True)
    return cond


@instruction("OTU", "Reset output", "Bit", ["bool"], ["Operand"], output=True, letter="R")
def reset(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], False)
    return cond


def _edge(rising: bool):
    def run(ctx, ops, cond):
        now, before = ctx.bit(ops[0]), ctx.bit(ops[1])
        ctx.set_bit(ops[1], now)
        return cond and ((now and not before) if rising else (before and not now))
    return run


def _edge_prescan(ctx, ops):
    ctx.set_bit(ops[1], ctx.bit(ops[0]))      # no edge on the first scan


instruction("P", "Scan operand for positive edge", "Bit", ["bool", "bool"], ["Operand", "Edge memory bit"],
            on_prescan=_edge_prescan, shape="small", letter="P")(_edge(True))
instruction("N", "Scan operand for negative edge", "Bit", ["bool", "bool"], ["Operand", "Edge memory bit"],
            on_prescan=_edge_prescan, shape="small", letter="N")(_edge(False))


# -- IEC timers ---------------------------------------------------------------------------------------
def _elapsed(ctx, key) -> int:
    mark = ctx.timer_marks.get(key)
    ctx.timer_marks[key] = ctx.now_ms
    return 0 if mark is None else int(ctx.now_ms - mark)


def _timer_prescan(ctx, ops):
    ctx.element(ops[0]).update(IN=False, Q=False, ET=0)
    ctx.timer_marks.pop(ops[0].lower(), None)


def _pt(ctx, ops, el) -> int:
    el["PT"] = int(ctx.value(ops[1]))
    return el["PT"]


@instruction("TON", "On delay (TON)", "Timer/Counter", ["timer", "time"], ["Instance", "PT"],
             on_prescan=_timer_prescan)
def ton(ctx, ops, cond):
    el, key = ctx.element(ops[0]), ops[0].lower()
    pt = _pt(ctx, ops, el)
    if cond:
        dt = _elapsed(ctx, key) if el["IN"] else (ctx.timer_marks.__setitem__(key, ctx.now_ms) or 0)
        el["ET"] = min(el["ET"] + dt, max(pt, 0))
        el["Q"] = el["ET"] >= pt
    else:
        el.update(ET=0, Q=False)
        ctx.timer_marks.pop(key, None)
    el["IN"] = cond
    return el["Q"]


@instruction("TOF", "Off delay (TOF)", "Timer/Counter", ["timer", "time"], ["Instance", "PT"],
             on_prescan=_timer_prescan)
def tof(ctx, ops, cond):
    el, key = ctx.element(ops[0]), ops[0].lower()
    pt = _pt(ctx, ops, el)
    if cond:
        el.update(ET=0, Q=True)
        ctx.timer_marks.pop(key, None)
    elif el["Q"]:
        dt = _elapsed(ctx, key) if not el["IN"] else (ctx.timer_marks.__setitem__(key, ctx.now_ms) or 0)
        el["ET"] = min(el["ET"] + dt, max(pt, 0))
        el["Q"] = el["ET"] < pt
    el["IN"] = cond
    return el["Q"]


@instruction("TP", "Pulse (TP)", "Timer/Counter", ["timer", "time"], ["Instance", "PT"],
             on_prescan=_timer_prescan)
def tp(ctx, ops, cond):
    el, key = ctx.element(ops[0]), ops[0].lower()
    pt = _pt(ctx, ops, el)
    if el["Q"]:                                     # a pulse runs for PT whatever IN does
        el["ET"] = min(el["ET"] + _elapsed(ctx, key), pt)
        el["Q"] = el["ET"] < pt
    elif cond and not el["IN"] and el["ET"] == 0:   # rising edge while idle starts a pulse
        el["Q"] = True
        ctx.timer_marks[key] = ctx.now_ms
    if not cond and not el["Q"]:                    # pulse over and IN low: ET back to 0
        el["ET"] = 0
        ctx.timer_marks.pop(key, None)
    el["IN"] = cond
    return el["Q"]


# -- IEC counters ----------------------------------------------------------------------------------------
def _counter_prescan(ctx, ops):
    el = ctx.element(ops[0])
    el["CU"] = el["CD"] = True                      # no count on the first scan


@instruction("CTU", "Count up (CTU)", "Timer/Counter", ["counter", "value", "bool"], ["Instance", "PV", "R"],
             optional=1, on_prescan=_counter_prescan)
def ctu(ctx, ops, cond):
    el = ctx.element(ops[0])
    el["PV"] = int(ctx.value(ops[1]))
    if len(ops) > 2 and ctx.bit(ops[2]):
        el["CV"] = 0
    elif cond and not el["CU"] and el["CV"] < 32767:
        el["CV"] += 1
    el["CU"] = cond
    el["Q"] = el["CV"] >= el["PV"]
    return el["Q"]


@instruction("CTD", "Count down (CTD)", "Timer/Counter", ["counter", "value", "bool"], ["Instance", "PV", "LD"],
             optional=1, on_prescan=_counter_prescan)
def ctd(ctx, ops, cond):
    el = ctx.element(ops[0])
    el["PV"] = int(ctx.value(ops[1]))
    if len(ops) > 2 and ctx.bit(ops[2]):
        el["CV"] = el["PV"]
    elif cond and not el["CD"] and el["CV"] > -32768:
        el["CV"] -= 1
    el["CD"] = cond
    el["Q"] = el["CV"] <= 0
    return el["Q"]


@instruction("RESET_TIMER", "Reset timer or counter", "Timer/Counter", ["element"], ["Instance"], output=True)
def res(ctx, ops, cond):
    if cond:
        el = ctx.element(ops[0])
        for k in el:
            if k not in ("PT", "PV"):
                el[k] = False if isinstance(el[k], bool) else 0
        ctx.timer_marks.pop(ops[0].lower(), None)
    return cond


# -- compare ------------------------------------------------------------------------------------------------
def _cmp(m, title, test):
    @instruction(m, title, "Compare", ["value", "value"], ["IN1", "IN2"])
    def run(ctx, ops, cond):
        return cond and test(ctx.value(ops[0]), ctx.value(ops[1]))
    return run


_cmp("CMP==", "Equal", lambda a, b: a == b)
_cmp("CMP<>", "Not equal", lambda a, b: a != b)
_cmp("CMP<", "Less than", lambda a, b: a < b)
_cmp("CMP<=", "Less or equal", lambda a, b: a <= b)
_cmp("CMP>", "Greater than", lambda a, b: a > b)
_cmp("CMP>=", "Greater or equal", lambda a, b: a >= b)


@instruction("IN_RANGE", "Value within range", "Compare", ["value", "value", "value"], ["MIN", "VAL", "MAX"])
def in_range(ctx, ops, cond):
    lo, v, hi = (ctx.value(o) for o in ops)
    return cond and lo <= v <= hi


# -- math and move ---------------------------------------------------------------------------------------------
def _math(m, title, fn):
    @instruction(m, title, "Math", ["value", "value", "dest"], ["IN1", "IN2", "OUT"])
    def run(ctx, ops, cond):
        if not cond:
            return False
        try:
            result = fn(ctx.value(ops[0]), ctx.value(ops[1]), ctx.dt.type_of(ops[2]))
        except ZeroDivisionError:
            return False                             # ENO = 0, OUT unchanged
        return not ctx.store(ops[2], result)         # ENO = 0 on overflow
    return run


def _div(a, b, t):
    if t == "Real" or isinstance(a, float) or isinstance(b, float):
        return a / b
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def _mod(a, b, t):
    if b == 0:
        raise ZeroDivisionError
    return a - _div(a, b, "Int") * b


_math("ADD", "Add", lambda a, b, t: a + b)
_math("SUB", "Subtract", lambda a, b, t: a - b)
_math("MUL", "Multiply", lambda a, b, t: a * b)
_math("DIV", "Divide", _div)
_math("MOD", "Modulo", _mod)


@instruction("MOVE", "Move value", "Move/Logical", ["value", "dest"], ["IN", "OUT1"])
def move(ctx, ops, cond):
    if cond:
        ctx.store(ops[1], ctx.value(ops[0]))
    return cond


@instruction("NORM_X", "Normalize", "Math", ["value", "value", "value", "dest"], ["MIN", "VALUE", "MAX", "OUT"])
def norm_x(ctx, ops, cond):
    if not cond:
        return False
    lo, v, hi = (float(ctx.value(o)) for o in ops[:3])
    if hi == lo:
        return False
    ctx.store(ops[3], (v - lo) / (hi - lo))
    return True


@instruction("SCALE_X", "Scale", "Math", ["value", "value", "value", "dest"], ["MIN", "VALUE", "MAX", "OUT"])
def scale_x(ctx, ops, cond):
    if not cond:
        return False
    lo, v, hi = (float(ctx.value(o)) for o in ops[:3])
    return not ctx.store(ops[3], v * (hi - lo) + lo)


# -- PID ----------------------------------------------------------------------------------------------------------
def _pid_prescan(ctx, ops):
    ctx.timer_marks.pop("pid:" + ops[0].lower(), None)
    ctx.pid_state.pop(ops[0].lower(), None)


@instruction("PID_Compact", "Universal PID controller", "Process", ["pid", "value", "value", "dest"],
             ["Instance", "Setpoint", "Input", "Out"], on_prescan=_pid_prescan)
def pid_compact(ctx, ops, cond):
    """Simplified PID_Compact: dependent gains (Gain, Ti, Td in seconds), Output in %. Runs every scan
    the box is enabled (on a real CPU it sits in a cyclic interrupt OB)."""
    if not cond:
        ctx.timer_marks.pop("pid:" + ops[0].lower(), None)
        return False
    ctx.store(ops[3], run_pid_compact(ctx, ops[0], float(ctx.value(ops[1])), float(ctx.value(ops[2]))))
    return True


def run_pid_compact(ctx, instance: str, setpoint: float, value: float) -> float:
    """One evaluation of a PID_Compact instance; returns Output (also used from structured text)."""
    el, key = ctx.element(instance), instance.lower()
    mark_key = "pid:" + key
    last = ctx.timer_marks.get(mark_key)
    ctx.timer_marks[mark_key] = ctx.now_ms
    dt = 0.0 if last is None else (ctx.now_ms - last) / 1000.0
    el["Setpoint"], el["Input"] = setpoint, value
    state = ctx.pid_state.setdefault(key, {"CV": el["Output"], "I": el["Output"]})
    el["Output"] = pid.step(state, setpoint, value, dt, kc=el["Gain"], ti=el["Ti"], td=el["Td"],
                            out_min=el["OutputLowerLimit"], out_max=el["OutputUpperLimit"],
                            manual=el["ManualEnable"], manual_value=el["ManualValue"], reverse=el["InvertControl"])
    return el["Output"]


# -- block calls ----------------------------------------------------------------------------------------------------
MAX_PARAMS = 8


@instruction("CALL", "Call a function (FC) or function block (FB)", "Program Control",
             ["block", *["param"] * MAX_PARAMS], ["Block", *[f"Parameter {k + 1}" for k in range(MAX_PARAMS)]],
             optional=MAX_PARAMS)
def call(ctx, ops, cond):
    """FC by name, FB by its instance (`Motor_DB`, or `#Inner` inside a block). Parameters as in a
    TIA box: `Start := Button` (input) or `Running => Lamp` (output). EN → ENO."""
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
        ctx.store(operand, result[name.upper()])
    return True


@instruction("RET", "Return", "Program Control", [], [], output=True, shape="coil", letter="RET")
def ret(ctx, ops, cond):
    if cond:
        raise isa.ReturnFromSubroutine()
    return cond


# -- operand checks ---------------------------------------------------------------------------------------------
KINDS = {
    "bool": "a Bool tag or a bit, like Start or %I0.0",
    "value": "a number, time (T#5s) or numeric tag, like 100 or %MW10",
    "time": "a time like T#5s or T#500ms, or a Time tag",
    "dest": "a numeric tag or address, like Result or %MW10",
    "timer": "an IEC_TIMER instance tag, like Delay",
    "counter": "an IEC_COUNTER instance tag, like Parts",
    "element": "an IEC_TIMER or IEC_COUNTER instance",
    "pid": "a PID_Compact instance tag, like LevelPID",
    "block": "a function (FC) name or a function block instance (its DB), like Scale or Motor_DB",
    "param": "a parameter like Start := Button or Running => Lamp",
}
WANT = {"bool": ("Bool",), "value": ("Bool", "Byte", "Int", "DInt", "Real", "Time"), "time": ("Time", "DInt", "Int"),
        "dest": ("Byte", "Int", "DInt", "Real", "Time"), "timer": ("IEC_TIMER",), "counter": ("IEC_COUNTER",),
        "element": ("IEC_TIMER", "IEC_COUNTER"), "pid": ("PID_Compact",)}


def check_operand(mem: S7Memory, kind: str, op: str) -> str | None:
    if kind == "block":
        return None if re.fullmatch(r'#?"?[A-Za-z_][A-Za-z0-9_]*"?(?:\.[A-Za-z_]\w*|\[[^\]]+\])*', op.strip()) \
            else f"{op!r} is not a block name"
    if kind == "param":
        p = parse_param(op)
        if p is None:
            return f"write a parameter as Name := value (input) or Name => tag (output), not {op!r}"
        if p[1] == ":=":
            return check_operand(mem, "value", p[2])
        return check_operand(mem, "out", p[2])
    if kind == "out":
        try:
            r = mem.ref(op, True)
        except S7Error as e:
            return str(e)
        if not mem.is_scalar(r.type):
            return f"{op} is a {r.type}; pass one of its members"
        return f"{op} is read-only" if r.area == "I" or r.tag == "FirstScan" else None
    lit = literal(op)
    if lit is not None:
        if kind == "value" or (kind == "time" and parse_time(op) is not None) or (kind == "bool" and op.lower() in ("true", "false")):
            return None
        if kind == "time":
            return f"{op} is not a time; write it like T#5s or T#500ms"
        return f"{op} is a constant; needs {KINDS[kind]}"
    try:
        r = mem.ref(op, True)
    except S7Error as e:
        if kind == "time" and op[:1].isdigit():
            return f"{op} is not a time; write it like T#5s or T#500ms"
        return str(e)
    if r.type not in WANT[kind]:
        return f"{op} is a {r.type}; needs {KINDS[kind]}"
    if kind == "dest" and (r.area == "I" or r.tag == "FirstScan"):
        return f"{op} is read-only; write to %Q, %M or a tag"
    return None
