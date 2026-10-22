"""Function block diagram: blocks with pins, wires between pins, and the execution order.

A pin that is not wired may carry an operand instead, as in most FBD editors: an input reads a tag,
an address or a constant (`%I0.0`, `Level`, `T#2s`, `5`); an output writes its value to a tag or
an address. Timers, counters and PID blocks work on their instance tag, the same instructions the
ladder and structured text use, so a TON behaves the same in all three languages.

Execution order: data flow (a block runs after every block that feeds it), then top to bottom and
left to right. In a feedback loop the value from the previous scan is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .isa import PlcFault


@dataclass
class Pin:
    name: str
    type: str            # BOOL, NUM (any number), ANY


@dataclass(frozen=True)
class BlockType:
    name: str
    title: str
    family: str
    inputs: tuple            # (Pin, …)
    outputs: tuple
    instance: str = ""       # tag type of the instance (TIMER, COUNTER, PID) or ""
    variable_inputs: bool = False


def _p(spec: str) -> tuple:
    out = []
    for item in spec.split():
        name, _, t = item.partition(":")
        out.append(Pin(name, t or "BOOL"))
    return tuple(out)


LIBRARY: dict[str, BlockType] = {}


def _block(name, title, family, ins, outs, instance="", variable=False):
    LIBRARY[name] = BlockType(name, title, family, _p(ins), _p(outs), instance, variable)


_block("AND", "AND", "Bit logic", "IN1 IN2", "OUT", variable=True)
_block("OR", "OR", "Bit logic", "IN1 IN2", "OUT", variable=True)
_block("XOR", "Exclusive OR", "Bit logic", "IN1 IN2", "OUT")
_block("NOT", "NOT", "Bit logic", "IN", "OUT")
_block("SR", "Set dominant flip-flop", "Bit logic", "S1 R", "Q1")
_block("RS", "Reset dominant flip-flop", "Bit logic", "S R1", "Q1")
_block("R_TRIG", "Rising edge", "Bit logic", "CLK", "Q")
_block("F_TRIG", "Falling edge", "Bit logic", "CLK", "Q")
for _t, _title in (("TON", "On delay"), ("TOF", "Off delay"), ("TP", "Pulse"), ("RTO", "Retentive on delay")):
    _block(_t, _title, "Timers", "IN PT:NUM" + (" R" if _t == "RTO" else ""), "Q ET:NUM", "TIMER")
_block("CTU", "Count up", "Counters", "CU R PV:NUM", "Q CV:NUM", "COUNTER")
_block("CTD", "Count down", "Counters", "CD LD PV:NUM", "Q CV:NUM", "COUNTER")
for _c, _title in (("EQ", "Equal"), ("NE", "Not equal"), ("LT", "Less than"), ("LE", "Less or equal"),
                   ("GT", "Greater than"), ("GE", "Greater or equal")):
    _block(_c, _title, "Compare", "IN1:NUM IN2:NUM", "OUT")
_block("LIMIT", "Limit to a range", "Compare", "MN:NUM IN:NUM MX:NUM", "OUT:NUM")
for _m, _title in (("ADD", "Add"), ("SUB", "Subtract"), ("MUL", "Multiply"), ("DIV", "Divide"), ("MOD", "Modulo"),
                   ("MAX", "Maximum"), ("MIN", "Minimum")):
    _block(_m, _title, "Math", "IN1:NUM IN2:NUM", "OUT:NUM", variable=_m in ("ADD", "MUL", "MAX", "MIN"))
_block("ABS", "Absolute value", "Math", "IN:NUM", "OUT:NUM")
_block("SQRT", "Square root", "Math", "IN:NUM", "OUT:NUM")
_block("MOVE", "Move", "Move", "IN:NUM", "OUT:NUM")
_block("SEL", "Select", "Move", "G IN0:NUM IN1:NUM", "OUT:NUM")
_block("TO_BCD", "Integer to BCD", "Move", "IN:NUM", "OUT:NUM")
_block("FROM_BCD", "BCD to integer", "Move", "IN:NUM", "OUT:NUM")
_block("SCALE", "Scale a range", "Move", "IN:NUM IN_MIN:NUM IN_MAX:NUM OUT_MIN:NUM OUT_MAX:NUM", "OUT:NUM")
_block("PID", "PID controller", "Process", "PV:NUM SP:NUM", "CV:NUM", "PID")

FAMILIES = ["Bit logic", "Timers", "Counters", "Compare", "Math", "Move", "Process"]


@dataclass
class Block:
    id: int
    type: str
    x: float = 0.0
    y: float = 0.0
    instance: str = ""                                   # instance tag for timers, counters, PID
    operands: dict[str, str] = field(default_factory=dict)   # pin name → operand (unwired pins)
    inputs: int = 0                                      # extra inputs of AND/OR/ADD… (0 = the default 2)

    def type_(self) -> BlockType:
        return LIBRARY[self.type]

    def input_pins(self) -> list[Pin]:
        bt = self.type_()
        pins = list(bt.inputs)
        if bt.variable_inputs and self.inputs > len(pins):
            t = pins[0].type
            pins += [Pin(f"IN{k + 1}", t) for k in range(len(pins), self.inputs)]
        return pins

    def output_pins(self) -> list[Pin]:
        return list(self.type_().outputs)


@dataclass
class Wire:
    src: int            # block id
    src_pin: str
    dst: int
    dst_pin: str


@dataclass
class Diagram:
    blocks: list[Block] = field(default_factory=list)
    wires: list[Wire] = field(default_factory=list)

    def block(self, bid: int) -> Block | None:
        return next((b for b in self.blocks if b.id == bid), None)

    def next_id(self) -> int:
        return max((b.id for b in self.blocks), default=0) + 1

    def wire_into(self, bid: int, pin: str) -> Wire | None:
        return next((w for w in self.wires if w.dst == bid and w.dst_pin == pin), None)

    def order(self) -> list[Block]:
        """Data flow first, then top to bottom, left to right; feedback loops keep last scan's value."""
        pending = sorted(self.blocks, key=lambda b: (b.y, b.x, b.id))
        done: set[int] = set()
        out: list[Block] = []
        while pending:
            ready = next((b for b in pending if all(w.src in done or w.src == b.id or self.block(w.src) is None
                                                    for w in self.wires if w.dst == b.id)), None)
            if ready is None:                            # a loop: take the first one in reading order
                ready = pending[0]
            pending.remove(ready)
            done.add(ready.id)
            out.append(ready)
        return out

    # -- file form ----------------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"blocks": [{"id": b.id, "type": b.type, "x": b.x, "y": b.y,
                            **({"instance": b.instance} if b.instance else {}),
                            **({"operands": b.operands} if b.operands else {}),
                            **({"inputs": b.inputs} if b.inputs else {})} for b in self.blocks],
                "wires": [[w.src, w.src_pin, w.dst, w.dst_pin] for w in self.wires]}

    @classmethod
    def from_dict(cls, d: dict) -> "Diagram":
        blocks = []
        for b in d.get("blocks", []):
            if b.get("type") not in LIBRARY:
                raise ValueError(f"unknown function block {b.get('type')!r}")
            blocks.append(Block(int(b["id"]), b["type"], float(b.get("x", 0)), float(b.get("y", 0)),
                                b.get("instance", ""), dict(b.get("operands", {})), int(b.get("inputs", 0))))
        wires = [Wire(int(w[0]), str(w[1]), int(w[2]), str(w[3])) for w in d.get("wires", [])]
        return cls(blocks, wires)


