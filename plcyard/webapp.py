"""The web version's bridge: the PLC, the I/O panel, the ladder editor and the exercise checker as
plain JSON for the page (web/app.js), which runs this module in the browser with Pyodide. No Qt.

Selections are ["rung", n], ["instr", n, path] or ["leg", n, path] (an empty branch leg), with the
rung paths of core/edit."""

from __future__ import annotations

import copy
import json

from . import grader, labs
from .core import edit
from .core.plc import PLC
from .core.processor import Processor
from .core.program import Parallel, Program, Series
from .formats import plcy
from .sims.io_panel import DISPLAY_SLOT, INPUT_SLOTS, OUTPUT_SLOTS, IoPanelModel
from .ui import ladder_layout as L
from .ui import notation

EXAMPLES = {"start-stop": "Start/stop with seal-in", "timer-counter": "Timer and counter"}
MAIN = 2


class Session:
    def __init__(self):
        self.plc = Processor()
        self.plc.tracing = True
        self.sim = IoPanelModel()
        self.plc.device = self.sim
        self.program = Program.new()
        self.sel: list | None = None
        self.undo: list[Program] = []
        self.redo: list[Program] = []
        self.dirty = True                  # the editor differs from what the PLC runs
        self.problems: list[str] = []
        self.message = ""
        self.lab: labs.Lab | None = None

    # -- files ----------------------------------------------------------------------------------
    def _open(self, program: Program, lab=None) -> None:
        self.program, self.lab, self.sel = program, lab, None
        self.undo.clear()
        self.redo.clear()
        self.sim = IoPanelModel()
        self.sim.configure_from_symbols(program.symbols)
        self.plc.device = self.sim
        self.plc.set_mode(Processor.PGM)
        self.dirty, self.problems, self.message = True, [], ""

    def new(self) -> None:
        self._open(Program.new())

    def open_example(self, key: str) -> None:
        self._open(plcy.load(labs.SAMPLES / f"{key}.plcy"))

    def open_text(self, text: str) -> str:
        try:
            program = plcy.loads(text)
        except plcy.PlcyError as e:
            return str(e)
        if program.main.language != "LD" or len(program.files) > 1:
            return "The web version edits ladder programs with one routine; open this one in the desktop app."
        self._open(program)
        return ""

    def save_text(self) -> str:
        return plcy.dumps(self.program)

    def exercises(self) -> list[dict]:
        return [{"id": lab.id, "title": lab.title} for lab in labs.load_all() if lab.simulation == "io"]

    def open_exercise(self, lab_id: str) -> dict:
        lab = next(x for x in labs.load_all() if x.id == lab_id)
        self._open(lab.starter(), lab)
        return self.lab_view()

    def lab_view(self) -> dict | None:
        """The open exercise's text in the current notation."""
        lab = self.lab
        return {"id": lab.id, "title": lab.title, "body": notation.show_text(lab.body)} if lab else None

    def check(self) -> dict:
        if self.lab is None:
            return {"error": "Open an exercise first."}
        report = grader.grade(self.lab, self.program)
        return {"error": notation.show_text(report.error), "score": report.score, "passed": report.passed,
                "checks": [{"text": notation.show_text(c.requirement), "passed": c.passed,
                            "detail": notation.show_text(c.detail)} for c in report.checks]}

    # -- PLC ------------------------------------------------------------------------------------
    def download(self) -> None:
        self.problems = [str(d) for d in self.plc.download(self.program)]
        self.dirty = bool(self.problems)
        self.message = "" if self.problems else "Downloaded. Switch to RUN."

    def set_mode(self, mode: str) -> None:
        if mode == Processor.RUN and (self.dirty or self.plc.program is None):
            self.download()
            if self.problems:
                return
        if self.plc.mode == Processor.FAULT:
            self.plc.clear_fault()
        self.plc.set_mode(mode)
        self.message = ""

    def tick(self, ms: float) -> None:
        self.plc.tick(ms)

    def press(self, slot: int, bit: int, on: bool) -> None:
        self.sim.set_pressed(slot, bit, on)

    def thumbwheel(self, digit: int, value: int) -> None:
        self.sim.thumbwheels[digit] = value % 10

    def set_notation(self, n: str) -> None:
        notation.set_current(n)

    # -- editing --------------------------------------------------------------------------------
    @property
    def file(self):
        return self.program.main

    def _edit(self, fn, rung: int | None = None, select=None) -> str:
        before = copy.deepcopy(self.program)
        try:
            result = fn(self.file.rungs[rung].body if rung is not None else self.file)
        except (edit.EditError, IndexError) as e:
            return str(e)
        self.undo.append(before)
        self.redo.clear()
        self.dirty = True
        if select is not None:
            self.sel = select(result)
        return ""

    def select(self, sel: list | None) -> None:
        self.sel = [sel[0], sel[1], tuple(sel[2])] if sel and len(sel) == 3 else sel

    def insert(self, mnemonic: str) -> str:
        """Right of the selected instruction, into the selected empty leg, or into the selected rung."""
        if mnemonic == "RUNG":
            return self.new_rung()
        if mnemonic == "BRANCH":
            return self.add_branch()
        if self.sel is None or self.sel[1] >= len(self.file.rungs):
            self.new_rung()
        kind, n = self.sel[0], self.sel[1]
        node = edit.new_instr(mnemonic, self.plc.profile.specs)
        if kind == "instr":
            sp, k = edit.parent_slot(self.sel[2])
            slot = edit.Slot(sp, k + 1)
        elif kind == "leg":
            slot = edit.Slot(self.sel[2], 0)
        else:
            slot = edit.default_slot(self.file.rungs[n].body, mnemonic, self.plc.profile.specs)
        return self._edit(lambda body: edit.insert(body, slot, node), n, lambda path: ["instr", n, path])

    def new_rung(self) -> str:
        idx = min(self.sel[1] + 1 if self.sel else len(self.file.rungs), len(self.file.rungs))
        return self._edit(lambda f: edit.new_rung(f, idx), None, lambda n: ["rung", n])

    def add_branch(self) -> str:
        if not (self.sel and self.sel[0] == "instr"):
            return "Select the instruction to put in a branch."
        n, path = self.sel[1], self.sel[2]
        return self._edit(lambda body: edit.wrap_in_branch(body, path), n,
                          lambda par: ["leg", n, par + (1,)])

    def add_leg(self) -> str:
        par = self._enclosing_parallel()
        if par is None:
            return "Select an instruction inside a branch."
        n = self.sel[1]
        return self._edit(lambda body: edit.add_leg(body, par), n, lambda leg: ["leg", n, leg])

    def _enclosing_parallel(self) -> tuple | None:
        if self.sel and self.sel[0] == "leg":
            return self.sel[2][:-1]
        if not (self.sel and self.sel[0] == "instr"):
            return None
        body, path = self.file.rungs[self.sel[1]].body, self.sel[2]
        while len(path) >= 2:
            path = path[:-2]
            if isinstance(edit.node_at(body, path), Parallel):
                return path
        return None

    def delete(self) -> str:
        if not self.sel or self.sel[1] >= len(self.file.rungs):
            return ""
        n = self.sel[1]
        if self.sel[0] == "rung":
            return self._edit(lambda f: f.rungs.pop(n), None,
                              lambda _: ["rung", min(n, len(self.file.rungs) - 1)] if self.file.rungs else None)
        path = self.sel[2]
        return self._edit(lambda body: edit.remove(body, path), n, lambda _: ["rung", n])

    def toggle_contact(self) -> str:
        if not (self.sel and self.sel[0] == "instr"):
            return ""
        n, path = self.sel[1], self.sel[2]
        return self._edit(lambda body: edit.toggle_contact(body, path), n, lambda _: ["instr", n, path])

    def set_operands(self, operands: list[str]) -> list[str]:
        """Typed operands (either notation) for the selected instruction; returns their problems."""
        if not (self.sel and self.sel[0] == "instr"):
            return []
        n, path = self.sel[1], self.sel[2]
        problems: list[str] = []

        def apply(body):
            problems.extend(edit.set_operands(body, path, [notation.store(o, self.program) for o in operands],
                                              self.plc.profile, self.program, MAIN))
        self._edit(apply, n, lambda _: ["instr", n, path])
        return problems

    def drop_operand(self, n: int, path: list, address: str) -> list[str]:
        self.select(["instr", n, path])
        node = edit.node_at(self.file.rungs[n].body, tuple(path))
        ops = list(node.operands) or [address]
        ops[0] = address
        return self.set_operands([notation.show(o, self.program) for o in ops])

    def set_comment(self, n: int, text: str) -> str:
        return self._edit(lambda f: setattr(f.rungs[n], "comment", text.strip()), None, lambda _: ["rung", n])

    def set_symbol(self, address: str, text: str) -> None:
        address = notation.store(address, self.program)
        before = copy.deepcopy(self.program)
        if text.strip():
            self.program.symbols[address] = text.strip()
        else:
            self.program.symbols.pop(address, None)
        self.undo.append(before)
        self.sim.configure_from_symbols(self.program.symbols)

    def undo_step(self) -> None:
        if self.undo:
            self.redo.append(self.program)
            self.program = self.undo.pop()
            self.sel, self.dirty = None, True

    def redo_step(self) -> None:
        if self.redo:
            self.undo.append(self.program)
            self.program = self.redo.pop()
            self.sel, self.dirty = None, True

    # -- the page -------------------------------------------------------------------------------
    def palette(self) -> list[dict]:
        """Instruction bar: families of the instruction set, in the current notation."""
        fams: dict[str, list] = {}
        for m, spec in self.plc.profile.specs.items():
            fams.setdefault(spec.family, []).append({"m": m, "name": notation.mnemonic(m), "title": spec.title})
        return [{"family": f, "items": items} for f, items in fams.items()]

    def selected_operands(self) -> dict | None:
        if not (self.sel and self.sel[0] == "instr"):
            return None
        try:
            ins = edit.node_at(self.file.rungs[self.sel[1]].body, self.sel[2])
        except (edit.EditError, IndexError):
            return None
        spec = self.plc.profile.specs.get(ins.mnemonic)
        labels = notation.labels(ins.mnemonic, list(spec.labels)) if spec else []
        return {"mnemonic": notation.mnemonic(ins.mnemonic), "title": spec.title if spec else "",
                "labels": labels, "values": [notation.show(o, self.program) if o != "?" else "" for o in ins.operands]}

    def _live(self) -> bool:
        return not self.dirty and self.plc.mode in (Processor.RUN, Processor.STEP)

    def _rung(self, n: int, width: float) -> dict:
        rung = self.file.rungs[n]
        g = L.layout_rung(rung.body, width, self.plc.profile.specs)
        live, trace, dt = self._live(), self.plc.trace, self.plc.dt

        def wire_on(tag) -> bool:
            hit = trace.get((MAIN, n) + tag[0]) if live else None
            return bool(hit and hit[0 if tag[1] == "in" else 1])

        instrs = []
        for pl in g.instrs:
            ins, spec = pl.instr, self.plc.profile.specs.get(pl.instr.mnemonic)
            block = L.is_block(ins, self.plc.profile.specs)
            hit = trace.get((MAIN, n) + pl.path) if live else None
            on = bool(hit and hit[1]) if block else self._contact_on(spec, ins.operands) if live else False
            extra, pins = [], []
            if live and block and ins.operands:
                try:
                    extra, pins = self.plc.profile.live(dt, ins)
                except Exception:
                    pass
            title = notation.mnemonic(ins.mnemonic)
            ops = [notation.show(o, self.program) for o in ins.operands]
            labels = notation.labels(ins.mnemonic, list(spec.labels)) if spec else []
            instrs.append({
                "path": list(pl.path), "x": pl.x, "y": pl.y, "w": pl.w, "h": pl.h,
                "shape": spec.shape if spec else "block",
                "letter": notation.letter(ins.mnemonic, spec.letter) if spec else "",
                "title": title, "ops": ops, "labels": labels, "on": on,
                "symbol": self.program.symbols.get(ins.operands[0], "") if ins.operands else "",
                "extra": [[notation.live_label(k, ins.mnemonic), v] for k, v in extra],
                "pins": [[notation.pin(k), bool(v)] for k, v in pins if notation.pin(k)]})
        wires = [[w.x1, w.y1, w.x2, w.y2, wire_on(w.tag)] for w in g.wires]
        legs = []
        for path in _empty_legs(rung.body, ()):
            w = next((w for w in g.wires if w.tag == (path, "in") and w.y1 == w.y2), None)
            if w is not None:
                legs.append({"path": list(path), "x": w.x1, "y": w.y1 - L.WIRE_Y, "w": w.x2 - w.x1, "h": L.CONTACT_H})
        return {"comment": notation.show_comment(rung.comment), "width": g.width, "height": g.height,
                "wires": wires, "instrs": instrs, "legs": legs}

    def _contact_on(self, spec, operands) -> bool:
        if not (spec and operands) or spec.shape not in ("contact", "contact_nc", "coil"):
            return False
        try:
            on = self.plc.dt.read_bit(operands[0])
        except Exception:
            return False
        return not on if spec.shape == "contact_nc" else on

    def rungs(self, width: float) -> list[dict]:
        width = max([width] + [L.natural_width(r.body, self.plc.profile.specs) for r in self.file.rungs])
        return [self._rung(n, width) for n in range(len(self.file.rungs))]

    def io(self) -> dict:
        def card(slot, direction):
            pts = []
            for bit in range(16):
                addr = PLC.io_name(direction, slot, bit)
                pt = {"bit": bit, "addr": notation.show(addr), "symbol": self.program.symbols.get(addr, "")}
                if direction == "I":
                    cfg = self.sim.switch(slot, bit)
                    pt.update(pressed=self.sim.pressed.get((slot, bit), False), nc=cfg.normally_closed,
                              momentary=cfg.momentary)
                else:
                    pt["on"] = self.sim.lamp(slot, bit)
                pts.append(pt)
            return {"slot": slot, "name": notation.show(PLC.io_name(direction, slot)), "points": pts}
        display = self.sim.outputs.get(DISPLAY_SLOT, 0)
        return {"inputs": [card(s, "I") for s in INPUT_SLOTS], "outputs": [card(s, "Q") for s in OUTPUT_SLOTS],
                "thumbwheels": list(self.sim.thumbwheels),
                "thumb_name": notation.show(PLC.io_name("I", 5)), "display_name": notation.show(PLC.io_name("Q", 6)),
                "display": [(display >> s) & 0xF for s in (12, 8, 4, 0)]}

    def state(self, width: float) -> str:
        """Everything the page draws, as JSON."""
        return json.dumps({
            "mode": self.plc.mode, "fault": self.plc.fault or "", "scans": self.plc.scan_count,
            "dirty": self.dirty, "problems": self.problems, "message": self.message,
            "notation": notation.current(), "live": self._live(),
            "sel": [self.sel[0], self.sel[1], list(self.sel[2])] if self.sel and len(self.sel) == 3 else self.sel,
            "rungs": self.rungs(width), "io": self.io(), "operands": self.selected_operands(),
            "can_undo": bool(self.undo), "can_redo": bool(self.redo),
            "lab": {"id": self.lab.id, "title": self.lab.title} if self.lab else None,
        })


def _empty_legs(node, path: tuple):
    if isinstance(node, Series):
        for k, item in enumerate(node.items):
            yield from _empty_legs(item, path + (k,))
    elif isinstance(node, Parallel):
        for b, br in enumerate(node.branches):
            if not br.items:
                yield path + (b,)
            else:
                yield from _empty_legs(br, path + (b,))
