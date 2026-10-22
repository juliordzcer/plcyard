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
    kind: str = "LAD"          # LAD (main, file 2), SBR (subroutine / Logix routine), FC or FB (S7 blocks)
    title: str | None = None   # None: header written without ':'
    rungs: list[Rung] = field(default_factory=list)   # END rung is implicit
    end_comment: str = ""
    language: str = "LD"       # LD (rungs) or ST (structured text in `source`)
    source: str = ""
    interface: dict[str, dict[str, str]] = field(default_factory=dict)   # S7 FC/FB: section → {name: type}


@dataclass
class Program:
    files: dict[int, ProgramFile] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)
    tables: dict[str, list[str]] = field(default_factory=dict)   # BTBL/NTBL/FTBL raw values
    symbols_section: bool = True                                   # write SYMBOLS even when empty
    profile: str = "slc500"                                        # controller family, see core/profiles
    tags: dict[str, dict] = field(default_factory=dict)            # tag-based controllers: {name: {type, value}}
    types: dict[str, dict[str, str]] = field(default_factory=dict)  # user data types: {name: {member: type}}

    @classmethod
    def new(cls, profile: str = "slc500", language: str = "LD") -> "Program":
        if profile != "slc500":             # tag-based controllers: one main routine, tags instead of tables
            p = cls(profile=profile, symbols_section=False)
            p.files[2] = ProgramFile(2, "LAD", "Main" if profile == "s7" else "MainRoutine", language=language)
            return p
        p = cls()
        p.files[2] = ProgramFile(2, "LAD")
        p.tables = {"BTBL": [], "NTBL": [], "FTBL": []}
        for n in range(3, 10):
            p.files[n] = ProgramFile(n, "SBR", "")
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
