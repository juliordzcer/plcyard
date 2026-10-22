"""Read .rsl ladder files (an older plain-text, data-table ladder format; converted on load by
formats/convert.py). Its rung token text ("XIC,%I0.0 OTE,%Q0.0") is also how .plcy stores rungs.

Layout::

    FILE,LAD 2[: title]
    SOR,0 XIC,I:1/0 BST,1 XIC,O:2/0 NXB,1 ... BND,1 OTE,O:2/0 EOR,0
    RCM,<rung comment>
    ...                                   last rung of every file: SOR,n END,n EOR? (END only)
    FILE,SBR 3: [title]
    BTBL / NTBL / FTBL                     100 values each (B3, N7, F8)
    SYMBOLS                                "<address> <description>" per line

BST/NXB/BND carry the nesting depth. Lines end with CRLF; text is Latin-1.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.program import Instr, Parallel, Program, ProgramFile, Rung, Series

TABLES = ("BTBL", "NTBL", "FTBL")
_FILE_RX = re.compile(r"^FILE,(LAD|SBR) (\d+)(:(.*))?$")


class RslError(ValueError):
    pass


def load(path: str | Path) -> Program:
    return loads(Path(path).read_bytes().decode("latin-1"))


def loads(text: str) -> Program:
    """The program in the file, converted to the PLC."""
    from .convert import convert
    prog = read(text)
    prog.profile = "slc500"
    return convert(prog)


def read(text: str) -> Program:
    """The program as the file has it (data-table addresses), before conversion."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    prog = Program()
    prog.symbols_section = False
    current: ProgramFile | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _FILE_RX.match(line)
        if m:
            title = m.group(4)
            current = ProgramFile(int(m.group(2)), m.group(1), title)
            prog.files[current.number] = current
            i += 1
            continue
        if line.startswith("SOR,"):
            if current is None:
                raise RslError(f"line {i + 1}: rung outside a FILE section")
            comment = ""
            if i + 1 < len(lines) and lines[i + 1].startswith("RCM,"):
                comment = lines[i + 1][4:]
                i += 1
            tokens = line.split(" ")
            if len(tokens) >= 2 and tokens[1].startswith("END,"):
                current.end_comment = comment
            else:
                current.rungs.append(Rung(_parse_rung(tokens, i), comment))
            i += 1
            continue
        if line in TABLES:
            prog.tables[line] = lines[i + 1:i + 101]
            i += 101
            continue
        if line == "SYMBOLS":
            prog.symbols_section = True
            for s in lines[i + 1:]:
                addr, _, desc = s.partition(" ")
                prog.symbols[addr] = desc
            break
        raise RslError(f"line {i + 1}: unexpected {line[:40]!r}")
    if 2 not in prog.files:
        raise RslError("no main ladder file (FILE,LAD 2)")
    return prog


def _parse_rung(tokens: list[str], line_no: int) -> Series:
    body = tokens[1:-1] if tokens[-1].startswith("EOR,") else tokens[1:]
    pos = 0

    def series(depth: int) -> Series:
        nonlocal pos
        s = Series()
        while pos < len(body):
            mnem, _, rest = body[pos].partition(",")
            if mnem in ("NXB", "BND"):
                return s
            pos += 1
            if mnem == "BST":
                s.items.append(parallel(depth + 1))
            else:
                s.items.append(Instr(mnem, rest.split(",") if rest else []))
        return s

    def parallel(depth: int) -> Parallel:
        nonlocal pos
        p = Parallel([series(depth)])
        while pos < len(body):
            mnem = body[pos].partition(",")[0]
            pos += 1
            if mnem == "NXB":
                p.branches.append(series(depth))
            elif mnem == "BND":
                return p
        raise RslError(f"line {line_no + 1}: branch not closed")

    out = series(0)
    if pos != len(body):
        raise RslError(f"line {line_no + 1}: unexpected {body[pos]!r}")
    return out


def parse_rung_text(text: str) -> Series:
    """A rung body as tokens separated by spaces: "XIC,I:1/0 BST,1 ... BND,1 OTE,O:2/0"."""
    return _parse_rung(["SOR,0", *text.split()], 0) if text.strip() else Series()


def rung_text(body: Series) -> str:
    return " ".join(_dump_series(body, 0))


def _dump_series(s: Series, depth: int) -> list[str]:
    out = []
    for item in s.items:
        if isinstance(item, Parallel):
            d = depth + 1
            out.append(f"BST,{d}")
            for k, br in enumerate(item.branches):
                if k:
                    out.append(f"NXB,{d}")
                out += _dump_series(br, d)
            out.append(f"BND,{d}")
        else:
            out.append(",".join([item.mnemonic, *item.operands]))
    return out
