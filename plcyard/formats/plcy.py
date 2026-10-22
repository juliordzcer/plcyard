"""PLCYard project files (.plcy): JSON with every routine and its language, tags, data types and
descriptions. Ladder rungs are stored as token text ("XIC,%I0.0 OTE,%Q0.0") so they stay readable
in a diff. Files made for the earlier controller styles are converted on load."""

from __future__ import annotations

import json
from pathlib import Path

from ..core import profiles
from ..core.program import Program, ProgramFile, Rung
from .rsl import RslError, parse_rung_text, rung_text

FORMAT, VERSION = "plcyard", 1


class PlcyError(ValueError):
    pass


def dumps(prog: Program) -> str:
    doc = {
        "format": FORMAT,
        "version": VERSION,
        "profile": profiles.DEFAULT,
        "programs": [
            {
                "number": f.number,
                "kind": f.kind,
                "title": f.title,
                "language": f.language,
                **({"interface": f.interface} if f.interface else {}),
                **({"source": f.source} if f.language == "ST" else {
                    "rungs": [{"text": rung_text(r.body), "comment": r.comment} for r in f.rungs],
                    "end_comment": f.end_comment}),
            }
            for _, f in sorted(prog.files.items())
        ],
        "tags": prog.tags,
        **({"types": prog.types} if prog.types else {}),
        "symbols": prog.symbols,
    }
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def loads(text: str) -> Program:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise PlcyError(f"not a PLCYard project: {e}") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise PlcyError("not a PLCYard project")
    if doc.get("version", 0) > VERSION:
        raise PlcyError(f"made by a newer PLCYard (file version {doc['version']}); please update")
    from .convert import LEGACY, convert
    style = doc.get("profile", profiles.DEFAULT)
    if style not in (*LEGACY, profiles.DEFAULT):
        raise PlcyError(f"unknown controller {style!r}")
    prog = Program(profile=style)
    prog.symbols = dict(doc.get("symbols", {}))
    prog.tags = {k: dict(v) for k, v in doc.get("tags", {}).items()}
    prog.tables = {k: list(v) for k, v in doc.get("tables", {}).items()}
    prog.types = {k: dict(v) for k, v in doc.get("types", {}).items()}
    for d in doc.get("programs", []):
        language = d.get("language", "LD")
        if language not in ("LD", "ST"):
            raise PlcyError(f"{language} programs are not supported yet")
        f = ProgramFile(int(d["number"]), d.get("kind", "LAD"), d.get("title"), end_comment=d.get("end_comment", ""),
                        language=language, source=d.get("source", ""),
                        interface={k: dict(v) for k, v in d.get("interface", {}).items()})
        try:
            f.rungs = [Rung(parse_rung_text(r.get("text", "")), r.get("comment", "")) for r in d.get("rungs", [])]
        except RslError as e:
            raise PlcyError(f"program {f.number}: {e}") from None
        prog.files[f.number] = f
    if 2 not in prog.files:
        raise PlcyError("no main program (number 2)")
    return convert(prog)


def load(path: str | Path) -> Program:
    return loads(Path(path).read_text(encoding="utf-8"))


def save(program: Program, path: str | Path) -> list[str]:
    """Write the project. Returns characters that could not be stored (none: JSON is UTF-8)."""
    Path(path).write_text(dumps(program), encoding="utf-8")
    return []
