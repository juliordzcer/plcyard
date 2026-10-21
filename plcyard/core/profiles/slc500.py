"""Allen-Bradley SLC 500 (1747-RM001): file data table (O0, I1, S2, B3, T4, C5, R6, N7, F8),
addresses like N7:0 and I:1/0, status file bits, rack slots as the I/O image."""

from __future__ import annotations

from .. import isa
from ..address import Address
from ..datatable import DataTable, DataTableError, to_int16
from ..program import Instr, Program, walk
from .base import Diagnostic, IODevice, Profile

INPUT_FILE, OUTPUT_FILE = 1, 0
FIRST_PASS = "S:1/15"
MAJOR_FAULT, FAULT_CODE = "S:1/13", "S:6"
TABLE_FILES = (("BTBL", 3), ("NTBL", 7), ("FTBL", 8))


class Slc500(Profile):
    name = "slc500"
    title = "SLC 500"
    specs = isa.SPECS
    memory_errors = (DataTableError,)
    memory_fault_code = 0x0024

    def new_memory(self) -> DataTable:
        return DataTable()

    def context(self, memory: DataTable) -> isa.Context:
        return isa.Context(memory)

    # -- download ------------------------------------------------------------
    def check(self, program: Program, memory: DataTable) -> list[Diagnostic]:
        problems = []
        for f in program.files.values():
            for i, rung in enumerate(f.rungs):
                for ins in walk(rung.body):
                    problems += [Diagnostic(f.number, i, m) for m in isa.validate(ins.mnemonic, ins.operands)]
                    problems += [Diagnostic(f.number, i, m) for m in self._range_problems(memory, ins)]
                    if ins.mnemonic == "JSR" and not problems:
                        n = int(ins.operands[0].split(":")[1])
                        if n not in program.files or program.files[n].kind != "SBR":
                            problems.append(Diagnostic(f.number, i, f"JSR: subroutine file {n} does not exist"))
        return problems

    @staticmethod
    def _range_problems(dt: DataTable, ins: Instr) -> list[str]:
        """Direct addresses must exist in the data table (indirect ones are checked at run time)."""
        out = []
        for op in ins.operands:
            if op in ("", "?") or isa.parse_literal(op) is not None or ":" not in op:
                continue
            try:
                a = dt.addr(op)
                if a.is_indirect:
                    continue
                if a.is_file_ref:
                    a = Address(a.type, a.file, a.element if a.element is not None else 0)
                dt._locate(a)
            except (DataTableError, ValueError) as e:
                if "out of range" in str(e) or "does not exist" in str(e):
                    out.append(f"{ins.mnemonic}: {e}")
        return out

    def load(self, program: Program, dt: DataTable) -> None:
        dt.clear(keep_io=True)           # the new program brings its own data
        for name, file_no in TABLE_FILES:
            f = dt.files[file_no]
            for k, raw in enumerate(program.tables.get(name, [])):
                if k < len(f.words):
                    f.words[k] = float(raw) if f.type == "F" else to_int16(int(float(raw)))

    def prescan(self, program: Program, dt: DataTable, ctx: isa.Context) -> None:
        """Manual ch. 2: OTE bits reset, OTL/OTU keep their state, timers/counters apply their
        re-entry rules."""
        for f in program.files.values():
            for rung in f.rungs:
                for ins in walk(rung.body):
                    if ins.mnemonic == "OTE":
                        try:
                            dt.write_bit(ins.operands[0], False)
                        except DataTableError:
                            pass

    def reset_timers_counters(self, dt: DataTable) -> None:
        for n in (4, 5):
            f = dt.files[n]
            f.words = [0] * len(f.words)

    # -- scan ----------------------------------------------------------------
    def begin_scan(self, dt: DataTable, first_pass: bool) -> None:
        dt.write_bit(FIRST_PASS, first_pass)

    def end_of_program(self, dt: DataTable) -> None:
        if dt.read_bit(isa.OVERFLOW_TRAP):
            raise isa.PlcFault(0x0020, "math overflow or divide by zero (S:5/0 still set at END)")

    def end_scan(self, dt: DataTable) -> None:
        dt.write_bit(FIRST_PASS, False)

    # -- faults --------------------------------------------------------------
    def set_fault(self, dt: DataTable, code: int) -> None:
        dt.write_bit(MAJOR_FAULT, True)
        dt.write_word(FAULT_CODE, code)

    def clear_fault(self, dt: DataTable) -> None:
        dt.write_bit(MAJOR_FAULT, False)
        dt.write_word(FAULT_CODE, 0)
        dt.write_bit(isa.OVERFLOW_TRAP, False)

    # -- I/O image -------------------------------------------------------------
    def read_inputs(self, dt: DataTable, device: IODevice) -> None:
        for slot, word in device.input_words().items():
            dt.write_slot(INPUT_FILE, slot, word)

    def write_outputs(self, dt: DataTable, device: IODevice) -> None:
        device.set_output_words({s: dt.read_slot(OUTPUT_FILE, s) for s in range(1, len(dt.files[0].words))})

    def outputs_off(self, dt: DataTable, device: IODevice) -> None:
        device.set_output_words({s: 0 for s in range(1, len(dt.files[0].words))})


SLC500 = Slc500()
