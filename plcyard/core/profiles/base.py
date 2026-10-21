"""What a controller family must provide to run on the shared scan engine (core/processor.py).

The engine owns modes, simulated time, the scan loop, subroutine calls, faults and the trace for
the live display. A profile owns everything that differs between PLC families: the memory model
and its address syntax, the instruction set, status bits, how the I/O image maps to a simulation,
and what download and entering RUN do to memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

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

    def __str__(self) -> str:
        where = "LAD 2" if self.file == 2 else f"SBR {self.file}"
        at = f"line {self.line}" if self.line is not None else f"rung {self.rung}"
        return f"{where}, {at}: {self.message}"


class Profile:
    name = ""
    title = ""
    specs: dict[str, isa.Spec] = {}
    memory_errors: tuple[type[Exception], ...] = ()   # raised by memory access → major fault
    memory_fault_code = 0

    # -- editing -----------------------------------------------------------------
    kinds: dict[str, str] = isa.KINDS          # operand kind → hint shown in the operand editor

    def validate(self, mnemonic: str, operands: list[str], program: Program | None = None) -> list[str]:
        """Problems with one instruction as typed; `program` gives declared tags where they matter."""
        return isa.validate(mnemonic, operands, self.specs)

    def normalize(self, operand: str) -> str:
        """How a typed operand is stored."""
        return operand.strip()

    def is_output(self, mnemonic: str) -> bool:
        return isa.is_output(mnemonic, self.specs)

    # -- structured text ---------------------------------------------------------------
    st_blocks: dict[str, tuple[str, tuple[str, ...]]] = {}   # block → (instruction, instance types)

    def check_st(self, program: Program, memory) -> list[Diagnostic]:
        """Parse every ST routine and check its variables and block calls against `memory`."""
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
            problems += [Diagnostic(f.number, 0, m, line) for line, m in st.check(body, memory, blocks)]
        return problems

    def st_call(self, ctx, instance: str, block: str, inputs: dict) -> dict:
        """Run one block call from structured text; returns its outputs by name."""
        raise NotImplementedError

    # -- tag list (tag-based controllers) -------------------------------------------
    tag_types: tuple[str, ...] = ()            # empty: the controller has no tag list (SLC 500)
    tag_fields: tuple[str, ...] = ()           # extra declaration fields shown as columns, e.g. "address"

    def check_tags(self, decls: dict[str, dict]) -> str:
        """Problem with a tag list, or "" when it is fine."""
        return ""

    def tag_value(self, memory, name: str) -> str:
        """A tag's live value as text."""
        return ""

    # -- memory --------------------------------------------------------------
    def new_memory(self) -> Any:
        raise NotImplementedError

    def context(self, memory) -> isa.Context:
        """What executing instructions may touch."""
        raise NotImplementedError

    # -- download ------------------------------------------------------------
    def check(self, program: Program, memory) -> list[Diagnostic]:
        """Everything that stops a download; empty list means it can run."""
        raise NotImplementedError

    def load(self, program: Program, memory) -> None:
        """Memory as a fresh download leaves it (I/O image kept)."""

    def prescan(self, program: Program, memory, ctx: isa.Context) -> None:
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
