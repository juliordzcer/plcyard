"""The web version's bridge: the PLC, the I/O panel, the ladder editor and the exercise checker as
plain JSON for the page (web/app.js), which runs this module in the browser with Pyodide. No Qt.

Selections are ["rung", n], ["instr", n, path] or ["leg", n, path] (an empty branch leg), with the
rung paths of core/edit."""

from __future__ import annotations

import copy
import json
import re

from . import grader, labs, webmachines
from .core import edit, fbd
from .core.plc import PLC
from .core import st
from .core.processor import Processor
from .core.profiles.base import ScopedMemory, scoped
from .core.program import Parallel, Program, ProgramFile, Series, name_problem, rename_routine
from .formats import plcy
from .sims import silo as silo_sim
from .sims import traffic as traffic_sim
from .sims import MODELS
from .sims.io_panel import DISPLAY_SLOT, INPUT_SLOTS, OUTPUT_SLOTS, IoPanelModel
from .sims.silo import SiloModel
from .sims.tank import HIGH, LOW, TankModel
from .sims.traffic import TrafficModel
from .ui import ladder_layout as L
from .ui import notation

SIMS = {"io": ("I/O panel", IoPanelModel), "silo": ("Silo", SiloModel), "traffic": ("Traffic lights", TrafficModel),
        "tank": ("Tank level", TankModel), **{k: MODELS[k] for k in webmachines.SPEC}}
# key → (menu title, simulation, file under data/)
EXAMPLES = {"start-stop": ("Start/stop with seal-in", "io", "samples/start-stop.plcy"),
            "timer-counter": ("Timer and counter", "io", "samples/timer-counter.plcy"),
            "silo": ("Silo filling line", "silo", "samples/silo.plcy"),
            "traffic-lights": ("Traffic lights", "traffic", "samples/traffic-lights.plcy"),
            "tank-on-off": ("Tank level, on/off", "tank", "labs/solutions/11-tank-on-off.plcy"),
            "tank-pid": ("Tank level, PID", "tank", "labs/solutions/12-tank-pid.plcy"),
            "start-stop-st": ("Start/stop in structured text", "io", "samples/start-stop-st.plcy"),
            "silo-st": ("Silo with modes in structured text", "silo", "labs/solutions/09-silo-modes.st.plcy"),
            "traffic-st": ("Traffic lights in structured text", "traffic", "labs/solutions/10-traffic-light.st.plcy"),
            "tank-pid-st": ("Tank level PID in structured text", "tank", "samples/tank-pid-structured-text.plcy"),
            "start-stop-fbd": ("Start/stop in function blocks", "io", "samples/start-stop-fbd.plcy"),
            "silo-fbd": ("Silo with modes in function blocks", "silo", "labs/solutions/09-silo-modes.fbd.plcy"),
            "traffic-fbd": ("Traffic lights in function blocks", "traffic", "labs/solutions/10-traffic-light.fbd.plcy"),
            "tank-pid-fbd": ("Tank level PID in function blocks", "tank", "samples/tank-pid-fbd.plcy"),
            "traffic-routines": ("Traffic lights in routines", "traffic", "samples/traffic-lights-routines.plcy"),
            "silo-fb": ("Silo with a function block", "silo", "samples/silo-function-block.plcy"),
            "motor-fb": ("Motor starters with a function block", "io", "samples/motor-starters-function-block.plcy"),
            "two-tanks": ("Two tanks, cascade PID", "two_tanks", "samples/two-tanks-cascade.plcy"),
            "garage": ("Garage door", "garage", "samples/garage-door.plcy"),
            "mixer": ("Batch mixer in structured text", "mixer", "samples/batch-mixer-st.plcy"),
            "elevator": ("Elevator in structured text", "elevator", "samples/elevator-st.plcy"),
            "bottles": ("Bottle line in structured text", "bottles", "samples/bottle-line-st.plcy"),
            "sorter": ("Sorting conveyor in structured text", "sorter", "samples/sorting-conveyor-st.plcy"),
            "pick-place": ("Pick and place in structured text", "pick_place", "samples/pick-and-place-st.plcy"),
            "parking": ("Parking garage in structured text", "parking", "samples/parking-garage-st.plcy"),
            "pumps": ("Pump station in structured text", "pumps", "samples/pump-station-st.plcy"),
            "hvac": ("Room climate in structured text", "hvac", "samples/room-climate-st.plcy"),
            "washer": ("Washing machine in structured text", "washer", "samples/washing-machine-st.plcy")}
