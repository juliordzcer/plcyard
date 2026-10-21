"""The emulated PLC: download, modes, scan cycle and simulated time.

The processor never reads the wall clock. Callers advance it with tick(ms) so
runs are deterministic; the UI scales ms by the speed slider.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Protocol

from . import isa
from .address import Address
from .datatable import DataTable, DataTableError, to_int16
from .program import Instr, Parallel, Program, Series, walk

SCAN_MS = 10.0
INPUT_FILE, OUTPUT_FILE = 1, 0
FIRST_PASS = "S:1/15"
MAJOR_FAULT, FAULT_CODE = "S:1/13", "S:6"
MAX_NESTING = 8


class IODevice(Protocol):
    """A simulation wired to the rack."""

    def input_words(self) -> dict[int, int]: ...
    def set_output_words(self, words: dict[int, int]) -> None: ...
    def step(self, dt_ms: float) -> None: ...


@dataclass
class Diagnostic:
    file: int
    rung: int
    message: str

    def __str__(self) -> str:
        where = "LAD 2" if self.file == 2 else f"SBR {self.file}"
        return f"{where}, rung {self.rung}: {self.message}"


class Processor:
    PGM, RUN, STEP, FAULT = "PGM", "RUN", "STEP", "FAULT"

    def __init__(self):
        self.dt = DataTable()
        self.program: Program | None = None
        self.mode = self.PGM
        self.device: IODevice | None = None
        self.scan_count = 0
        self.fault: str | None = None
        self.fault_code = 0
        self.now_ms = 0.0
        self._pending_ms = 0.0
        self._first_pass = False
        self._depth = 0
        self.tracing = False
        self.trace: dict[tuple, tuple[bool, bool]] = {}   # (file, rung, *path) -> (in, out)
        self._ctx = isa.Context(self.dt)
        self._ctx.call = self._call

    # -- program --------------------------------------------------------
    def download(self, program: Program) -> list[Diagnostic]:
        problems = []
        for f in program.files.values():
            for i, rung in enumerate(f.rungs):
                for ins in walk(rung.body):
                    problems += [Diagnostic(f.number, i, m) for m in isa.validate(ins.mnemonic, ins.operands)]
                    problems += [Diagnostic(f.number, i, m) for m in self._range_problems(ins)]
                    if ins.mnemonic == "JSR" and not problems:
                        n = int(ins.operands[0].split(":")[1])
                        if n not in program.files or program.files[n].kind != "SBR":
                            problems.append(Diagnostic(f.number, i, f"JSR: subroutine file {n} does not exist"))
        if problems:
            return problems
        was_running = self.mode in (self.RUN, self.STEP)
        self.program = copy.deepcopy(program)
        self.mode = self.PGM
        self.fault, self.fault_code = None, 0
        if was_running:
            self._io_scan_outputs_off()
        self.dt.clear(keep_io=True)           # the new program brings its own data
        self._ctx.timer_marks.clear()
        self._load_tables()
        try:
            self._each_instruction("on_download")
        except (DataTableError, ValueError) as e:
            return [Diagnostic(2, 0, str(e))]
        return []

    def _range_problems(self, ins: Instr) -> list[str]:
        """Direct addresses must exist in the data table (indirect ones are checked at run time)."""
        out = []
        for op in ins.operands:
            if op in ("", "?") or isa.parse_literal(op) is not None or ":" not in op:
                continue
            try:
                a = self.dt.addr(op)
                if a.is_indirect:
                    continue
                if a.is_file_ref:
                    a = Address(a.type, a.file, a.element if a.element is not None else 0)
                self.dt._locate(a)
            except (DataTableError, ValueError) as e:
                if "out of range" in str(e) or "does not exist" in str(e):
                    out.append(f"{ins.mnemonic}: {e}")
        return out

    def _load_tables(self) -> None:
        for name, file_no in (("BTBL", 3), ("NTBL", 7), ("FTBL", 8)):
            for k, raw in enumerate(self.program.tables.get(name, [])):
                f = self.dt.files[file_no]
                if k < len(f.words):
                    f.words[k] = float(raw) if f.type == "F" else to_int16(int(float(raw)))

    def _each_instruction(self, hook: str) -> None:
        for f in self.program.files.values():
            for rung in f.rungs:
                for ins in walk(rung.body):
                    fn = getattr(isa.SPECS[ins.mnemonic], hook)
                    if fn:
                        fn(self._ctx, ins.operands)

    # -- modes ----------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        if mode in (self.RUN, self.STEP) and self.program is None:
            raise RuntimeError("download a program first")
        if mode in (self.RUN, self.STEP) and self.fault:
            raise RuntimeError("clear the fault first")
        entering_run = mode in (self.RUN, self.STEP) and self.mode not in (self.RUN, self.STEP)
        self.mode = mode
        self._pending_ms = 0.0
        if entering_run:
            self._prescan()
        if mode == self.PGM:
            self._io_scan_outputs_off()

    def _prescan(self) -> None:
        """Entering RUN (manual ch. 2): OTE bits reset, OTL/OTU keep their state,
        timers/counters apply their re-entry rules; the next scan is the first pass."""
        for f in self.program.files.values():
            for rung in f.rungs:
                for ins in walk(rung.body):
                    if ins.mnemonic == "OTE":
                        try:
                            self.dt.write_bit(ins.operands[0], False)
                        except DataTableError:
                            pass
        try:
            self._each_instruction("on_prescan")
        except DataTableError:
            pass
        self._first_pass = True

    def clear_fault(self) -> None:
        self.fault, self.fault_code = None, 0
        self.dt.write_bit(MAJOR_FAULT, False)
        self.dt.write_word(FAULT_CODE, 0)
        self.dt.write_bit(isa.OVERFLOW_TRAP, False)
        self.mode = self.PGM

    # -- time -----------------------------------------------------------
    def tick(self, dt_ms: float) -> int:
        """Advance simulated time; runs as many scans as fit. Returns scans run."""
        if self.device:
            self.device.step(dt_ms)
        if self.mode != self.RUN:
            self._read_inputs()
            return 0
        self._pending_ms += dt_ms
        n = 0
        while self._pending_ms >= SCAN_MS and self.mode == self.RUN:
            self._pending_ms -= SCAN_MS
            self.scan()
            n += 1
        return n

    def step(self) -> None:
        """One scan in STEP mode."""
        if self.mode != self.STEP:
            raise RuntimeError("not in STEP mode")
        if self.device:
            self.device.step(SCAN_MS)
        self.scan()

    # -- scan -----------------------------------------------------------
    def scan(self) -> None:
        self.now_ms += SCAN_MS
        self._ctx.now_ms = self.now_ms
        self._read_inputs()
        self.dt.write_bit(FIRST_PASS, self._first_pass)
        self._first_pass = False
        try:
            self._depth = 0
            self._run_file(self.program.main)
            if self.dt.read_bit(isa.OVERFLOW_TRAP):
                raise isa.PlcFault(0x0020, "math overflow or divide by zero (S:5/0 still set at END)")
        except isa.PlcFault as e:
            return self._major_fault(e.code, str(e))
        except DataTableError as e:
            return self._major_fault(0x0024, str(e))
        self.dt.write_bit(FIRST_PASS, False)
        self._write_outputs()
        self.scan_count += 1

    def _major_fault(self, code: int, message: str) -> None:
        self.fault, self.fault_code = message, code
        self.dt.write_bit(MAJOR_FAULT, True)
        self.dt.write_word(FAULT_CODE, code)
        self.mode = self.FAULT
        self._io_scan_outputs_off()

    def _call(self, number: int) -> None:
        if self._depth >= MAX_NESTING:
            raise isa.PlcFault(0x0021, f"subroutines nested deeper than {MAX_NESTING}")
        self._depth += 1
        try:
            self._run_file(self.program.files[number])
        finally:
            self._depth -= 1

    def _run_file(self, f) -> None:
        try:
            for n, rung in enumerate(f.rungs):
                self._series(rung.body, True, (f.number, n))
        except isa.ReturnFromSubroutine:
            if f.kind != "SBR":
                raise isa.PlcFault(0x0021, "RET outside a subroutine")

    # path identifies a node inside a rung for the live wire display (see ui/ladder_layout)
    def _series(self, s: Series, cond: bool, path: tuple) -> bool:
        cin = cond
        for k, item in enumerate(s.items):
            if isinstance(item, Parallel):
                cond = self._parallel(item, cond, path + (k,))
            else:
                cond = self._instr(item, cond, path + (k,))
        if self.tracing:
            self.trace[path] = (cin, cond)
        return cond

    def _parallel(self, p: Parallel, cond: bool, path: tuple) -> bool:
        out = False
        for b, br in enumerate(p.branches):   # every branch executes, even after one is true
            out = self._series(br, cond, path + (b,)) or out
        if self.tracing:
            self.trace[path] = (cond, out)
        return out

    def _instr(self, ins: Instr, cond: bool, path: tuple) -> bool:
        out = isa.SPECS[ins.mnemonic].run(self._ctx, ins.operands, cond)
        if self.tracing:
            self.trace[path] = (cond, out)
        return out

    # -- I/O ------------------------------------------------------------
    def _read_inputs(self) -> None:
        if not self.device:
            return
        for slot, word in self.device.input_words().items():
            self.dt.write_slot(INPUT_FILE, slot, word)

    def _write_outputs(self) -> None:
        if not self.device:
            return
        words = {s: self.dt.read_slot(OUTPUT_FILE, s) for s in range(1, len(self.dt.files[0].words))}
        self.device.set_output_words(words)

    def _io_scan_outputs_off(self) -> None:
        if self.device:
            self.device.set_output_words({s: 0 for s in range(1, len(self.dt.files[0].words))})
