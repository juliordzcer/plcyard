"""Generate the reference pages of the wiki from the code: instructions, function blocks,
structured-text functions and simulations. Run `python -m plcyard.docgen` after changing any of
them; a test fails while the pages are out of date."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

from .core import fbd, isa
from .core.st import FUNCS
from .sims import MODELS
from .ui.notation import MNEMONICS_B as IEC

OUT = Path(__file__).resolve().parent.parent / "docs" / "wiki" / "reference"
FAMILY_ORDER = ["Bit", "Timer/Counter", "Compare", "Math", "Move/Logical", "Array", "Program Control", "Process"]


def instructions() -> str:
    lines = ["# Instructions", "",
             "Every ladder instruction, generated from the instruction set. The *IEC* column is the name",
             "shown in the IEC-symbols notation (Tools → Options). Operands in *italics* are optional.", ""]
    families = sorted({s.family for s in isa.SPECS.values()},
                      key=lambda f: FAMILY_ORDER.index(f) if f in FAMILY_ORDER else 99)
    for fam in families:
        lines += [f"## {fam}", "", "| Mnemonic | IEC | What it does | Operands |", "| --- | --- | --- | --- |"]
        for m, spec in isa.SPECS.items():
            if spec.family != fam:
                continue
            n = len(spec.operands)
            ops = []
            for k, (kind, label) in enumerate(zip(spec.operands, spec.labels)):
                text = f"{label} ({kind.removesuffix('_opt')})"
                ops.append(f"*{text}*" if k >= n - spec.optional or kind.endswith("_opt") else text)
            if m == "CALL":
                ops = [ops[0], "*up to 8 parameters `Name:=value` or `Name=>tag`*"]
            lines.append(f"| `{m}` | `{IEC.get(m, m)}` | {spec.title} | {'<br>'.join(ops) or '—'} |")
        lines.append("")
    for m in ("TON", "CTU", "PID", "CALL"):
        doc = inspect.getdoc(isa.SPECS[m].run)
        if doc:
            lines += [f"### {m}", "", doc, ""]
    return "\n".join(lines)


def blocks() -> str:
    lines = ["# Function blocks (FBD)", "",
             "Blocks of the function block diagram editor. An input pin takes a wire or an operand (a tag,",
             "an address or a constant); an output pin may feed wires and write an operand. Blocks with an",
             "instance keep their state in a tag of that type.", ""]
    for fam in fbd.FAMILIES:
        lines += [f"## {fam}", "", "| Block | What it does | Inputs | Outputs | Instance |", "| --- | --- | --- | --- | --- |"]
        for name, bt in fbd.LIBRARY.items():
            if bt.family != fam:
                continue
            fmt = lambda pins: ", ".join(f"{p.name} ({'BOOL' if p.type == 'BOOL' else 'number'})" for p in pins)
            more = " (more inputs: right-click → Add input)" if bt.variable_inputs else ""
            lines.append(f"| `{name}` | {bt.title}{more} | {fmt(bt.inputs)} | {fmt(bt.outputs)} | {bt.instance or '—'} |")
        lines.append("")
    return "\n".join(lines)


def st_functions() -> str:
    lines = ["# Structured text functions", "",
             "Functions callable in expressions, with their number of arguments. Conversions `X_TO_Y` work",
             "between BOOL, SINT, INT, DINT, LINT, REAL, LREAL, TIME, WORD, DWORD and BYTE.", "",
             "| Function | Arguments |", "| --- | --- |"]
    lines += [f"| `{name}` | {n} |" for name, n in sorted(FUNCS.items())]
    lines += ["", "Blocks called on their tag: `Tag.TON(IN := …, PT := …)`, `TOF`, `TP`, `RTO`, `CTU`",
              "(`CU`, `R`, `PV`), `CTD` (`CD`, `LD`, `PV`), `PID` (`PV`, `SP`, `CV =>`). Routines and blocks:",
              "`JSR(Name);`, `\"Function\"(In := x, Out => y);`, `\"Instance\"(…);`.", ""]
    return "\n".join(lines)


def simulations() -> str:
    lines = ["# Simulations", "",
             "Every simulation, its inputs and outputs as the PLC sees them (canonical addresses; the",
             "mnemonic notation shows them as `Local:<slot>:I.Data.<point>`). Choose one in the",
             "Simulations menu.", ""]
    for key, (title, cls) in MODELS.items():
        doc = inspect.getdoc(inspect.getmodule(cls)) or ""
        lines += [f"## {title}", "", f"Menu key `{key}`.", "", doc, ""]
    return "\n".join(lines)


PAGES = {"instructions.md": instructions, "function-blocks.md": blocks, "st-functions.md": st_functions,
         "simulations.md": simulations}


def generate() -> dict[str, str]:
    return {name: fn() for name, fn in PAGES.items()}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in generate().items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"wrote {len(PAGES)} pages to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
