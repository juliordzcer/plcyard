"""Program model: files of rungs; each rung is a tree of series and parallel branches."""

from __future__ import annotations

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
