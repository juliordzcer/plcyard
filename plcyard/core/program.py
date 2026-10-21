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
    kind: str = "LAD"          # LAD (main, file 2) or SBR
    title: str | None = None   # None: header written without ':'
    rungs: list[Rung] = field(default_factory=list)   # END rung is implicit
    end_comment: str = ""


@dataclass
class Program:
    files: dict[int, ProgramFile] = field(default_factory=dict)
    symbols: dict[str, str] = field(default_factory=dict)
    tables: dict[str, list[str]] = field(default_factory=dict)   # BTBL/NTBL/FTBL raw values
    symbols_section: bool = True                                   # write SYMBOLS even when empty
    profile: str = "slc500"                                        # controller family, see core/profiles

    @classmethod
    def new(cls) -> "Program":
        p = cls()
        p.files[2] = ProgramFile(2, "LAD")
        p.tables = {"BTBL": [], "NTBL": [], "FTBL": []}
        for n in range(3, 10):
            p.files[n] = ProgramFile(n, "SBR", "")
        return p

    @property
    def main(self) -> ProgramFile:
        return self.files[2]


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
