"""The PLC: one controller with tags, arrays, data types, routines, functions and function blocks.

Simulated rack (canonical addresses; the other notation shows Local:<slot>:I.Data.<point>):
  inputs   slot 1 → %I0.0-%I1.7, slot 3 → %I2.0-%I3.7, slot 5 → %IW4 (BCD thumbwheels)
  outputs  slot 2 → %Q0.0-%Q1.7, slot 4 → %Q2.0-%Q3.7, slot 6 → %QW4 (BCD display)
  analog   inputs %IW64 %IW66 %IW68 %IW70, outputs %QW64 %QW66 %QW68: 0-27648 = 0-10 V
"""

from __future__ import annotations

import re

from .. import isa
from ..program import Program, walk
from ..profiles.base import Diagnostic, IODevice, Profile, parse_param
from .instructions import KINDS, SPECS, WANT, Context, _cv_out, literal, run_pid, unused
from .memory import (ANALOG_IN, ANALOG_OUT, FULL_SCALE, INPUT_SLOTS, OUTPUT_SLOTS, STRUCTS, SYSTEM, TYPES,
                     WORD_SLOTS, Memory, PlcMemoryError, _BIT, _MODULE, _SYM, _WORD, parse_time)

MEMORY_FAULT = 0x0414         # bad reference at run time
SECTIONS = ("Input", "Output", "InOut", "Static", "Temp")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _slot_to_bytes(word: int) -> int:
    """Point p of a 16-point module is bit p%8 of byte p//8: swap to the big-endian word."""
    return ((word & 0xFF) << 8) | ((word >> 8) & 0xFF)


def blocks(program: Program) -> list:
    return [f for f in program.files.values() if f.kind in ("FC", "FB")]


def check_operand(mem, kind: str, op: str) -> str | None:
    op = op.strip()
    if kind.endswith("_opt") and unused(op):
        return None
    if kind == "routine":
        return None if _NAME.fullmatch(op) else f"{op!r} is not a routine name"
    if kind == "block":
        return None if re.fullmatch(r'#?"?[A-Za-z_]\w*"?(?:\.[A-Za-z_]\w*|\[[^\]]+\])*', op) \
            else f"{op!r} is not a block name"
    if kind == "param":
        p = parse_param(op)
        if p is None:
            return f"write a parameter as Name:=value (input) or Name=>tag (output), not {op!r}"
        return check_operand(mem, "value" if p[1] == ":=" else "out", p[2])
    lit = literal(op)
    if lit is not None:
        if kind in ("value", "value_opt", "time") or (kind in ("bool", "bool_opt") and op.lower() in ("true", "false")):
            if kind == "time" and op[:2].upper() == "T#" and parse_time(op) is None:
                return f"{op} is not a time; write it like T#5s or T#500ms"
            return None
        return f"{op} is a constant; needs {KINDS[kind]}"
    if kind == "time" and op[:2].upper() == "T#":
        return f"{op} is not a time; write it like T#5s or T#500ms"
    if mem is None:
        ok = _BIT.match(op) or _WORD.match(op) or _MODULE.match(op) or _SYM.match(op)
        return None if ok else f"{op!r} is not an address or a tag"
    try:
        r = mem.ref(op, True)
    except PlcMemoryError as e:
        return str(e)
    if kind == "array":
        if r.area is not None or not r.path or not isinstance(r.path[-1], int):
            return f"{op} is not an array element; write it like {op}[0]"
        return None
    if r.type not in WANT[kind]:
        return f"{op} is a {r.type}; needs {KINDS[kind]}"
    if kind in ("dest", "out") and (r.area == "I" or r.tag in SYSTEM):
        return f"{op} is read-only"
    return None


def value_text(t: str, v) -> str:
    """A value as the tag list shows it."""
    if t == "PID":
        return f"SP {v['SP']:g}  PV {v['PV']:.1f}  Out {v['CV']:.1f} %" + ("  MAN" if v["MO"] else "")
    if t in ("TIMER", "COUNTER"):
        return f"ACC {v['ACC']} / PRE {v['PRE']}" + ("  DN" if v["DN"] else "")
    if t == "CONTROL":
        return f"POS {v['POS']} / LEN {v['LEN']}" + ("  DN" if v["DN"] else "")
    if isinstance(v, dict):
        return "{…}"
    if isinstance(v, list):
        return f"[{len(v)}]"
    if isinstance(v, bool):
        return "1" if v else "0"
    return f"{v:g}" if isinstance(v, float) else str(v)


