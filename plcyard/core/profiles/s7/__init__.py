"""Siemens S7-1200/1500 (TIA Portal): %I/%Q/%M addresses, symbolic PLC tags, IEC timer and counter
instances. The simulated rack: input slots 1 and 3 are %IB0-1 and %IB2-3 (channel 0 = %I0.0,
channel 8 = %I1.0), the thumbwheels are %IW4; outputs 2 and 4 are %QB0-1 and %QB2-3, the BCD
display is %QW4."""

from __future__ import annotations

from ... import isa
from ...program import Program, walk
from ..base import Diagnostic, IODevice, Profile
from .instructions import KINDS, SPECS, S7Context, check_operand, literal
from .memory import ANALOG_IN, ANALOG_OUT, FULL_SCALE, STRUCTS, TYPES, S7Error, S7Memory, _BIT, _SYM, _WORD

INPUT_BYTES = {1: 0, 3: 2, 5: 4}       # slot → first byte
OUTPUT_BYTES = {2: 0, 4: 2, 6: 4}
WORD_SLOTS = (5, 6)                    # whole words (BCD), not 16 channels
MEMORY_FAULT = 0x2522                  # area length error


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

    # -- editing -------------------------------------------------------------
    def validate(self, mnemonic: str, operands: list[str], program: Program | None = None) -> list[str]:
        mem = None
        if program is not None:
            try:
                mem = S7Memory(program.tags)
            except S7Error:
                mem = None
        return isa.validate(mnemonic, operands, self.specs,
                            check=(lambda k, op: check_operand(mem, k, op)) if mem else _syntax_only)

    def normalize(self, operand: str) -> str:
        op = operand.strip()
        if _BIT.match(op) or _WORD.match(op):
            return "%" + op.lstrip("%").upper()
        return op.strip('"') if op.startswith('"') and op.endswith('"') else op

    def check_tags(self, decls: dict[str, dict]) -> str:
        try:
            S7Memory(decls)
        except S7Error as e:
            return str(e)
        return ""

    def tag_value(self, mem: S7Memory, name: str) -> str:
        t = mem.decls[name]["type"]
        el = mem.values.get(name)
        if t == "IEC_TIMER":
            return f"ET {el['ET']} / PT {el['PT']} ms" + ("  Q" if el["Q"] else "")
        if t == "IEC_COUNTER":
            return f"CV {el['CV']} / PV {el['PV']}" + ("  Q" if el["Q"] else "")
        if t == "PID_Compact":
            return (f"SP {el['Setpoint']:g}  PV {el['Input']:.1f}  Out {el['Output']:.1f}"
                    + ("  MAN" if el["ManualEnable"] else ""))
        v = mem.read_word(name)
        return f"{v:g}" if isinstance(v, float) else str(v)

    # -- memory --------------------------------------------------------------
    def new_memory(self) -> S7Memory:
        return S7Memory()

    def context(self, memory: S7Memory) -> S7Context:
        return S7Context(memory)

    def check(self, program: Program, memory) -> list[Diagnostic]:
        try:
            mem = S7Memory(program.tags)
        except S7Error as e:
            return [Diagnostic(2, 0, f"Tags: {e}")]
        problems = []
        for f in program.files.values():
            for i, rung in enumerate(f.rungs):
                for ins in walk(rung.body):
                    msgs = isa.validate(ins.mnemonic, ins.operands, self.specs,
                                        check=lambda k, op: check_operand(mem, k, op))
                    problems += [Diagnostic(f.number, i, m) for m in msgs]
        return problems

    def load(self, program: Program, mem: S7Memory) -> None:
        mem.clear(program.tags, keep_io=True)

    def prescan(self, program: Program, mem: S7Memory, ctx) -> None:
        for f in program.files.values():
            for rung in f.rungs:
                for ins in walk(rung.body):
                    if ins.mnemonic == "OTE":
                        mem.write_bit(ins.operands[0], False)

    def reset_timers_counters(self, mem: S7Memory) -> None:
        for name in mem.names():
            if mem.decls[name]["type"] in STRUCTS:
                el = mem.values[name]
                keep = {k: el[k] for k in ("PT", "PV") if k in el}
                el.update({k: (False if isinstance(v, bool) else 0) for k, v in el.items()})
                el.update(keep)

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


def _syntax_only(kind: str, op: str) -> str | None:
    if literal(op) is not None or _BIT.match(op.strip()) or _WORD.match(op.strip()) or _SYM.match(op.strip()):
        return None
    return f"{op!r} is not an address or a tag"


S7_PROFILE = S7()
