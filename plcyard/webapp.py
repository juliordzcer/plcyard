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
from .core import st
from .core.processor import Processor
from .core.program import Parallel, Program, Series
from .formats import plcy
from .sims import silo as silo_sim
from .sims import traffic as traffic_sim
from .sims.io_panel import DISPLAY_SLOT, INPUT_SLOTS, OUTPUT_SLOTS, IoPanelModel
from .sims.silo import SiloModel
from .sims.tank import HIGH, LOW, TankModel
from .sims.traffic import TrafficModel
from .ui import ladder_layout as L
from .ui import notation

SIMS = {"io": ("I/O panel", IoPanelModel), "silo": ("Silo", SiloModel), "traffic": ("Traffic lights", TrafficModel),
        "tank": ("Tank level", TankModel)}
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
            "tank-pid-st": ("Tank level PID in structured text", "tank", "samples/tank-pid-structured-text.plcy")}
LANGUAGES = ("LD", "ST")
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
        self.undo: list[Program] = []
        self.redo: list[Program] = []
        self.dirty = True                  # the editor differs from what the PLC runs
        self.problems: list[str] = []
        self.message = ""
        self.lab: labs.Lab | None = None
        self._st_key, self._st = None, {}

    # -- files ----------------------------------------------------------------------------------
    def _open(self, program: Program, lab=None, sim: str | None = None) -> None:
        self.program, self.lab, self.sel = program, lab, None
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
        return self.program.main.language

    def examples(self) -> list[dict]:
        return [{"key": k, "title": t} for k, (t, _, _) in EXAMPLES.items()]

    def open_example(self, key: str) -> None:
        _, sim, path = EXAMPLES[key]
        self._open(plcy.load(labs.DATA / path), sim=sim)

    def open_text(self, text: str) -> str:
        try:
            program = plcy.loads(text)
        except plcy.PlcyError as e:
            return str(e)
        if program.main.language not in LANGUAGES or len(program.files) > 1:
            return ("The web version edits one ladder or structured text routine; open this one in the "
                    "desktop app.")
        self._open(program)
        return ""

    def save_text(self) -> str:
        return plcy.dumps(self.program)

    def exercises(self) -> list[dict]:
        return [{"id": lab.id, "title": lab.title} for lab in labs.load_all() if lab.simulation in SIMS]

    def open_exercise(self, lab_id: str, language: str = "LD") -> dict:
        lab = next(x for x in labs.load_all() if x.id == lab_id)
        program = lab.starter()
        if language == "ST":
            program.main.language = "ST"
            program.main.source = "// Write your program here.\n"
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
        key = (self.file.source, json.dumps(self.program.tags, sort_keys=True), json.dumps(self.program.types))
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
                    problems.append(f"line {d.line}: {d.message}")
                    lines.append(d.line or 1)
        problems = list(dict.fromkeys(problems))
        self._st_key, self._st = key, {"problems": [notation.show_text(p) for p in problems], "lines": lines,
                                       "names": names}
        return self._st

    def _watch(self, names: list[str]) -> list[list[str]]:
        rows, mem, live = [], self.plc.dt, self._live()
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

    def machine(self) -> dict:
        """What the page draws for the machine on screen, with the address of every device."""
        m, kind = self.sim, self.sim_kind
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
            "language": self.language, "tags": self.tags(),
            "st": ({"source": self.file.source, **(c := self._st_check()), "watch": self._watch(c["names"])}
                   if self.language == "ST" else None),
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
