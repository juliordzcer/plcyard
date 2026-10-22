"""Siemens S7-1200/1500 (TIA Portal): %I/%Q/%M addresses, symbolic PLC tags, IEC timer and counter
instances, PLC data types, arrays, functions (FC) and function blocks (FB) whose instances are data
blocks. The simulated rack: input slots 1 and 3 are %IB0-1 and %IB2-3 (channel 0 = %I0.0,
channel 8 = %I1.0), the thumbwheels are %IW4; outputs 2 and 4 are %QB0-1 and %QB2-3, the BCD
display is %QW4."""

from __future__ import annotations

from ... import isa
from ...program import Program, walk
from ..base import Diagnostic, IODevice, Profile, parse_param
from .instructions import KINDS, SPECS, S7Context, check_operand, literal, run_pid_compact
from .memory import ANALOG_IN, ANALOG_OUT, FULL_SCALE, STRUCTS, TYPES, S7Error, S7Memory, _BIT, _SYM, _WORD

INPUT_BYTES = {1: 0, 3: 2, 5: 4}       # slot → first byte
OUTPUT_BYTES = {2: 0, 4: 2, 6: 4}
WORD_SLOTS = (5, 6)                    # whole words (BCD), not 16 channels
MEMORY_FAULT = 0x2522                  # area length error
SECTIONS = ("Input", "Output", "InOut", "Static", "Temp")


def _slot_to_bytes(word: int) -> int:
    """Channel b of a 16-channel module is bit b%8 of byte b//8: swap to the big-endian word."""
    return ((word & 0xFF) << 8) | ((word >> 8) & 0xFF)


