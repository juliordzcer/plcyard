"""The emulated PLC: download, modes, scan cycle and simulated time.

The processor never reads the wall clock. Callers advance it with tick(ms) so
runs are deterministic; the UI scales ms by the speed slider.
"""

from __future__ import annotations

import copy

from . import isa, profiles, st
from .profiles import Diagnostic, IODevice, Profile  # noqa: F401  (re-exported)
from .profiles.base import ScopedMemory, scoped
from .program import Instr, Parallel, Program, ProgramFile, Series, walk

SCAN_MS = 10.0
MAX_NESTING = 8


class Processor:
    """The scan engine. The PLC's memory, instructions and I/O mapping live in its profile (core/plc)."""

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
        self._st: dict[int, list] = {}                     # file number -> parsed structured text
        self._fbd: dict = {}                               # (file number, instance) -> diagram state
        self.fbd_values: dict[int, dict] = {}              # file number -> {(block, pin): value} last scan
        self._scope: list[tuple[str, set[str]]] = []       # block instances being run, innermost last
        self.forces: dict[str, bool] = {}                  # forced I/O points -> forced state
        self._use(profiles.get(profile) if isinstance(profile, str) else profile)

    def _use(self, profile: Profile) -> None:
        self.profile = profile
        self.dt = profile.new_memory()        # the PLC memory (tags and I/O)
        self._ctx = profile.context(self.dt)
        self._ctx.call = self._call
        self.forces = {}

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
        self._st = {f.number: st.parse(f.source) for f in self.program.files.values() if f.language == "ST"}
        self._scope = []
        self._fbd, self.fbd_values = {}, {}
        try:
            self._each_instruction("on_download")
        except self.profile.memory_errors + (ValueError,) as e:
            return [Diagnostic(2, 0, str(e))]
        return []

    def _each_instruction(self, hook: str) -> None:
        """Run a download or prescan hook of every instruction, once per instance of a block."""
        for f in self.program.files.values():
            for inst in self._instances(f):
                if inst is not None:
                    self._scope.append((inst, self._locals(f)))
                try:
                    for rung in f.rungs:
                        for ins in walk(rung.body):
                            fn = getattr(self.profile.specs[ins.mnemonic], hook)
                            if fn:
                                fn(self._ctx, self._ops(ins.operands))
                    if hook == "on_prescan" and f.language == "FBD" and f.diagram is not None:
                        self._fbd.pop((f.number, inst), None)
                        for b in f.diagram.blocks:
                            spec = self.profile.specs.get(b.type)
                            if b.instance and spec is not None and spec.on_prescan:
                                spec.on_prescan(self._ctx, [self._fix(b.instance), "0"])
                    if hook == "on_prescan" and f.number in self._st:   # timers called from structured text
                        for call in st.calls(self._st[f.number]):
                            if call.block not in self.profile.st_blocks:
                                continue
                            fn = self.profile.specs[self.profile.st_blocks[call.block][0]].on_prescan
                            if fn:
                                fn(self._ctx, [self._fix(call.instance), "0", "0"])
                finally:
                    if inst is not None:
                        self._scope.pop()

    def _instances(self, f: ProgramFile) -> list[str | None]:
        """Where a routine's local data lives: None for a routine without an interface, every
        instance of a function block, the one hidden instance of a function."""
        if f.kind != "FB":
            return [self.profile.block_instance(self.program, f)]
        out = []
        for name in self.dt.names():
            for ref, t, _ in self.dt.walk(name):
                if t == f.title:
                    out.append(ref)
        return out

    @staticmethod
    def _locals(f: ProgramFile) -> set[str]:
        return {n.lower() for sec in f.interface.values() for n in sec}

    def _fix(self, text: str) -> str:
        if not self._scope:
            return text
        inst, names = self._scope[-1]
        return scoped(text, inst, names)

    def _ops(self, operands: list[str]) -> list[str]:
        return [self._fix(o) for o in operands] if self._scope else operands

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
            self._scope = []
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

    def _call(self, target: int | str, inputs: dict | None = None) -> dict:
        """Run a routine (by number or name, JSR), a function or a function block instance (CALL).
        Inputs go into the block's parameters; returns its outputs by name."""
        if isinstance(target, int):
            f, inst = self.program.files[target], None
        else:
            target = self._fix(target)
            f = self.program.routine(target)
            if f is not None and f.kind == "FB":
                raise isa.PlcFault(0x0021, f"{f.title} is a function block; call one of its instances")
            inst = self.profile.block_instance(self.program, f) if f else None
            if f is None:                                    # a function block instance
                t = self.dt.type_of(target)
                f = next((g for g in self.program.files.values() if g.kind == "FB" and g.title == t), None)
                if f is None:
                    raise isa.PlcFault(0x0021, f"{target} is not a routine or block instance")
                inst = target
        if self._depth >= MAX_NESTING:
            raise isa.PlcFault(0x0021, f"calls nested deeper than {MAX_NESTING}")
        if inst is not None:
            self._pass_in(f, inst, inputs or {})
            self._scope.append((inst, self._locals(f)))
        self._depth += 1
        try:
            self._run_file(f)
        finally:
            self._depth -= 1
            if inst is not None:
                self._scope.pop()
        if inst is None:
            return {}
        el = self.dt.struct(inst)
        return {n.upper(): el[n] for sec in ("Output", "InOut") for n in f.interface.get(sec, {})}

    def _pass_in(self, f: ProgramFile, inst: str, inputs: dict) -> None:
        el = self.dt.struct(inst)
        for n, t in f.interface.get("Temp", {}).items():      # temporary data starts from zero each call
            el[n] = self.dt.ts.default(self.dt.ts.canon(t))
        names = {n.lower(): (sec, n) for sec in f.interface for n in f.interface[sec]}
        for name, value in inputs.items():
            sec, n = names.get(name.lower(), (None, name))
            if sec not in ("Input", "InOut"):
                raise isa.PlcFault(0x0021, f"{f.title} has no input {name}")
            self.dt.write_word(f"{inst}.{n}", value)

    def _run_file(self, f) -> None:
        if f.language == "FBD":
            from . import fbd
            from .plc.instructions import run_pid
            inst = self._scope[-1][0] if self._scope else None
            state = self._fbd.setdefault((f.number, inst), {})
            vals = fbd.Runner(self._ctx, self.profile.specs, run_pid, state).run(f.diagram or fbd.Diagram(), self._fix)
            if self.tracing:
                self.fbd_values[f.number] = dict(vals)
            return
        if f.language == "ST":
            mem = ScopedMemory(self.dt, self._fix) if self._scope else self.dt
            runner = st.Runner(mem, lambda inst, block, ins, line: self._st_block(inst, block, ins),
                               lambda name, ins, line: self._call(name, ins))
            return runner.run(self._st[f.number])
        try:
            for n, rung in enumerate(f.rungs):
                self._series(rung.body, True, (f.number, n))
        except isa.ReturnFromSubroutine:
            pass                                      # RET in the main routine ends it for this scan

    def _st_block(self, inst: str, block: str, inputs: dict) -> dict:
        return self.profile.st_call(self._ctx, self._fix(inst), block, inputs)

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
        out = self.profile.specs[ins.mnemonic].run(self._ctx, self._ops(ins.operands), cond)
        if self.tracing:
            self.trace[path] = (cond, out)
        return out

    # -- I/O ------------------------------------------------------------
    def _read_inputs(self) -> None:
        if self.device:
            self.profile.read_inputs(self.dt, self.device)
        self._apply_forces()

    def _write_outputs(self) -> None:
        self._apply_forces()
        if self.device:
            self.profile.write_outputs(self.dt, self.device)

    # -- forces -----------------------------------------------------------
    def force(self, ref: str, on: bool | None) -> str:
        """Force an I/O point on or off (None removes the force). Returns a problem or ""."""
        if on is None:
            self.forces.pop(ref, None)
            return ""
        problem = self.profile.forceable(self.dt, ref)
        if problem:
            return problem
        self.forces[ref] = on
        self._apply_forces()
        return ""

    def _apply_forces(self) -> None:
        for ref, on in self.forces.items():
            self.dt.write_bit(ref, on)

    def outputs_off(self) -> None:
        if self.device:
            self.profile.outputs_off(self.dt, self.device)