LANGUAGES = ("LD", "ST", "FBD")
KINDS = {"SBR": "Routine", "FC": "Function", "FB": "Function block"}
MAIN = 2


class Session:
    def __init__(self):
        self.plc = Processor()
        self.plc.tracing = True
        self.sim_kind = "io"
        self.sim = IoPanelModel()
        self.plc.device = self.sim
        self.program = Program.new()
        self.sel: list | None = None
        self.cur = MAIN                    # the routine in the editor
        self.undo: list[Program] = []
        self.redo: list[Program] = []
        self.dirty = True                  # the editor differs from what the PLC runs
        self.problems: list[str] = []
        self.message = ""
        self.lab: labs.Lab | None = None
        self._st_key, self._st = None, {}
        self._fbd_key, self._fbd = None, {}

    # -- files ----------------------------------------------------------------------------------
    def _open(self, program: Program, lab=None, sim: str | None = None) -> None:
        self.program, self.lab, self.sel, self.cur = program, lab, None, MAIN
        self.undo.clear()
        self.redo.clear()
        self.plc.set_mode(Processor.PGM)
        self.set_sim(sim or self.sim_kind)
        self.dirty, self.problems, self.message = True, [], ""

    def set_sim(self, kind: str) -> None:
        """A fresh machine of that kind on the PLC's I/O. The I/O panel is wired from the symbols."""
        self.sim_kind = kind if kind in SIMS else "io"
        self.sim = SIMS[self.sim_kind][1]()
        if self.sim_kind == "io":
            self.sim.configure_from_symbols(self.program.symbols)
        self.plc.device = self.sim

    def new(self, language: str = "LD") -> None:
        self._open(Program.new(language=language if language in LANGUAGES else "LD"))

    @property
    def language(self) -> str:
        return self.file.language

    def examples(self) -> list[dict]:
        out = []
        for k, (t, sim, path) in EXAMPLES.items():
            lang = "FBD" if ".fbd." in path or path.endswith("-fbd.plcy") else \
                "ST" if ".st." in path or "-st." in path or "structured-text" in path else "LD"
            out.append({"key": k, "title": t, "sim": sim, "machine": SIMS[sim][0], "language": lang})
        return out

    def open_example(self, key: str) -> None:
        _, sim, path = EXAMPLES[key]
        self._open(plcy.load(labs.DATA / path), sim=sim)

    def open_text(self, text: str) -> str:
        try:
            program = plcy.loads(text)
        except plcy.PlcyError as e:
            return str(e)
        if any(f.language not in LANGUAGES for f in program.files.values()):
            return "This program uses a language the web version does not edit; open it in the desktop app."
        self._open(program)
        return ""

    def save_text(self) -> str:
        return plcy.dumps(self.program)

    def exercises(self) -> list[dict]:
        return [{"id": lab.id, "title": lab.title, "level": lab.level, "sim": lab.simulation,
                 "machine": SIMS[lab.simulation][0]} for lab in labs.load_all() if lab.simulation in SIMS]

    def open_exercise(self, lab_id: str, language: str = "LD") -> dict:
        lab = next(x for x in labs.load_all() if x.id == lab_id)
        program = lab.starter()
        if language == "ST":
            program.main.language = "ST"
            program.main.source = "// Write your program here.\n"
        elif language == "FBD":
            program.main.language, program.main.diagram = "FBD", fbd.Diagram()
        self._open(program, lab, lab.simulation)
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
        self.message = "" if self.problems else "Sent to the PLC."

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
        """Advance the machine and the PLC scan by scan, as on the desktop."""
        while ms > 0:
            self.plc.tick(min(ms, 10.0))
            ms -= 10.0

    def press(self, slot: int, bit: int, on: bool) -> None:
        if self.sim_kind == "io":
            self.sim.set_pressed(slot, bit, on)

    def sim_action(self, name: str, value=None) -> None:
        """A control of the machine on screen: buttons, selector, knobs, parked cars, reset."""
        m, kind = self.sim, self.sim_kind
        if name == "reset":
            self.set_sim(kind)
        elif kind in webmachines.SPEC:
            webmachines.act(m, kind, name, value)
        elif kind in ("silo", "tank") and name in ("start", "stop"):
            setattr(m, f"{name}_pressed", bool(value))
        elif kind == "silo" and name == "selector" and value in ("A", "B", "C"):
            m.selector = value
        elif kind == "traffic" and name in ("button_A", "button_B"):
            m.buttons[name[-1]] = bool(value)
        elif kind == "traffic" and name in ("park_A", "park_B"):
            m.cars[name[-1]].parked = bool(value)
        elif kind == "tank" and name in ("outlet", "setpoint"):
            setattr(m, "outlet" if name == "outlet" else "setpoint_knob", min(max(float(value), 0.0), 100.0))

    def thumbwheel(self, digit: int, value: int) -> None:
        self.sim.thumbwheels[digit] = value % 10

    def set_notation(self, n: str) -> None:
        notation.set_current(n)

    # -- editing --------------------------------------------------------------------------------
    @property
    def file(self):
        return self.program.files.get(self.cur) or self.program.main

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
        self.sel = [sel[0], sel[1], tuple(sel[2])] if sel and len(sel) == 3 else list(sel) if sel else None

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
        if self.language == "FBD":
            return self.fbd_delete()
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
                                              self.plc.profile, self.program, self.cur))
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
            self._after_swap()

    def redo_step(self) -> None:
        if self.redo:
            self.undo.append(self.program)
            self.program = self.redo.pop()
            self._after_swap()

    def _after_swap(self) -> None:
        self.sel, self.dirty = None, True
        if self.cur not in self.program.files:
            self.cur = MAIN

    # -- routines and blocks ------------------------------------------------------------------------
    def routines(self) -> list[dict]:
        return [{"number": n, "title": (f.title or "Main") if n == MAIN else (f.title or str(n)), "kind": f.kind,
                 "language": f.language} for n, f in sorted(self.program.files.items())]

    def open_routine(self, number: int) -> None:
        if number in self.program.files:
            self.cur, self.sel = number, None

    def _structure(self, fn) -> str:
        """A change to the routines (undoable). `fn` returns a problem, and then nothing changes."""
        before = copy.deepcopy(self.program)
        problem = fn()
        if problem:
            self.program = before
            return problem
        self.undo.append(before)
        self.redo.clear()
        self.dirty = True
        return ""

    def add_routine(self, name: str, kind: str, language: str) -> str:
        name = name.strip()
        if kind not in KINDS or language not in LANGUAGES:
            return "Choose a type and a language."
        problem = name_problem(self.program, name)
        if problem:
            return problem
        number = max(self.program.files) + 1

        def fn():
            f = ProgramFile(number, kind, name, language=language)
            if language == "FBD":
                f.diagram = fbd.Diagram()
            self.program.files[number] = f
        problem = self._structure(fn)
        if not problem:
            self.open_routine(number)
        return problem

    def rename_routine(self, number: int, name: str) -> str:
        f, name = self.program.files.get(number), name.strip()
        if f is None or number == MAIN or name == f.title:
            return ""
        return self._structure(lambda: name_problem(self.program, name) or rename_routine(self.program, f.title, name))

    def delete_routine(self, number: int) -> str:
        if number == MAIN or number not in self.program.files:
            return ""
        problem = self._structure(lambda: self.program.files.pop(number) and None)
        self.cur, self.sel = MAIN, None
        return problem

    def interface(self) -> dict | None:
        """The parameters of the function or function block in the editor."""
        f = self.file
        if f.kind not in ("FC", "FB"):
            return None
        secs = [s for s in self.plc.profile.interface_sections if f.kind == "FB" or s != "Static"]
        return {"sections": secs, "rows": [{"section": sec, "name": n, "type": t}
                                           for sec in secs for n, t in f.interface.get(sec, {}).items()]}

    def set_param(self, section: str, old: str, name: str, type_: str) -> str:
        """Add (old == ""), change or (empty name) delete a parameter. Checked against the whole program."""
        f, name, type_ = self.file, name.strip(), type_.strip() or "BOOL"
        view = self.interface()
        if view is None or section not in view["sections"]:
            return "Not a section of this block."
        if name and (not name.replace("_", "a").isalnum() or name[0].isdigit()):
            return "A name is letters, digits and _, not starting with a digit."
        taken = {n.lower() for sec in f.interface.values() for n in sec if not (n == old and sec is f.interface.get(section))}
        if name and name.lower() in taken:
            return f"There is already a parameter {name}."

        def fn():
            rows = list(f.interface.get(section, {}).items())
            if old:
                rows = [(name, type_) if n == old else (n, t) for n, t in rows if n != old or name]
            else:
                rows.append((name, type_))
            f.interface[section] = dict(rows)
            if not f.interface[section]:
                del f.interface[section]
            return self.plc.profile.check_tags(self.program)
        return self._structure(fn)

    # -- structured text ---------------------------------------------------------------------------
    def set_source(self, text: str) -> None:
        """The routine's code as typed (the text box keeps its own undo)."""
        if self.language == "ST" and text != self.file.source:
            self.file.source = text
            self.dirty = True

    def st_syntax(self) -> dict:
        return {"keywords": sorted(st.KEYWORDS), "functions": sorted(st.FUNCS)}

    def _st_check(self) -> dict:
        """Problems (with their lines) and the names the code uses; cached until code or tags change."""
        key = (self.cur, self.file.source, json.dumps(self.program.tags, sort_keys=True), json.dumps(self.program.types),
               json.dumps([[f.title, f.kind, f.interface] for f in self.program.files.values()]))
        if key == self._st_key:
            return self._st
        problems, lines, names = [], [], []
        try:
            body = st.parse(self.file.source)
        except st.StError as e:
            problems, lines = [f"line {e.line}: {e.message}"], [e.line]
        else:
            names = list(dict.fromkeys(n.ref.replace('"', "") for n in st.walk(body)
                                       if isinstance(n, st.Var) and not n.index))
            names += [c.instance.replace('"', "") for c in st.calls(body)
                      if not c.index and c.instance.replace('"', "") not in names]
            prof = self.plc.profile
            try:
                mem = prof.new_memory()
                prof.load(self.program, mem)
            except Exception as e:                   # the tag list itself is wrong
                problems = [f"Tags: {e}"]
            else:
                for d in prof.check_st(self.program, mem):
                    if d.file != self.cur:
                        continue
                    problems.append(f"line {d.line}: {d.message}")
                    lines.append(d.line or 1)
        problems = list(dict.fromkeys(problems))
        self._st_key, self._st = key, {"problems": [notation.show_text(p) for p in problems], "lines": lines,
                                       "names": names}
        return self._st

    def _mem(self):
        """The PLC memory as code in this routine sees it: inside a block, through its (first) instance."""
        f = self.file
        if f.kind not in ("FC", "FB") or self.plc.program is None:
            return self.plc.dt
        try:
            insts = self.plc._instances(f)
        except Exception:                            # the PLC runs an older program
            return self.plc.dt
        if not insts or insts[0] is None:
            return self.plc.dt
        names = {n.lower() for sec in f.interface.values() for n in sec}
        return ScopedMemory(self.plc.dt, lambda text: scoped(text, insts[0], names))

    def _watch(self, names: list[str]) -> list[list[str]]:
        rows, mem, live = [], self._mem(), self._live()
        for n in names:
            text = ""
            if live:
                try:
                    t = mem.ref(n).type.lower()
                    if t in ("timer", "counter", "control", "pid"):
                        text = self.plc.profile.tag_value(mem, n)
                    elif t == "bool":
                        text = "TRUE" if mem.read_bit(n) else "FALSE"
                    else:
                        v = mem.read_word(n)
                        text = f"{v:g}" if isinstance(v, float) else str(v)
                except Exception:
                    text = "?"
            rows.append([notation.show(n, self.program), text])
        return rows

    # -- function block diagram -----------------------------------------------------------------
    @property
    def diagram(self) -> fbd.Diagram:
        if self.file.diagram is None:
            self.file.diagram = fbd.Diagram()
        return self.file.diagram

    def _block_edit(self, fn, select=None) -> str:
        return self._edit(lambda f: fn(self.diagram), None, select)

    def fbd_palette(self) -> list[dict]:
        return [{"family": fam, "items": [{"m": t.name, "name": t.name, "title": t.title}
                                          for t in fbd.LIBRARY.values() if t.family == fam]}
                for fam in fbd.FAMILIES]

    def add_block(self, kind: str, x: float, y: float) -> str:
        if kind not in fbd.LIBRARY:
            return f"No block {kind}."
        bid = self.diagram.next_id()
        return self._block_edit(lambda d: d.blocks.append(fbd.Block(bid, kind, max(0.0, x), max(0.0, y))),
                                lambda _: ["block", bid])

    def move_block(self, bid: int, x: float, y: float) -> str:
        b = self.diagram.block(bid)
        if b is None or (b.x, b.y) == (x, y):
            return ""
        return self._block_edit(lambda d: (setattr(d.block(bid), "x", max(0.0, x)),
                                           setattr(d.block(bid), "y", max(0.0, y))), lambda _: ["block", bid])

    def connect(self, src: int, src_pin: str, dst: int, dst_pin: str) -> str:
        if src == dst:
            return "A block cannot feed itself."

        def fn(d):
            d.wires = [w for w in d.wires if not (w.dst == dst and w.dst_pin == dst_pin)]
            d.wires.append(fbd.Wire(src, src_pin, dst, dst_pin))
            d.block(dst).operands.pop(dst_pin, None)     # a wired input takes no operand
        return self._block_edit(fn, lambda _: ["wire", len(self.diagram.wires) - 1])

    def set_pin(self, bid: int, pin: str, text: str) -> str:
        """The operand of an unwired pin (either notation); empty removes it."""
        def fn(d):
            b = d.block(bid)
            if text.strip():
                b.operands[pin] = notation.store(text.strip(), self.program)
                d.wires = [w for w in d.wires if not (w.dst == bid and w.dst_pin == pin)]
            else:
                b.operands.pop(pin, None)
        return self._block_edit(fn, lambda _: ["block", bid])

    def set_block(self, bid: int, instance: str, operands: dict) -> str:
        """The operand form: the instance tag and the operands of the unwired pins (either notation)."""
        def fn(d):
            b = d.block(bid)
            b.instance = notation.store(instance.strip(), self.program) if instance.strip() else ""
            for pin, text in operands.items():
                if text.strip():
                    b.operands[pin] = notation.store(text.strip(), self.program)
                    d.wires = [w for w in d.wires if not (w.dst == bid and w.dst_pin == pin)]
                else:
                    b.operands.pop(pin, None)
        return self._block_edit(fn, lambda _: ["block", bid])

    def selected_block(self) -> dict | None:
        if not (self.language == "FBD" and self.sel and self.sel[0] == "block"):
            return None
        b = self.diagram.block(self.sel[1])
        if b is None:
            return None
        wired = {w.dst_pin for w in self.diagram.wires if w.dst == b.id}
        return {"id": b.id, "type": b.type, "title": b.type_().title, "kind": b.type_().instance,
                "instance": notation.show(b.instance, self.program) if b.instance else "",
                "variable": b.type_().variable_inputs, "inputs": len(b.input_pins()),
                "pins": [{"name": p.name, "out": out, "wired": p.name in wired and not out,
                          "op": notation.show(b.operands[p.name], self.program) if b.operands.get(p.name) else ""}
                         for out, ps in ((False, b.input_pins()), (True, b.output_pins())) for p in ps],
                "problems": self._fbd_check().get(str(b.id), [])}

    def set_inputs(self, bid: int, n: int) -> str:
        def fn(d):
            b = d.block(bid)
            b.inputs = max(2, n)
            names = {p.name for p in b.input_pins()} | {p.name for p in b.output_pins()}
            d.wires = [w for w in d.wires if w.dst != bid or w.dst_pin in names]
            b.operands = {k: v for k, v in b.operands.items() if k in names}
        return self._block_edit(fn, lambda _: ["block", bid])

    def fbd_delete(self) -> str:
        if not self.sel:
            return ""
        kind, k = self.sel[0], self.sel[1]
        if kind == "block":
            def fn(d):
                d.blocks = [b for b in d.blocks if b.id != k]
                d.wires = [w for w in d.wires if w.src != k and w.dst != k]
        elif kind == "wire":
            def fn(d):
                if k < len(d.wires):
                    d.wires.pop(k)
        else:
            return ""
        return self._block_edit(fn, lambda _: None)

    def _fbd_check(self) -> dict:
        """Problems by block, as on download; cached until the program changes."""
        key = (self.cur, plcy.dumps(self.program))
        if key != self._fbd_key:
            by: dict[str, list[str]] = {}
            for d in self.plc.profile.check(self.program, None):
                if d.file != self.cur:
                    continue
                by.setdefault(str(d.block or 0), []).append(notation.show_text(d.message))
            self._fbd_key, self._fbd = key, by
        return self._fbd

    def _fbd_view(self) -> dict:
        d, live = self.diagram, self._live()
        vals = self.plc.fbd_values.get(self.cur, {}) if live else {}

        def value(bid, pin):
            v = vals.get((bid, pin))
            if v is None or isinstance(v, bool):
                return v
            return f"{v:.2f}" if isinstance(v, float) else str(v)

        def pins(b, ps):
            return [{"name": p.name, "bool": p.type == "BOOL", "value": value(b.id, p.name),
                     "op": notation.show(b.operands[p.name], self.program) if b.operands.get(p.name) else ""}
                    for p in ps]
        blocks = [{"id": b.id, "type": b.type, "title": b.type_().title, "x": b.x, "y": b.y,
                   "kind": b.type_().instance, "instance": notation.show(b.instance, self.program) if b.instance else "",
                   "variable": b.type_().variable_inputs,
                   "inputs": pins(b, b.input_pins()), "outputs": pins(b, b.output_pins())} for b in d.blocks]
        return {"blocks": blocks, "wires": [[w.src, w.src_pin, w.dst, w.dst_pin] for w in d.wires],
                "problems": self._fbd_check()}

    # -- tags -------------------------------------------------------------------------------------
    def tag_types(self) -> list[str]:
        return list(self.plc.profile.tag_types) + sorted(self.program.types)

    def tags(self) -> list[dict]:
        return [{"name": n, "type": str(d.get("type", "")), "comment": d.get("comment", "")}
                for n, d in self.program.tags.items()]

    def _tags_problem(self) -> str:
        try:
            self.plc.profile.build_memory(self.program)
        except Exception as e:
            return str(e)
        return ""

    def set_tag(self, old: str, name: str, type_: str, comment: str) -> str:
        """Add (old == "") or change a tag. Returns a problem, and then changes nothing."""
        name, type_ = name.strip(), type_.strip()
        if not name.replace("_", "a").isalnum() or name[0].isdigit():
            return "A tag name is letters, digits and _, not starting with a digit."
        if name != old and name in self.program.tags:
            return f"There is already a tag {name}."
        before = copy.deepcopy(self.program)
        tags = list(self.program.tags.items())
        decl = dict(self.program.tags.get(old, {}))
        if decl.get("type", "").upper() != type_.upper():
            decl.pop("value", None)
        decl["type"] = type_
        if comment.strip():
            decl["comment"] = comment.strip()
        else:
            decl.pop("comment", None)
        self.program.tags = ({(name if n == old else n): (decl if n == old else d) for n, d in tags}
                             if old else {**self.program.tags, name: decl})
        problem = self._tags_problem()
        if problem:
            self.program = before
            return problem
        self.undo.append(before)
        self.redo.clear()
        self.dirty = True
        return ""

    def delete_tag(self, name: str) -> None:
        if name in self.program.tags:
            self.undo.append(copy.deepcopy(self.program))
            del self.program.tags[name]
            self.dirty = True

    # -- the page -------------------------------------------------------------------------------
    def palette(self) -> list[dict]:
        """Instruction bar: families of the instruction set, in the current notation."""
        fams: dict[str, list] = {}
        for m, spec in self.plc.profile.specs.items():
            fams.setdefault(spec.family, []).append({"m": m, "name": notation.mnemonic(m), "title": spec.title,
                                                     "shape": spec.shape})
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
        live, trace, dt = self._live(), self.plc.trace, self._mem()

        def wire_on(tag) -> bool:
            hit = trace.get((self.cur, n) + tag[0]) if live else None
            return bool(hit and hit[0 if tag[1] == "in" else 1])

        instrs = []
        for pl in g.instrs:
            ins, spec = pl.instr, self.plc.profile.specs.get(pl.instr.mnemonic)
            block = L.is_block(ins, self.plc.profile.specs)
            hit = trace.get((self.cur, n) + pl.path) if live else None
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
            on = self._mem().read_bit(operands[0])
        except Exception:
            return False
        return not on if spec.shape == "contact_nc" else on

    def rungs(self, width: float) -> list[dict]:
        width = max([width] + [L.natural_width(r.body, self.plc.profile.specs) for r in self.file.rungs])
        return [self._rung(n, width) for n in range(len(self.file.rungs))]

    def machine(self) -> dict:
        """What the page draws for the machine on screen, with the address of every device."""
        m, kind = self.sim, self.sim_kind
        if kind in webmachines.SPEC:
            return webmachines.view(m, kind)
        i = lambda bit: notation.show(PLC.io_name("I", 1, bit))
        q = lambda bit: notation.show(PLC.io_name("Q", 2, bit))
        out = {"kind": kind, "events": list(getattr(m, "events", []))[-4:]}
        if kind == "silo":
            out.update(
                belt=silo_sim.CONVEYOR_LEN, box_w=silo_sim.BOX_W, sensor_x=silo_sim.SENSOR_X,
                boxes=[{"x": b.x, "fill": b.fill, "spilled": b.spilled} for b in m.boxes],
                motor=m.motor, solenoid=m.solenoid, prox=m.prox(), level=m.level(), selector=m.selector,
                start=m.start_pressed, stop=m.stop_pressed, lamps=[m.lamp(2), m.lamp(3), m.lamp(4)],
                shipped=len(m.shipped), full=sum(1 for f in m.shipped if f >= 99.0), spill=m.spill,
                addr={"start": i(0), "stop": i(1), "prox": i(3), "level": i(4), "selector": f"{i(5)}…{i(7)}",
                      "motor": q(0), "solenoid": q(1), "run": q(2), "fill": q(3), "full": q(4)})
        elif kind == "traffic":
            out.update(
                road=traffic_sim.ROAD_LEN, stop_line=traffic_sim.STOP_LINE, junction=list(traffic_sim.JUNCTION),
                car_len=traffic_sim.CAR_LEN, crashed=m.crashed,
                lights={r: {c: m.light(r, c) for c in ("red", "amber", "green")} | {"walk": m.walk(r)} for r in "AB"},
                cars={r: {"pos": c.pos, "parked": c.parked, "hidden": c.wait > 0, "passes": c.passes,
                          "waiting": m.waiting(r)} for r, c in m.cars.items()},
                buttons=dict(m.buttons),
                addr={"A": [q(0), q(1), q(2), q(3)], "B": [q(4), q(5), q(6), q(7)],
                      "button_A": i(0), "button_B": i(1), "car_A": i(2), "car_B": i(3)})
        elif kind == "tank":
            pts = list(m.trend)[::5]
            out.update(
                level=m.level, outlet=m.outlet, setpoint=m.setpoint_knob, pump=m.pump, valve=m.valve,
                start=m.start_pressed, stop=m.stop_pressed, high=m.level >= HIGH, low=m.level <= LOW,
                lamps=[m.lamp(1), m.lamp(2)], high_at=HIGH, low_at=LOW,
                trend=[[round(t, 1), sp, round(pv, 2), round(cv, 1)] for t, sp, pv, cv in pts],
                addr={"start": i(0), "stop": i(1), "high": i(2), "low": i(3), "pump": q(0), "run": q(1),
                      "alarm": q(2), "level": notation.show(PLC.analog_name("I", 0)),
                      "setpoint": notation.show(PLC.analog_name("I", 1)),
                      "valve": notation.show(PLC.analog_name("Q", 0))})
        return out

    def io(self) -> dict | None:
        if self.sim_kind != "io":
            return None
        text = plcy.dumps(self.program) + (self.lab.body if self.lab else "")   # the exercise's devices too
        used = lambda addr: re.search(re.escape(addr) + r"(?![\d.])", text) is not None

        def card(slot, direction):
            pts = []
            for bit in range(16):
                addr = PLC.io_name(direction, slot, bit)
                pt = {"bit": bit, "addr": notation.show(addr), "symbol": self.program.symbols.get(addr, ""),
                      "used": used(addr)}
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
                "display": [(display >> s) & 0xF for s in (12, 8, 4, 0)],
                "bcd_used": used(PLC.io_name("I", 5)) or used(PLC.io_name("Q", 6))}

    def state(self, width: float) -> str:
        """Everything the page draws, as JSON."""
        return json.dumps({
            "mode": self.plc.mode, "fault": self.plc.fault or "", "scans": self.plc.scan_count,
            "dirty": self.dirty, "problems": self.problems, "message": self.message,
            "notation": notation.current(), "live": self._live(),
            "sel": [self.sel[0], self.sel[1], list(self.sel[2])] if self.sel and len(self.sel) == 3 else self.sel,
            "language": self.language, "tags": self.tags(),
            "routine": self.cur, "routines": self.routines(), "interface": self.interface(),
            "st": ({"source": self.file.source, **(c := self._st_check()), "watch": self._watch(c["names"])}
                   if self.language == "ST" else None),
            "fbd": self._fbd_view() if self.language == "FBD" else None, "block": self.selected_block(),
            "rungs": self.rungs(width) if self.language == "LD" else [], "io": self.io(), "machine": self.machine(), "sims": [[k, t] for k, (t, _) in SIMS.items()],
            "operands": self.selected_operands(),
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
