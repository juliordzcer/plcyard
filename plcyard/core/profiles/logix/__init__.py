"""Allen-Bradley Logix (ControlLogix / CompactLogix, Studio 5000): tags instead of a data table,
millisecond timers, DINT math. I/O modules appear as Local:<slot>:I.Data / Local:<slot>:O.Data."""

from __future__ import annotations

from ... import isa
from ...program import Program, walk
from ..base import Diagnostic, IODevice, Profile
from .instructions import KINDS, SPECS, LogixContext, check_operand, run_pid
from .tags import (_REF as REF, ANALOG_IN_SLOT, ANALOG_OUT_SLOT, INPUT_SLOTS, OUTPUT_SLOTS, STRUCTS, TYPES,
                   TagError, TagTable)

MEMORY_FAULT = 0x0414        # major fault type 4 (program) code 20: bad reference at run time


class Logix(Profile):
    name = "logix"
    title = "Logix (Studio 5000)"
    specs = SPECS
    kinds = KINDS
    memory_errors = (TagError,)
    memory_fault_code = MEMORY_FAULT

    tag_types = TYPES

    def check_tags(self, decls: dict[str, dict]) -> str:
        try:
            TagTable(decls)
        except TagError as e:
            return str(e)
        return ""

    def tag_value(self, tags: TagTable, name: str) -> str:
        t = tags.types[name]
        if t == "PID":
            el = tags.values[name]
            return f"SP {el['SP']:g}  PV {el['PV']:.1f}  CV {el['CV']:.1f}" + ("  MAN" if el["MO"] else "")
        if t in STRUCTS:
            el = tags.values[name]
            return f"ACC {el['ACC']} / PRE {el['PRE']}" + ("  DN" if el["DN"] else "")
        v = tags.read_word(name)
        return f"{v:g}" if isinstance(v, float) else str(v)

    # -- editing -------------------------------------------------------------
    def validate(self, mnemonic: str, operands: list[str], program: Program | None = None) -> list[str]:
        tags = None
        if program is not None:
            try:
                tags = TagTable(program.tags)
            except TagError:
                tags = None
        return isa.validate(mnemonic, operands, self.specs,
                            check=(lambda k, op: check_operand(tags, k, op)) if tags else _syntax_only)

    def new_memory(self) -> TagTable:
        return TagTable()

    def context(self, memory: TagTable) -> LogixContext:
        return LogixContext(memory)

    # -- download ------------------------------------------------------------
    st_blocks = {"TON": ("TON", ("TIMER",)), "TOF": ("TOF", ("TIMER",)), "RTO": ("RTO", ("TIMER",)),
                 "CTU": ("CTU", ("COUNTER",)), "CTD": ("CTD", ("COUNTER",)), "PID": ("PID", ("PID",))}

    def st_call(self, ctx, instance: str, block: str, inputs: dict) -> dict:
        """IEC-style calls on Logix tags: Delay.TON(IN := x, PRE := 2000); Parts.CTU(CU := x, RES := y);
        LevelPID.PID(PV := level). (Studio 5000's own TONR/FBD_TIMER are not modelled.)"""
        el = ctx.element(instance)
        if block == "PID":
            return {"CV": run_pid(ctx, instance, float(inputs.get("PV", el["PV"])))}
        if "PRE" in inputs or "PT" in inputs:
            el["PRE"] = int(inputs.get("PRE", inputs.get("PT")))
        if block in ("TON", "TOF", "RTO"):
            SPECS[block].run(ctx, [instance, "0", "0"], bool(inputs.get("IN", False)))
            if block == "RTO" and inputs.get("RES"):
                SPECS["RES"].run(ctx, [instance], True)
            return {"EN": el["EN"], "TT": el["TT"], "DN": el["DN"], "ACC": el["ACC"], "Q": el["DN"], "ET": el["ACC"]}
        edge = "CU" if block == "CTU" else "CD"
        SPECS[block].run(ctx, [instance, "0", "0"], bool(inputs.get(edge, False)))
        if inputs.get("RES") or inputs.get("R"):
            SPECS["RES"].run(ctx, [instance], True)
        return {"DN": el["DN"], "ACC": el["ACC"], "Q": el["DN"], "CV": el["ACC"]}

    def check(self, program: Program, memory) -> list[Diagnostic]:
        try:
            tags = TagTable(program.tags)
        except TagError as e:
            return [Diagnostic(2, 0, f"Tags: {e}")]
        problems = self.check_st(program, tags)
        for f in program.files.values():
            for i, rung in enumerate(f.rungs):
                for ins in walk(rung.body):
                    msgs = isa.validate(ins.mnemonic, ins.operands, self.specs,
                                        check=lambda k, op: check_operand(tags, k, op))
                    problems += [Diagnostic(f.number, i, m) for m in msgs]
                    if ins.mnemonic in ("JSR", "SBR", "RET"):
                        problems.append(Diagnostic(f.number, i, f"{ins.mnemonic}: routines are not supported yet"))
        return problems

    def load(self, program: Program, tags: TagTable) -> None:
        tags.clear(program.tags, keep_io=True)

    def prescan(self, program: Program, tags: TagTable, ctx) -> None:
        for f in program.files.values():
            for rung in f.rungs:
                for ins in walk(rung.body):
                    if ins.mnemonic == "OTE":
                        tags.write_bit(ins.operands[0], False)

    def reset_timers_counters(self, tags: TagTable) -> None:
        for name in tags.names():
            if tags.types[name] in ("TIMER", "COUNTER"):
                pre = tags.values[name]["PRE"]
                tags.values[name] = {k: (False if isinstance(v, bool) else 0) for k, v in tags.values[name].items()}
                tags.values[name]["PRE"] = pre

    # -- scan ----------------------------------------------------------------
    def begin_scan(self, tags: TagTable, first_pass: bool) -> None:
        tags.write_bit("S:FS", first_pass)

    def end_scan(self, tags: TagTable) -> None:
        tags.write_bit("S:FS", False)

    def clear_fault(self, tags: TagTable) -> None:
        tags.write_bit("S:V", False)

    # -- live display ------------------------------------------------------------
    def live(self, tags: TagTable, ins):
        m, ops = ins.mnemonic, ins.operands
        if m == "PID":
            el = tags.element(ops[0])
            return [("SP", f"{el['SP']:g}"), ("Output", f"{el['CV']:.1f} %")], [("MAN", bool(el["MO"]))]
        if m in ("TON", "TOF", "RTO", "CTU", "CTD"):
            el = tags.element(ops[0])
            bits = ("EN", "TT", "DN") if m in ("TON", "TOF", "RTO") else (("CU" if m == "CTU" else "CD"), "DN")
            return [("Accum", str(el["ACC"]))], [(b, bool(el[b])) for b in bits]
        return [], []

    def io_name(self, direction: str, slot: int, bit: int | None = None) -> str:
        return f"Local:{slot}:{direction}" + ("" if bit is None else f".Data.{bit}")

    def analog_name(self, direction: str, channel: int) -> str:
        return f"Local:{ANALOG_IN_SLOT if direction == 'I' else ANALOG_OUT_SLOT}:{direction}.Ch{channel}Data"

    def io_image(self, tags: TagTable) -> list[tuple[str, int]]:
        return [(f"Local:{s}:{d}", tags.module_data(s, d) & 0xFFFF) for s, d in ((1, "I"), (3, "I"), (2, "O"), (4, "O"))]

    # -- I/O image -------------------------------------------------------------
    def read_inputs(self, tags: TagTable, device: IODevice) -> None:
        for slot, word in device.input_words().items():
            if slot in INPUT_SLOTS:
                tags.set_module_data(slot, "I", word)
        if hasattr(device, "analog_inputs"):
            for ch, volts in device.analog_inputs().items():
                if ch in (0, 1):
                    tags.set_analog(ANALOG_IN_SLOT, "I", ch, volts)

    def write_outputs(self, tags: TagTable, device: IODevice) -> None:
        device.set_output_words({s: tags.module_data(s, "O") & 0xFFFF for s in OUTPUT_SLOTS})
        if hasattr(device, "set_analog_outputs"):
            device.set_analog_outputs({0: tags.analog(ANALOG_OUT_SLOT, "O", 0)})

    def outputs_off(self, tags: TagTable, device: IODevice) -> None:
        device.set_output_words({s: 0 for s in OUTPUT_SLOTS})
        if hasattr(device, "set_analog_outputs"):
            device.set_analog_outputs({0: 0.0})


def _syntax_only(kind: str, op: str) -> str | None:
    """Without the tag list (editor preview): only the shape of the reference is checked."""
    if kind == "value" and isa.parse_literal(op) is not None:
        return None
    return None if REF.match(op.strip()) else f"{op!r} is not a tag reference"


LOGIX = Logix()
