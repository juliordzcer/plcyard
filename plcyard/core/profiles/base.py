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

    def __str__(self) -> str:
        where = "LAD 2" if self.file == 2 else f"SBR {self.file}"
        return f"{where}, rung {self.rung}: {self.message}"


class Profile:
    name = ""
    title = ""
    specs: dict[str, isa.Spec] = {}
    memory_errors: tuple[type[Exception], ...] = ()   # raised by memory access → major fault
    memory_fault_code = 0

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

    # -- I/O image -------------------------------------------------------------
    def read_inputs(self, memory, device: IODevice) -> None:
        pass

    def write_outputs(self, memory, device: IODevice) -> None:
        pass

    def outputs_off(self, memory, device: IODevice) -> None:
        pass
