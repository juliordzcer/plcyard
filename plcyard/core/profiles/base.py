"""What a controller family must provide to run on the shared scan engine (core/processor.py).

The engine owns modes, simulated time, the scan loop, subroutine calls, faults and the trace for
the live display. A profile owns everything that differs between PLC families: the memory model
and its address syntax, the instruction set, status bits, how the I/O image maps to a simulation,
and what download and entering RUN do to memory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .. import isa
from ..program import Program


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
    line: int | None = None          # structured text: the source line instead of a rung
    block: int | None = None         # function block diagram: the block instead of a rung

    def __str__(self) -> str:
        where = "Main" if self.file == 2 else f"Routine {self.file}"
        at = (f"line {self.line}" if self.line is not None else
              f"block {self.block}" if self.block is not None else f"rung {self.rung}")
        return f"{where}, {at}: {self.message}"


_LOCAL = re.compile(r'(^|\[)(\s*)(#?)("?)([A-Za-z_][A-Za-z0-9_]*)("?)(?=\s*$|\s*[.\[\]])')
_PARAM = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(:=|=>)\s*(.*?)\s*$")


def parse_param(text: str) -> tuple[str, str, str] | None:
    """A block call parameter as written in a ladder CALL box: `Start := Button`, `Run => Lamp`."""
    m = _PARAM.match(text)
    return (m[1], m[2], m[3]) if m else None


def scoped(text: str, instance: str, names: set[str]) -> str:
    """A reference written inside a function block, made absolute: local names (`#Count`, or a bare
    `Count` the block declares) become members of the instance; `"Count"` stays global."""
    p = parse_param(text)
    if p:
        return f"{p[0]}{p[1]}{scoped(p[2], instance, names)}"

    def fix(m):
        lead, ws, hash_, q1, name, q2 = m.groups()
        if q1 or name.lower() not in names:
            return m.group()
        return f"{lead}{ws}{instance}.{name}"
    return _LOCAL.sub(fix, text)


class ScopedMemory:
    """A controller memory seen from inside a block: references go through `scoped` first."""

    def __init__(self, memory, fix: Callable[[str], str]):
        self.memory, self.fix = memory, fix

    def ref(self, text: str, *a):
        return self.memory.ref(self.fix(text), *a)

    def __getattr__(self, name):
        attr = getattr(self.memory, name)
        if name in ("read_bit", "write_bit", "read_word", "write_word", "element", "struct", "type_of"):
            return lambda text, *a: attr(self.fix(text), *a)
        return attr


class Profile:
    name = ""
    title = ""
    specs: dict[str, isa.Spec] = {}
    memory_errors: tuple[type[Exception], ...] = ()   # raised by memory access → major fault
    memory_fault_code = 0

    # -- editing -----------------------------------------------------------------
    kinds: dict[str, str] = {}                 # operand kind → hint shown in the operand editor

    def validate(self, mnemonic: str, operands: list[str], program: Program | None = None,
                 routine: int | None = None) -> list[str]:
        """Problems with one instruction as typed; `program` gives declared tags where they matter."""
        return []

    def normalize(self, operand: str) -> str:
        """How a typed operand is stored."""
        return operand.strip()

    def is_output(self, mnemonic: str) -> bool:
        return isa.is_output(mnemonic, self.specs)

    # -- structured text ---------------------------------------------------------------
    st_blocks: dict[str, tuple[str, tuple[str, ...]]] = {}   # block → (instruction, instance types)

    def check_st(self, program: Program, memory) -> list[Diagnostic]:
        """Parse every ST routine and check its variables and calls against `memory`."""
        from .. import st
        problems = []
        for f in program.files.values():
            if f.language != "ST":
                continue
            if not self.st_blocks:
                problems.append(Diagnostic(f.number, 0, f"{self.title} has no structured text; use ladder", 1))
                continue
            try:
                body = st.parse(f.source)
            except st.StError as e:
                problems.append(Diagnostic(f.number, 0, e.message, e.line))
                continue
            blocks = {k: types for k, (_, types) in self.st_blocks.items()}
            mem = self.scoped_memory(program, memory, f)
            routine = lambda name, ins, outs: self.call_problem(program, mem, name, ins, outs)
            problems += [Diagnostic(f.number, 0, m, line) for line, m in st.check(body, mem, blocks, routine)]
        return problems

    def scoped_memory(self, program: Program, memory, f):
        """`memory` as code inside routine f sees it (its local names resolved)."""
        inst = self.block_instance(program, f)
        if inst is None:
            return memory
        names = {n.lower() for sec in f.interface.values() for n in sec}
        return ScopedMemory(memory, lambda text: scoped(text, inst, names))

    def call_problem(self, program: Program, memory, name: str, inputs: list[str], outputs: list[str]) -> str | None:
        """Problem with calling a routine or block by name from code, or None."""
        return f"{name}: {self.title} cannot call routines"

    def st_call(self, ctx, instance: str, block: str, inputs: dict) -> dict:
        """Run one block call from structured text; returns its outputs by name."""
        raise NotImplementedError

    # -- tag list (tag-based controllers) -------------------------------------------
    tag_types: tuple[str, ...] = ()            # data types offered in the tag list
    tag_fields: tuple[str, ...] = ()           # extra declaration fields shown as columns, e.g. "address"
    routine_kinds: tuple[str, ...] = ()        # kinds of extra routines: SBR (JSR), FC and FB (blocks)
    interface_sections: tuple[str, ...] = ()   # block interface sections (FC/FB)

    def build_memory(self, program: Program):
        """Memory with the program's declarations; raises one of memory_errors when they are wrong."""
        return self.new_memory()

    def check_tags(self, program: Program) -> str:
        """Problem with the tag list, data types or block interfaces, or "" when they are fine."""
        try:
            self.build_memory(program)
        except self.memory_errors as e:
            return str(e)
        return ""

    def block_instance(self, program: Program, f) -> str | None:
        """Where a block's local data lives while it is checked or (for an FC) run: None for routines
        without an interface."""
        return None

    def forceable(self, memory, ref: str) -> str:
        """Problem with forcing this reference, or "" when it is an I/O point that can be forced."""
        return "this controller cannot force"

    def tag_value(self, memory, name: str) -> str:
        """A tag's live value as text."""
        return ""

    # -- memory --------------------------------------------------------------
    def new_memory(self) -> Any:
        raise NotImplementedError

    def context(self, memory):
        """What executing instructions may touch."""
        raise NotImplementedError

    # -- download ------------------------------------------------------------
    def check(self, program: Program, memory) -> list[Diagnostic]:
        """Everything that stops a download; empty list means it can run."""
        raise NotImplementedError

    def load(self, program: Program, memory) -> None:
        """Memory as a fresh download leaves it (I/O image kept)."""

    def prescan(self, program: Program, memory, ctx) -> None:
        """Entering RUN."""

    def reset_timers_counters(self, memory) -> None:
        """Accumulators and status bits to zero (the engine re-applies presets)."""

    # -- scan ----------------------------------------------------------------
    def begin_scan(self, memory, first_pass: bool) -> None:
        pass

    def end_of_program(self, memory) -> None:
        """After the main program, before outputs are written; may raise isa.PlcFault."""

    def end_scan(self, memory) -> None:
        pass

    # -- faults --------------------------------------------------------------
    def set_fault(self, memory, code: int) -> None:
        pass

    def clear_fault(self, memory) -> None:
        pass

    # -- live display ------------------------------------------------------------
    def live(self, memory, ins) -> tuple[list[tuple[str, str]], list[tuple[str, bool]]]:
        """Extra rows (label, value) and status pins (name, on) drawn on an instruction block."""
        return [], []

    # -- naming of the simulated rack ---------------------------------------------
    def io_name(self, direction: str, slot: int, bit: int | None = None) -> str:
        """Name of an input ("I") or output ("O") point, or of the whole module when bit is None."""
        return f"{direction}:{slot}" + ("" if bit is None else f"/{bit}")

    def analog_name(self, direction: str, channel: int) -> str:
        """Name of an analog channel: AI0 tank level, AI1 setpoint knob, AO0 inlet valve."""
        return f"{direction}A{channel}"

    def io_image(self, memory) -> list[tuple[str, int]]:
        """Module words shown on the PLC panel."""
        return []

    # -- I/O image -------------------------------------------------------------
    def read_inputs(self, memory, device: IODevice) -> None:
        pass

    def write_outputs(self, memory, device: IODevice) -> None:
        pass

    def outputs_off(self, memory, device: IODevice) -> None:
        pass