# -- checks ----------------------------------------------------------------------------------------
def check(diagram: Diagram, memory, operand_problem) -> list[tuple[int, str]]:
    """Problems (block id, message). `operand_problem(kind, text)` checks an operand as the ladder
    does ("bool", "value", "out")."""
    problems = []
    ids = {b.id for b in diagram.blocks}
    for w in diagram.wires:
        if w.src not in ids or w.dst not in ids:
            problems.append((w.dst, "a wire ends on a block that is gone"))
    seen_inputs = set()
    for w in diagram.wires:
        if (w.dst, w.dst_pin) in seen_inputs:
            problems.append((w.dst, f"input {w.dst_pin} has two wires"))
        seen_inputs.add((w.dst, w.dst_pin))
    for b in diagram.blocks:
        bt = b.type_()
        name = f"{b.type} block {b.id}"
        if bt.instance:
            if not b.instance:
                problems.append((b.id, f"{name}: needs a {bt.instance} tag as its instance"))
            else:
                try:
                    t = memory.ref(b.instance, True).type
                except Exception as e:
                    problems.append((b.id, f"{name}: {e}"))
                else:
                    if t != bt.instance:
                        problems.append((b.id, f"{name}: {b.instance} is a {t}; needs a {bt.instance}"))
        pins = {p.name: p for p in b.input_pins()}
        outs = {p.name: p for p in b.output_pins()}
        for pin, text in b.operands.items():
            if not text.strip():
                continue
            if pin in pins:
                msg = operand_problem("bool" if pins[pin].type == "BOOL" else "value", text)
            elif pin in outs:
                msg = operand_problem("out", text)
            else:
                msg = f"has no pin {pin}"
            if msg:
                problems.append((b.id, f"{name} {pin}: {msg}"))
        for w in diagram.wires:
            if w.dst == b.id and w.dst_pin not in pins:
                problems.append((b.id, f"{name}: has no input {w.dst_pin}"))
            elif w.dst == b.id and diagram.block(w.src) is not None:
                src = next((p for p in diagram.block(w.src).output_pins() if p.name == w.src_pin), None)
                if src is not None and (src.type == "BOOL") != (pins[w.dst_pin].type == "BOOL"):
                    problems.append((b.id, f"{name}: {w.dst_pin} takes a {'BOOL' if pins[w.dst_pin].type == 'BOOL' else 'number'}, "
                                           f"the wire brings a {'BOOL' if src.type == 'BOOL' else 'number'}"))
            if w.src == b.id and w.src_pin not in outs:
                problems.append((b.id, f"{name}: has no output {w.src_pin}"))
    return problems


