"""Read and write .rsl ladder files (the plain-text SLC 500 trainer format).

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


def save(program: Program, path: str | Path) -> list[str]:
    """Write the file. Returns the characters that .rsl (Latin-1) cannot hold; they are saved as '?'."""
    text = dumps(program)
    bad = sorted({ch for ch in text if ord(ch) > 0xFF})
    Path(path).write_bytes(text.encode("latin-1", errors="replace"))
    return bad


def loads(text: str) -> Program:
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


def dumps(prog: Program) -> str:
    out: list[str] = []
    for num in sorted(prog.files):
        f = prog.files[num]
        out.append(f"FILE,{f.kind} {f.number}" + ("" if f.title is None else f":{f.title}"))
        for n, rung in enumerate(f.rungs):
            out.append(" ".join([f"SOR,{n}", *_dump_series(rung.body, 0), f"EOR,{n}"]))
            out.append(f"RCM,{rung.comment}")
        n = len(f.rungs)
        out.append(f"SOR,{n} END,{n}")
        out.append(f"RCM,{f.end_comment}")
    for t in TABLES:
        if t not in prog.tables:
            continue
        out.append(t)
        vals = list(prog.tables.get(t, []))
        out += vals + ["0"] * (100 - len(vals))
    if prog.symbols_section or prog.symbols:
        out.append("SYMBOLS")
        out += [f"{a} {d}" for a, d in prog.symbols.items()]
    return "\r\n".join(out) + "\r\n"