class PlcYard(Profile):
    name = "plcyard"
    title = "PLCYard"
    specs = SPECS
    kinds = KINDS
    memory_errors = (PlcMemoryError,)
    memory_fault_code = MEMORY_FAULT
    tag_types = TYPES
    tag_fields = ("address",)
    routine_kinds = ("SBR", "FC", "FB")
    interface_sections = SECTIONS

    # -- memory and declarations ---------------------------------------------------
    def new_memory(self) -> Memory:
        return Memory()

    def context(self, memory: Memory) -> Context:
        return Context(memory)

    def build_memory(self, program: Program) -> Memory:
        structs, kinds = {}, {}
        for n, ms in program.types.items():
            structs[n], kinds[n] = dict(ms), "data type"
        for f in blocks(program):
            members: dict[str, str] = {}
            for sec, names in f.interface.items():
                if sec not in SECTIONS:
                    raise PlcMemoryError(f"{f.title}: unknown interface section {sec} (use {', '.join(SECTIONS)})")
                if f.kind == "FC" and sec == "Static":
                    raise PlcMemoryError(f"function {f.title}: a function keeps no static data; use a function block")
                for n, t in names.items():
                    if n.lower() in {m.lower() for m in members}:
                        raise PlcMemoryError(f"{f.title}: {n} is declared twice in the interface")
                    members[n] = t
            structs[f.title] = members
            kinds[f.title] = "function block" if f.kind == "FB" else "function"
        decls = {**program.tags, **{f"__{f.title}": {"type": f.title} for f in blocks(program)}}
        mem = Memory(decls, structs, kinds)
        for name in program.tags:
            t = mem.decls[name]["type"]
            if kinds.get(t) == "function":
                raise PlcMemoryError(f"tag {name}: {t} is a function; only function blocks have instances")
        return mem

    def tag_value(self, mem: Memory, name: str) -> str:
        r = mem.ref(name)
        return value_text(r.type, mem.read_word(name) if mem.is_scalar(r.type) else mem.values[r.tag])

    def forceable(self, mem: Memory, ref: str) -> str:
        try:
            r = mem.ref(ref)
        except PlcMemoryError as e:
            return str(e)
        if r.type != "BOOL" or r.area not in ("I", "Q"):
            return "only I/O points can be forced"
        return ""

    def block_instance(self, program: Program, f) -> str | None:
        return f"__{f.title}" if f is not None and f.kind in ("FC", "FB") else None

    def call_problem(self, program: Program, memory, name: str, inputs: list[str], outputs: list[str]) -> str | None:
        f = program.routine(name)
        if f is not None and f.kind == "SBR":
            return f"routine {f.title} takes no parameters" if inputs or outputs else None
        if f is not None and f.kind == "FB":
            return f"{f.title} is a function block; call an instance of it (a tag of type {f.title})"
        if f is None:
            try:
                t = memory.type_of(name)
            except PlcMemoryError:
                return f"{name} is not a routine, a function or a function block instance"
            f = next((g for g in blocks(program) if g.kind == "FB" and g.title == t), None)
            if f is None:
                return f"{name} is a {t}, not a function block instance"
        sections = {n.lower(): sec for sec, ns in f.interface.items() for n in ns}
        for n in inputs:
            if sections.get(n.lower()) not in ("Input", "InOut"):
                return f"{f.title} has no input {n}"
        for n in outputs:
            if sections.get(n.lower()) not in ("Output", "InOut"):
                return f"{f.title} has no output {n}"
        return None

    # -- editing -------------------------------------------------------------
    def normalize(self, operand: str) -> str:
        """Canonical text: I/O as %I0.0 (Local:1:I.Data.0 converts), parameters without spaces."""
        from .memory import module_to_absolute
        op = operand.strip()
        p = parse_param(op)
        if p:
            return f"{p[0]}{p[1]}{self.normalize(p[2])}"
        op = module_to_absolute(op) or op
        if _BIT.match(op) or _WORD.match(op):
            return "%" + op.lstrip("%").upper()
        if op.lower() == "s:fs":
            return "FirstScan"
        if op.lower() == "s:v":
            return "Overflow"
        return op

    def validate(self, mnemonic: str, operands: list[str], program: Program | None = None,
                 routine: int | None = None) -> list[str]:
        mem = None
        if program is not None:
            try:
                mem = self.scoped_memory(program, self.build_memory(program), program.files.get(routine))
            except PlcMemoryError:
                mem = None
        return self._problems(program, mem, mnemonic, operands)

    def _problems(self, program, mem, mnemonic: str, operands: list[str]) -> list[str]:
        spec = self.specs.get(mnemonic)
        if spec is None:
            return [f"{mnemonic} is not an instruction"]
        n = len(spec.operands)
        if not n - spec.optional <= len(operands) <= n:
            return [f"{mnemonic} needs {n - spec.optional} operand(s), has {len(operands)}"]
        problems = []
        for kind, label, op in zip(spec.operands, spec.labels, operands):
            if unused(op) and not kind.endswith("_opt") and not (kind == "param"):
                problems.append(f"{mnemonic}: {label} is not set")
                continue
            if kind == "param" and unused(op):
                continue
            msg = check_operand(mem, kind, op)
            if msg:
                problems.append(f"{mnemonic} {label}: {msg}")
        if problems or program is None or mem is None:
            return problems
        if mnemonic == "JSR" and program.routine(operands[0]) is None:
            return [f"JSR: routine {operands[0]} does not exist"]
        if mnemonic == "CALL":
            params = [parse_param(p) for p in operands[1:] if not unused(p)]
            msg = self.call_problem(program, mem, operands[0], [p[0] for p in params if p[1] == ":="],
                                    [p[0] for p in params if p[1] == "=>"])
            return [f"CALL: {msg}"] if msg else []
        return []

    # -- structured text ---------------------------------------------------------------
    st_blocks = {"TON": ("TON", ("TIMER",)), "TOF": ("TOF", ("TIMER",)), "TP": ("TP", ("TIMER",)),
                 "RTO": ("RTO", ("TIMER",)), "CTU": ("CTU", ("COUNTER",)), "CTD": ("CTD", ("COUNTER",)),
                 "PID": ("PID", ("PID",))}

    def st_call(self, ctx, instance: str, block: str, inputs: dict) -> dict:
        """Delay.TON(IN := x, PT := T#2s) (PRE works too); Parts.CTU(CU := x, PV := 5, R := y);
        LevelPID.PID(PV := level, SP := 50.0)."""
        el = ctx.element(instance)
        lit = lambda v: "TRUE" if v is True else ("FALSE" if v is False else repr(v))
        if block == "PID":
            if "SP" in inputs:
                el["SP"] = float(inputs["SP"])
            out = run_pid(ctx, instance, float(inputs.get("PV", el["PV"])), inputs.get("TIEBACK"))
            return {"CV": out if out is not None else _cv_out(el, el["CV"]), "OUT": el["CV"]}
        pre = inputs.get("PT", inputs.get("PV", inputs.get("PRE", el["PRE"])))
        if block in ("TON", "TOF", "TP", "RTO"):
            q = SPECS[block].run(ctx, [instance, lit(int(pre))], bool(inputs.get("IN", False)))
            if block == "RTO" and (inputs.get("RES") or inputs.get("R")):
                SPECS["RES"].run(ctx, [instance], True)
            return {"Q": q, "DN": el["DN"], "ET": el["ACC"], "ACC": el["ACC"], "EN": el["EN"], "TT": el["TT"]}
        edge, extra = ("CU", "R") if block == "CTU" else ("CD", "LD")
        reset = bool(inputs.get(extra, False) or inputs.get("RES", False))
        q = SPECS[block].run(ctx, [instance, lit(int(pre)), lit(reset)], bool(inputs.get(edge, False)))
        return {"Q": q, "DN": el["DN"], "CV": el["ACC"], "ACC": el["ACC"]}

    # -- download ------------------------------------------------------------
    def check(self, program: Program, memory) -> list[Diagnostic]:
        try:
            mem = self.build_memory(program)
        except PlcMemoryError as e:
            return [Diagnostic(2, 0, f"Tags: {e}")]
        problems = self.check_st(program, mem)
        for f in program.files.values():
            local = self.scoped_memory(program, mem, f)
            if f.language == "FBD":
                from .. import fbd
                problems += [Diagnostic(f.number, 0, m, block=bid) for bid, m in
                             fbd.check(f.diagram or fbd.Diagram(), local, lambda k, t: check_operand(local, k, t))]
            for i, rung in enumerate(f.rungs):
                for ins in walk(rung.body):
                    problems += [Diagnostic(f.number, i, m)
                                 for m in self._problems(program, local, ins.mnemonic, ins.operands)]
        return problems

    def load(self, program: Program, mem: Memory) -> None:
        built = self.build_memory(program)
        io = (bytearray(mem.areas["I"]), bytearray(mem.areas["Q"]))
        mem.__dict__.update(built.__dict__)
        mem.areas["I"][:], mem.areas["Q"][:] = io

    def prescan(self, program: Program, mem: Memory, ctx) -> None:
        for f in program.files.values():
            if f.kind in ("FC", "FB"):                 # local outputs are reset when the block runs
                continue
            for rung in f.rungs:
                for ins in walk(rung.body):
                    if ins.mnemonic == "OTE":
                        mem.write_bit(ins.operands[0], False)

    def reset_timers_counters(self, mem: Memory) -> None:
        for name in mem.names():
            for _, t, el in list(mem.walk(name)):
                if t in ("TIMER", "COUNTER"):
                    el.update({k: (False if isinstance(v, bool) else 0) for k, v in el.items() if k != "PRE"})

    # -- scan ----------------------------------------------------------------
    def begin_scan(self, mem: Memory, first_pass: bool) -> None:
        mem.write_bit("FirstScan", first_pass)

    def end_scan(self, mem: Memory) -> None:
        mem.write_bit("FirstScan", False)

    def clear_fault(self, mem: Memory) -> None:
        mem.write_bit("Overflow", False)

    # -- live display ------------------------------------------------------------
    def live(self, mem: Memory, ins):
        m, ops = ins.mnemonic, ins.operands
        if m == "PID":
            el = mem.element(ops[0])
            return ([("Setpoint", f"{el['SP']:g}"), ("Process Variable", f"{el['PV']:.1f}"),
                     ("Output %", f"{el['CV']:.1f}")], [("MAN", bool(el["MO"]))])
        if m in ("TON", "TOF", "RTO", "TP"):
            el = mem.element(ops[0])
            return [("Accum", str(el["ACC"]))], [(b, bool(el[b])) for b in ("EN", "TT", "DN")]
        if m in ("CTU", "CTD"):
            el = mem.element(ops[0])
            return [("Accum", str(el["ACC"]))], [("CU" if m == "CTU" else "CD", bool(el["CU" if m == "CTU" else "CD"])),
                                                 ("DN", bool(el["DN"]))]
        if m in ("BSL", "BSR", "SQO", "SQC", "SQL"):
            ctl = ops[1] if m in ("BSL", "BSR") else (ops[2] if m == "SQL" else ops[3])
            el = mem.element(ctl)
            return [("Position", str(el["POS"]))], [(b, bool(el[b])) for b in (("EN", "DN", "FD") if m == "SQC" else ("EN", "DN"))]
        return [], []

    # -- naming of the simulated rack ---------------------------------------------
    def io_name(self, direction: str, slot: int, bit: int | None = None) -> str:
        base = (INPUT_SLOTS if direction == "I" else OUTPUT_SLOTS).get(slot, 0)
        area = "I" if direction == "I" else "Q"
        if bit is None:
            return f"%{area}W{base}"
        return f"%{area}{base + bit // 8}.{bit % 8}"

    def analog_name(self, direction: str, channel: int) -> str:
        return f"%{'I' if direction == 'I' else 'Q'}W{(ANALOG_IN if direction == 'I' else ANALOG_OUT)[channel]}"

    def io_image(self, mem: Memory) -> list[tuple[str, int]]:
        return [(f"%IW{b}", mem.word("I", b)) for b in (0, 2)] + [(f"%QW{b}", mem.word("Q", b)) for b in (0, 2)]

    # -- I/O image -------------------------------------------------------------
    def read_inputs(self, mem: Memory, device: IODevice) -> None:
        for slot, word in device.input_words().items():
            if slot in INPUT_SLOTS:
                mem.set_word("I", INPUT_SLOTS[slot], word if slot in WORD_SLOTS else _slot_to_bytes(word))
        if hasattr(device, "analog_inputs"):
            for ch, volts in device.analog_inputs().items():
                if ch in ANALOG_IN:
                    mem.set_word("I", ANALOG_IN[ch], round(min(max(volts, 0.0), 10.0) / 10.0 * FULL_SCALE))

    def write_outputs(self, mem: Memory, device: IODevice) -> None:
        words = {}
        for slot, b in OUTPUT_SLOTS.items():
            w = mem.word("Q", b)
            words[slot] = w if slot in WORD_SLOTS else _slot_to_bytes(w)
        device.set_output_words(words)
        if hasattr(device, "set_analog_outputs"):
            volts = {}
            for ch, byte in ANALOG_OUT.items():
                raw = int.from_bytes(mem.areas["Q"][byte:byte + 2], "big", signed=True)
                volts[ch] = min(max(raw, 0), FULL_SCALE) / FULL_SCALE * 10.0
            device.set_analog_outputs(volts)

    def outputs_off(self, mem: Memory, device: IODevice) -> None:
        device.set_output_words({s: 0 for s in OUTPUT_SLOTS})
        if hasattr(device, "set_analog_outputs"):
            device.set_analog_outputs({ch: 0.0 for ch in ANALOG_OUT})


PLC = PlcYard()