# -- execution -------------------------------------------------------------------------------------------
class Runner:
    """Runs a diagram once per scan. `state` keeps edge memories, flip-flops and last-scan values."""

    def __init__(self, ctx, specs, run_pid, state: dict):
        self.ctx, self.specs, self.run_pid, self.state = ctx, specs, run_pid, state

    def run(self, diagram: Diagram, fix=lambda t: t, values: dict | None = None) -> dict:
        """Evaluate every block; returns {(block id, pin): value} of this scan (for the live view)."""
        self.diagram = diagram
        vals = self.state.setdefault("values", {})
        for b in diagram.order():
            ins = {}
            for p in b.input_pins():
                w = diagram.wire_into(b.id, p.name)
                if w is not None:
                    v = vals.get((w.src, w.src_pin), False if p.type == "BOOL" else 0)
                elif b.operands.get(p.name, "").strip():
                    op = fix(b.operands[p.name])
                    v = self.ctx.bit(op) if p.type == "BOOL" else self.ctx.value(op)
                else:
                    v = self._default(b, p)
                ins[p.name] = bool(v) if p.type == "BOOL" else v
                vals[(b.id, p.name)] = ins[p.name]
            outs = self._eval(b, ins, fix)
            for name, v in outs.items():
                vals[(b.id, name)] = v
                op = b.operands.get(name, "").strip()
                if op:
                    self.ctx.dt.write_word(fix(op), v)
        if values is not None:
            values.update(vals)
        return vals

    @staticmethod
    def _default(b: Block, p: Pin):
        if p.type == "BOOL":
            return b.type in ("AND",)          # an unused AND input does not block the others
        return 0

    def _eval(self, b: Block, i: dict, fix) -> dict:
        t, ctx = b.type, self.ctx
        vals = list(i.values())
        if t == "AND":
            return {"OUT": all(vals)}
        if t == "OR":
            return {"OUT": any(vals)}
        if t == "XOR":
            return {"OUT": vals[0] != vals[1]}
        if t == "NOT":
            return {"OUT": not vals[0]}
        key = ("mem", b.id)
        if t in ("SR", "RS"):
            q = self.state.get(key, False)
            s, r = (i["S1"], i["R"]) if t == "SR" else (i["S"], i["R1"])
            q = (s or (q and not r)) if t == "SR" else (not r and (s or q))
            self.state[key] = q
            return {"Q1": q}
        if t in ("R_TRIG", "F_TRIG"):
            prev = self.state.get(key, i["CLK"] if t == "R_TRIG" else i["CLK"])
            self.state[key] = i["CLK"]
            return {"Q": (i["CLK"] and not prev) if t == "R_TRIG" else (prev and not i["CLK"])}
        if b.type_().instance == "TIMER":
            inst = fix(b.instance)
            q = self.specs[t].run(ctx, [inst, repr(int(i["PT"]))], i["IN"])
            el = ctx.element(inst)
            if t == "RTO" and i.get("R"):
                self.specs["RES"].run(ctx, [inst], True)
            return {"Q": bool(q), "ET": el["ACC"]}
        if b.type_().instance == "COUNTER":
            inst = fix(b.instance)
            edge, extra = ("CU", "R") if t == "CTU" else ("CD", "LD")
            q = self.specs[t].run(ctx, [inst, repr(int(i["PV"])), "TRUE" if i[extra] else "FALSE"], i[edge])
            return {"Q": bool(q), "CV": ctx.element(inst)["ACC"]}
        if t == "PID":
            inst = fix(b.instance)
            if self.diagram.wire_into(b.id, "SP") or b.operands.get("SP", "").strip():
                ctx.element(inst)["SP"] = float(i["SP"])
            out = self.run_pid(ctx, inst, float(i["PV"]))
            if out is not None:                          # between loop updates the output holds
                self.state[("cv", b.id)] = out
            return {"CV": self.state.get(("cv", b.id), 0.0)}
        a = vals[0] if vals else 0
        if t in ("EQ", "NE", "LT", "LE", "GT", "GE"):
            x, y = i["IN1"], i["IN2"]
            return {"OUT": {"EQ": x == y, "NE": x != y, "LT": x < y, "LE": x <= y, "GT": x > y, "GE": x >= y}[t]}
        if t == "LIMIT":
            return {"OUT": min(max(i["IN"], i["MN"]), i["MX"])}
        if t in ("ADD", "MUL", "MAX", "MIN"):
            out = vals[0]
            for v in vals[1:]:
                out = {"ADD": out + v, "MUL": out * v, "MAX": max(out, v), "MIN": min(out, v)}[t]
            return {"OUT": out}
        if t in ("SUB", "DIV", "MOD"):
            x, y = i["IN1"], i["IN2"]
            if t == "SUB":
                return {"OUT": x - y}
            if y == 0:
                raise PlcFault(0x0601, f"{t} block {b.id}: division by zero")
            if t == "MOD":
                return {"OUT": math.fmod(x, y) if isinstance(x, float) or isinstance(y, float) else int(math.fmod(x, y))}
            if isinstance(x, float) or isinstance(y, float):
                return {"OUT": x / y}
            q = abs(x) // abs(y)
            return {"OUT": q if (x >= 0) == (y >= 0) else -q}
        if t == "ABS":
            return {"OUT": abs(a)}
        if t == "SQRT":
            if a < 0:
                raise PlcFault(0x0601, f"SQRT block {b.id}: square root of a negative number")
            return {"OUT": math.sqrt(a)}
        if t == "MOVE":
            return {"OUT": a}
        if t in ("TO_BCD", "FROM_BCD"):
            from .st import from_bcd, to_bcd
            try:
                return {"OUT": (to_bcd if t == "TO_BCD" else from_bcd)(int(a))}
            except ValueError as e:
                raise PlcFault(0x0601, f"{t} block {b.id}: {e}") from None
        if t == "SEL":
            return {"OUT": i["IN1"] if i["G"] else i["IN0"]}
        if t == "SCALE":
            lo, hi = float(i["IN_MIN"]), float(i["IN_MAX"])
            if hi == lo:
                return {"OUT": float(i["OUT_MIN"])}
            return {"OUT": i["OUT_MIN"] + (float(i["IN"]) - lo) * (i["OUT_MAX"] - i["OUT_MIN"]) / (hi - lo)}
        raise PlcFault(0x0601, f"{t} cannot run")
