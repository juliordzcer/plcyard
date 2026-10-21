"""The emulated PLC: download, modes, scan cycle and simulated time.

The processor never reads the wall clock. Callers advance it with tick(ms) so
runs are deterministic; the UI scales ms by the speed slider.
"""

from __future__ import annotations

import copy

from . import isa, profiles
from .profiles import Diagnostic, IODevice, Profile  # noqa: F401  (re-exported)
from .program import Instr, Parallel, Program, Series, walk

SCAN_MS = 10.0
MAX_NESTING = 8


class Processor:
    """The shared scan engine. Everything specific to a PLC family lives in its profile."""

    PGM, RUN, STEP, FAULT = "PGM", "RUN", "STEP", "FAULT"

    def __init__(self, profile: str | Profile = profiles.DEFAULT):
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
        self._use(profiles.get(profile) if isinstance(profile, str) else profile)

    def _use(self, profile: Profile) -> None:
        self.profile = profile
        self.dt = profile.new_memory()        # the profile's memory (a DataTable for SLC 500)
        self._ctx = profile.context(self.dt)
        self._ctx.call = self._call

    # -- program --------------------------------------------------------
    def download(self, program: Program) -> list[Diagnostic]:
        target = profiles.get(program.profile)
        problems = target.check(program, self.dt if target is self.profile else target.new_memory())
        if problems:
            return problems
        was_running = self.mode in (self.RUN, self.STEP)
        if was_running:
            self.outputs_off()
        if target is not self.profile:
            self._use(target)
        self.program = copy.deepcopy(program)
        self.mode = self.PGM
        self.fault, self.fault_code = None, 0
        self.profile.load(self.program, self.dt)
        self._ctx.timer_marks.clear()
        try:
            self._each_instruction("on_download")
        except self.profile.memory_errors + (ValueError,) as e:
            return [Diagnostic(2, 0, str(e))]
        return []

    def _each_instruction(self, hook: str) -> None:
        for f in self.program.files.values():
            for rung in f.rungs:
                for ins in walk(rung.body):
                    fn = getattr(self.profile.specs[ins.mnemonic], hook)
                    if fn:
                        fn(self._ctx, ins.operands)

    def reset_timers_counters(self) -> None:
        """Accumulators and status bits to zero; presets come back from the program."""
        self.profile.reset_timers_counters(self.dt)
        if self.program:
            self._each_instruction("on_download")
        self._ctx.timer_marks.clear()

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
            self.outputs_off()

    def _prescan(self) -> None:
        """Entering RUN: the profile's rules, then each instruction's; the next scan is the first pass."""
        self.profile.prescan(self.program, self.dt, self._ctx)
        try:
            self._each_instruction("on_prescan")
        except self.profile.memory_errors:
            pass
        self._first_pass = True

    def clear_fault(self) -> None:
        self.fault, self.fault_code = None, 0
        self.profile.clear_fault(self.dt)
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
        self.profile.begin_scan(self.dt, self._first_pass)
        self._first_pass = False
        try:
            self._depth = 0
            self._run_file(self.program.main)
            self.profile.end_of_program(self.dt)
        except isa.PlcFault as e:
            return self._major_fault(e.code, str(e))
        except self.profile.memory_errors as e:
            return self._major_fault(self.profile.memory_fault_code, str(e))
        self.profile.end_scan(self.dt)
        self._write_outputs()
        self.scan_count += 1

    def _major_fault(self, code: int, message: str) -> None:
        self.fault, self.fault_code = message, code
        self.profile.set_fault(self.dt, code)
        self.mode = self.FAULT
        self.outputs_off()

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
        out = self.profile.specs[ins.mnemonic].run(self._ctx, ins.operands, cond)
        if self.tracing:
            self.trace[path] = (cond, out)
        return out

    # -- I/O ------------------------------------------------------------
    def _read_inputs(self) -> None:
        if self.device:
            self.profile.read_inputs(self.dt, self.device)

    def _write_outputs(self) -> None:
        if self.device:
            self.profile.write_outputs(self.dt, self.device)

    def outputs_off(self) -> None:
        if self.device:
            self.profile.outputs_off(self.dt, self.device)
