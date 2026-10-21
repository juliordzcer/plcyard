"""Practice exercises: markdown files with a small header (title, simulation, level, symbols)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .core.program import Program

ROOT = Path(__file__).resolve().parent.parent / "labs"


@dataclass
class Lab:
    id: str
    title: str
    simulation: str          # io | silo | traffic
    level: int
    body: str
    symbols: dict[str, str] = field(default_factory=dict)
    path: Path | None = None

    def starter(self) -> Program:
        """Empty program with the exercise's symbols, so switches come wired (NC, pushbuttons)."""
        p = Program.new()
        p.symbols = dict(self.symbols)
        return p

    @property
    def solution(self) -> Path | None:
        """Reference solution: labs/solutions/<same name as the exercise>.rsl."""
        return self.path.parent.parent / "solutions" / f"{self.path.stem}.rsl" if self.path else None


def parse(text: str, lab_id: str = "") -> Lab:
    head, body = {}, text
    symbols: dict[str, str] = {}
    if text.startswith("---"):
        _, raw, body = text.split("---", 2)
        key = None
        for line in raw.strip().splitlines():
            if line.startswith("- ") and key == "symbols":
                addr, _, desc = line[2:].strip().partition(" ")
                symbols[addr] = desc
            elif ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                head[key] = val.strip()
    return Lab(lab_id, head.get("title", lab_id), head.get("simulation", "io"),
               int(head.get("level", 1)), body.strip(), symbols)


def load_all(lang: str = "en", root: Path = ROOT) -> list[Lab]:
    labs = []
    for f in sorted((root / lang).glob("*.md")):
        lab = parse(f.read_text(encoding="utf-8"), f.stem.split("-")[0])
        lab.path = f
        labs.append(lab)
    return labs
