"""Program model: files of rungs; each rung is a tree of series and parallel branches."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator, Union


@dataclass
class Instr:
    mnemonic: str
    operands: list[str] = field(default_factory=list)


@dataclass
class Parallel:
    branches: list["Series"] = field(default_factory=list)


@dataclass
class Series:
    items: list[Union[Instr, Parallel]] = field(default_factory=list)


@dataclass
class Rung:
    body: Series = field(default_factory=Series)
    comment: str = ""


@dataclass
class ProgramFile:
    number: int
    kind: str = "LAD"          # LAD (main, number 2), SBR (routine called with JSR), FC or FB (blocks)
    title: str | None = None   # None: header written without ':'
    rungs: list[Rung] = field(default_factory=list)   # END rung is implicit
    end_comment: str = ""
    language: str = "LD"       # LD (rungs), ST (structured text in `source`) or FBD (`diagram`)
    source: str = ""
    diagram: object = None     # core.fbd.Diagram for FBD
    interface: dict[str, dict[str, str]] = field(default_factory=dict)   # FC/FB: section → {name: type}


@dataclass
class Program:
    files: dict[int, ProgramFile] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)
    tables: dict[str, list[str]] = field(default_factory=dict)   # BTBL/NTBL/FTBL raw values
    symbols_section: bool = True                                   # write SYMBOLS even when empty
    profile: str = "plcyard"                                       # the PLC (earlier styles are converted on load)
    tags: dict[str, dict] = field(default_factory=dict)            # tag-based controllers: {name: {type, value}}
    types: dict[str, dict[str, str]] = field(default_factory=dict)  # user data types: {name: {member: type}}

    @classmethod
    def new(cls, profile: str = "plcyard", language: str = "LD") -> "Program":
        p = cls(symbols_section=False)
        p.files[2] = ProgramFile(2, "LAD", "Main", language=language)
        if language == "FBD":
            from .fbd import Diagram
            p.files[2].diagram = Diagram()
        return p

    @property
    def main(self) -> ProgramFile:
        return self.files[2]

    def routine(self, name: str) -> ProgramFile | None:
        """A routine or block by name (case-insensitive), other than the main one."""
        low = name.strip().strip('"').lower()
        return next((f for n, f in self.files.items() if n != 2 and (f.title or "").lower() == low), None)


def walk(node: Union[Series, Parallel, Instr]) -> Iterator[Instr]:
    """All instructions in a rung tree, left to right."""
    if isinstance(node, Instr):
        yield node
    elif isinstance(node, Series):
        for it in node.items:
            yield from walk(it)
    else:
        for br in node.branches:
            yield from walk(br)


def name_problem(program: Program, name: str) -> str:
    """Why `name` cannot be a new routine, block or data type ("" if it can)."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return f"{name!r} is not a valid name (letters, digits and _; no leading digit)"
    taken = {(f.title or "").lower() for f in program.files.values()} | {t.lower() for t in program.types}
    if name.lower() in taken:
        return f"{name} is already used by a routine, block or data type"
    return ""


def _rename_word(text: str, old: str, new: str) -> str:
    return re.sub(rf'(?<![\w.])("?){re.escape(old)}("?)(?!\w)', lambda m: f"{m[1]}{new}{m[2]}", text, flags=re.I)


def rename_routine(program: Program, old: str, new: str) -> None:
    """Rename a routine or block and every call to it (JSR, CALL, ST calls, FB instance types)."""
    f = program.routine(old)
    f.title = new
    for g in program.files.values():
        for rung in g.rungs:
            for ins in walk(rung.body):
                if ins.mnemonic in ("JSR", "CALL") and ins.operands and ins.operands[0].strip('"').lower() == old.lower():
                    ins.operands[0] = new
        if g.language == "ST":
            g.source = _rename_word(g.source, old, new)
        for sec in g.interface.values():
            for n, t in sec.items():
                if t.lower() == old.lower():
                    sec[n] = new
    for d in program.tags.values():
        if str(d.get("type", "")).lower() == old.lower():
            d["type"] = new


def rename_type(program: Program, old: str, new: str) -> None:
    """Rename a data type where tags, other types and block interfaces use it."""
    program.types = {(new if k == old else k): v for k, v in program.types.items()}
    pattern = re.compile(rf"\b{re.escape(old)}\b", re.I)
    for d in program.tags.values():
        d["type"] = pattern.sub(new, str(d.get("type", "")))
    for ms in program.types.values():
        for n, t in ms.items():
            ms[n] = pattern.sub(new, t)
    for g in program.files.values():
        for sec in g.interface.values():
            for n, t in sec.items():
                sec[n] = pattern.sub(new, t)