class S7(Profile):
    name = "s7"
    title = "S7-1200/1500 (TIA Portal)"
    specs = SPECS
    kinds = KINDS
    memory_errors = (S7Error,)
    memory_fault_code = MEMORY_FAULT
    tag_types = TYPES
    tag_fields = ("address",)
    routine_kinds = ("FC", "FB")
    interface_sections = SECTIONS

    def build_memory(self, program: Program) -> S7Memory:
        structs, kinds = {}, {}
        for n, ms in program.types.items():
            structs[n], kinds[n] = dict(ms), "PLC data type"
        blocks = _blocks(program)
        for f in blocks:
            members: dict[str, str] = {}
            for sec, names in f.interface.items():
                if sec not in SECTIONS:
                    raise S7Error(f"{f.title}: unknown interface section {sec} (use {', '.join(SECTIONS)})")
                if f.kind == "FC" and sec == "Static":
                    raise S7Error(f"function {f.title}: an FC keeps no static data; use an FB")
                for n, t in names.items():
                    if n.lower() in {m.lower() for m in members}:
                        raise S7Error(f"{f.title}: {n} is declared twice in the interface")
                    members[n] = t
            structs[f.title] = members
            kinds[f.title] = "function block" if f.kind == "FB" else "function"
        decls = {**program.tags, **{f"__{f.title}": {"type": f.title} for f in blocks}}
        mem = S7Memory(decls, structs, kinds)
        for name in program.tags:
            t = mem.decls[name]["type"]
            if kinds.get(t) == "function":
                raise S7Error(f"tag {name}: {t} is a function (FC); only function blocks have instances")
        return mem

    def block_instance(self, program: Program, f) -> str | None:
        return f"__{f.title}" if f is not None and f.kind in ("FC", "FB") else None

    def call_problem(self, program: Program, memory, name: str, inputs: list[str], outputs: list[str]) -> str | None:
        f = program.routine(name)
        if f is not None and f.kind == "FB":
            return f"{f.title} is a function block; call an instance of it (a tag or DB of type {f.title})"
        if f is None:
            try:
                t = memory.type_of(name)
            except S7Error:
                return f"{name} is not a function (FC) or a function block instance"
            f = next((g for g in _blocks(program) if g.kind == "FB" and g.title == t), None)
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

    def forceable(self, mem: S7Memory, ref: str) -> str:
        try:
            r = mem.ref(ref)
        except S7Error as e:
            return str(e)
        if r.type != "Bool" or r.area not in ("I", "Q"):
            return "only I/O bits can be forced, like %I0.0 or %Q0.1"
        return ""

    # -- editing -------------------------------------------------------------
    def validate(self, mnemonic: str, operands: list[str], program: Program | None = None,
                 routine: int | None = None) -> list[str]:
        mem = None
        if program is not None:
            try:
                mem = self.scoped_memory(program, self.build_memory(program), program.files.get(routine))
            except S7Error:
                mem = None
        problems = isa.validate(mnemonic, operands, self.specs,
                                check=(lambda k, op: check_operand(mem, k, op)) if mem else _syntax_only)
        if mem is not None and not problems and mnemonic == "CALL":
            problems += self._call_problems(program, mem, operands)
        return problems

    def _call_problems(self, program: Program, mem, operands: list[str]) -> list[str]:
        params = [parse_param(p) for p in operands[1:]]
        msg = self.call_problem(program, mem, operands[0], [p[0] for p in params if p[1] == ":="],
                                [p[0] for p in params if p[1] == "=>"])
        return [f"CALL: {msg}"] if msg else []

    def normalize(self, operand: str) -> str:
        op = operand.strip()
        p = parse_param(op)
        if p:                                    # rung text has no spaces: Start:=Button
            return f"{p[0]}{p[1]}{self.normalize(p[2])}"
        if _BIT.match(op) or _WORD.match(op):
            return "%" + op.lstrip("%").upper()
        return op.strip('"') if op.startswith('"') and op.endswith('"') else op

    def tag_value(self, mem: S7Memory, name: str) -> str:
        r = mem.ref(name)
        return value_text(r.type, mem.read_word(name) if mem.is_scalar(r.type) else mem.values[r.tag])

    # -- memory --------------------------------------------------------------
    def new_memory(self) -> S7Memory:
        return S7Memory()

    def context(self, memory: S7Memory) -> S7Context:
        return S7Context(memory)

    st_blocks = {"TON": ("TON", ("IEC_TIMER",)), "TOF": ("TOF", ("IEC_TIMER",)), "TP": ("TP", ("IEC_TIMER",)),
                 "CTU": ("CTU", ("IEC_COUNTER",)), "CTD": ("CTD", ("IEC_COUNTER",)),
                 "PID_COMPACT": ("PID_Compact", ("PID_Compact",))}

    def st_call(self, ctx, instance: str, block: str, inputs: dict) -> dict:
        """TIA syntax: Delay.TON(IN := x, PT := T#2s); Parts.CTU(CU := x, R := y, PV := 5);
        LevelPID.PID_Compact(Setpoint := sp, Input := pv, Output => out)."""
        el = ctx.element(instance)
        lit = lambda v: "TRUE" if v is True else ("FALSE" if v is False else repr(v))
        if block in ("TON", "TOF", "TP"):
            pt = inputs.get("PT", el["PT"])
            SPECS[block].run(ctx, [instance, lit(int(pt))], bool(inputs.get("IN", False)))
            return {"Q": el["Q"], "ET": el["ET"]}
        if block in ("CTU", "CTD"):
            edge, extra = ("CU", "R") if block == "CTU" else ("CD", "LD")
            pv = inputs.get("PV", el["PV"])
            SPECS[block].run(ctx, [instance, lit(int(pv)), lit(bool(inputs.get(extra, False)))],
                             bool(inputs.get(edge, False)))
            return {"Q": el["Q"], "CV": el["CV"]}
        out = run_pid_compact(ctx, instance, float(inputs.get("SETPOINT", el["Setpoint"])),
                              float(inputs.get("INPUT", el["Input"])))
        return {"OUTPUT": out}

    def check(self, program: Program, memory) -> list[Diagnostic]:
        try:
            mem = self.build_memory(program)
        except S7Error as e:
            return [Diagnostic(2, 0, f"Tags: {e}")]
        problems = self.check_st(program, mem)
        for f in program.files.values():
            local = self.scoped_memory(program, mem, f)
            for i, rung in enumerate(f.rungs):
                for ins in walk(rung.body):
                    msgs = isa.validate(ins.mnemonic, ins.operands, self.specs,
                                        check=lambda k, op: check_operand(local, k, op))
                    if not msgs and ins.mnemonic == "CALL":
                        msgs = self._call_problems(program, local, ins.operands)
                    problems += [Diagnostic(f.number, i, m) for m in msgs]
        return problems

    def load(self, program: Program, mem: S7Memory) -> None:
        built = self.build_memory(program)
        io = (bytearray(mem.areas["I"]), bytearray(mem.areas["Q"]))
        mem.__dict__.update(built.__dict__)
        mem.areas["I"][:], mem.areas["Q"][:] = io

    def prescan(self, program: Program, mem: S7Memory, ctx) -> None:
        for f in program.files.values():
            if f.kind in ("FC", "FB"):                 # local outputs are reset when the block runs
                continue
            for rung in f.rungs:
                for ins in walk(rung.body):
                    if ins.mnemonic == "OTE":
                        mem.write_bit(ins.operands[0], False)

    def reset_timers_counters(self, mem: S7Memory) -> None:
        for name in mem.names():
            for _, t, el in list(mem.walk(name)):
                if t in ("IEC_TIMER", "IEC_COUNTER"):
                    el.update({k: (False if isinstance(v, bool) else 0) for k, v in el.items() if k not in ("PT", "PV")})

    # -- scan ----------------------------------------------------------------
    def begin_scan(self, mem: S7Memory, first_pass: bool) -> None:
        mem.write_bit("FirstScan", first_pass)

    def end_scan(self, mem: S7Memory) -> None:
        mem.write_bit("FirstScan", False)

    # -- live display ------------------------------------------------------------
    def live(self, mem: S7Memory, ins):
        m, ops = ins.mnemonic, ins.operands
        if m in ("TON", "TOF", "TP"):
            el = mem.element(ops[0])
            return [("ET", f"{el['ET']} ms")], [("Q", bool(el["Q"]))]
        if m in ("CTU", "CTD"):
            el = mem.element(ops[0])
            return [("CV", str(el["CV"]))], [("Q", bool(el["Q"]))]
        if m == "PID_Compact":
            el = mem.element(ops[0])
            return [("Output", f"{el['Output']:.1f} %")], [("MAN", bool(el["ManualEnable"]))]
        return [], []

    # -- naming of the simulated rack ---------------------------------------------
    def io_name(self, direction: str, slot: int, bit: int | None = None) -> str:
        base = (INPUT_BYTES if direction == "I" else OUTPUT_BYTES).get(slot, 0)
        area = "I" if direction == "I" else "Q"
        if bit is None:
            return f"%{area}W{base}"
        return f"%{area}{base + bit // 8}.{bit % 8}"

    def analog_name(self, direction: str, channel: int) -> str:
        return f"%{'I' if direction == 'I' else 'Q'}W{(ANALOG_IN if direction == 'I' else ANALOG_OUT)[channel]}"

    def io_image(self, mem: S7Memory) -> list[tuple[str, int]]:
        return [(f"%IW{b}", mem.word("I", b)) for b in (0, 2)] + [(f"%QW{b}", mem.word("Q", b)) for b in (0, 2)]

    # -- I/O image -------------------------------------------------------------
    def read_inputs(self, mem: S7Memory, device: IODevice) -> None:
        for slot, word in device.input_words().items():
            if slot in INPUT_BYTES:
                mem.set_word("I", INPUT_BYTES[slot], word if slot in WORD_SLOTS else _slot_to_bytes(word))
        if hasattr(device, "analog_inputs"):
            for ch, volts in device.analog_inputs().items():
                if ch in ANALOG_IN:
                    mem.set_word("I", ANALOG_IN[ch], round(min(max(volts, 0.0), 10.0) / 10.0 * FULL_SCALE))

    def write_outputs(self, mem: S7Memory, device: IODevice) -> None:
        words = {}
        for slot, b in OUTPUT_BYTES.items():
            w = mem.word("Q", b)
            words[slot] = w if slot in WORD_SLOTS else _slot_to_bytes(w)
        device.set_output_words(words)
        if hasattr(device, "set_analog_outputs"):
            raw = int.from_bytes(mem.areas["Q"][ANALOG_OUT[0]:ANALOG_OUT[0] + 2], "big", signed=True)
            device.set_analog_outputs({0: min(max(raw, 0), FULL_SCALE) / FULL_SCALE * 10.0})

    def outputs_off(self, mem: S7Memory, device: IODevice) -> None:
        device.set_output_words({s: 0 for s in OUTPUT_BYTES})
        if hasattr(device, "set_analog_outputs"):
            device.set_analog_outputs({0: 0.0})


def _blocks(program: Program) -> list:
    return [f for f in program.files.values() if f.kind in ("FC", "FB")]


def value_text(t: str, v) -> str:
    """A value as the tag list shows it."""
    if t == "IEC_TIMER":
        return f"ET {v['ET']} / PT {v['PT']} ms" + ("  Q" if v["Q"] else "")
    if t == "IEC_COUNTER":
        return f"CV {v['CV']} / PV {v['PV']}" + ("  Q" if v["Q"] else "")
    if t == "PID_Compact":
        return (f"SP {v['Setpoint']:g}  PV {v['Input']:.1f}  Out {v['Output']:.1f}"
                + ("  MAN" if v["ManualEnable"] else ""))
    if isinstance(v, dict):
        return "{…}"
    if isinstance(v, list):
        return f"[{len(v)}]"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return f"{v:g}" if isinstance(v, float) else str(v)


def _syntax_only(kind: str, op: str) -> str | None:
    if kind in ("block", "param"):
        return None
    if literal(op) is not None or _BIT.match(op.strip()) or _WORD.match(op.strip()) or _SYM.match(op.strip()):
        return None
    return f"{op!r} is not an address or a tag"


S7_PROFILE = S7()
