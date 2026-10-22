"""Programs written for the earlier controller styles (file profiles "slc500", "logix", "s7"),
converted to the one PLC.

- "slc500" (data table): I:1/0 → %I0.0, O:2/0 → %Q0.0, N7:5 → Values[5], B3:0/5 → Bits[0].5,
  B3/37 → Bits[2].5, T4:0/DN → Timers[0].DN, #N7:0 → Values[0], N7:[N7:0] → Values[Values[0]],
  S:1/15 → FirstScan; the files used become array tags (Values INT[...], Timers TIMER[...], N10 →
  Values10); timer presets in 0.1 s become ms;
  JSR U:3 calls routine SBR3; OSR (one operand) becomes ONS.
- "logix": Local:1:I.Data.0 → %I0.0, S:FS → FirstScan; the accumulator operand of timers and
  counters is dropped; PID operands move to PID, PV, CV, setpoint, tieback, master, inhold.
- "s7": IEC-style type and instruction names (MOVE, CMP==, IN_RANGE, RESET_TIMER, IEC_TIMER, the
  compact PID block…) become the PLC's.
"""

from __future__ import annotations

import re

from ..core.plc import PLC
from ..core.plc.memory import module_to_absolute
from ..core.program import Instr, Program, walk

LEGACY = ("slc500", "logix", "s7")
TIME_BASE_MS = 100


def convert(prog: Program) -> Program:
    """Convert in place (and return) a program of an earlier controller style."""
    style = prog.profile
    if style not in LEGACY:
        return prog
    if style == "slc500":
        _from_slc(prog)
    elif style == "logix":
        _from_logix(prog)
    else:
        _from_s7(prog)
    prog.profile = PLC.name
    prog.symbols_section = False
    return prog


def _instrs(prog: Program):
    for f in prog.files.values():
        for rung in f.rungs:
            yield from walk(rung.body)


def _map_rungs(prog: Program, fn) -> None:
    """fn(instr) → list of instructions to put in its place (empty removes it)."""
    from ..core.program import Parallel, Series

    def series(s: Series) -> None:
        out = []
        for item in s.items:
            if isinstance(item, Parallel):
                for br in item.branches:
                    series(br)
                out.append(item)
            else:
                out.extend(fn(item))
        s.items = out
    for f in prog.files.values():
        for rung in f.rungs:
            series(rung.body)


# -- data-table style ------------------------------------------------------------------------------------
FILE_TYPES = {"B": "INT", "N": "INT", "F": "REAL", "T": "TIMER", "C": "COUNTER", "R": "CONTROL"}
FILE_NAMES = {"B": "Bits", "N": "Values", "F": "Reals", "T": "Timers", "C": "Counters", "R": "Controls"}
DEFAULT_FILES = {"B": 3, "T": 4, "C": 5, "R": 6, "N": 7, "F": 8}


def file_tag(letter: str, number: int) -> str:
    """The array tag a data file becomes: N7 → Values, N10 → Values10, T4 → Timers."""
    return FILE_NAMES[letter] + ("" if DEFAULT_FILES[letter] == number else str(number))
_SLC_IO_BIT = re.compile(r"^([IO]):(\d+)(?:\.(\d+))?/(\d+)$", re.I)
_SLC_IO_WORD = re.compile(r"^([IO]):(\d+)(?:\.(\d+))?$", re.I)
_SLC_ELEM = re.compile(r"^#?([BNFTCR])(\d+):(\d+|\[[^\]]+\])(?:([./])(\w+))?$", re.I)
_SLC_BITFILE = re.compile(r"^#?B(\d+)/(\d+)$", re.I)
SLC_ANALOG = {("I", 7): "%IW64", ("I", 6): "%IW66", ("O", 7): "%QW64"}
SLC_STATUS = {"S:1/15": "FirstScan", "S:0/1": "Overflow", "S:5/0": "Overflow"}


_SLC_TOKEN = re.compile(r"(?<![\w%#\[])(#?(?:[IO]:\d+(?:\.\d+)?(?:/\d+)?|[BNFTCR]\d+:\d+(?:[./][A-Za-z0-9]+)?"
                        r"|B\d+/\d+|S:1/15|S:0/1|S:5/0))(?![\w\]])")


def slc_text(text: str) -> str:
    """Data-table addresses inside free text (comments, descriptions) in the PLC's form."""
    return _SLC_TOKEN.sub(lambda m: _Slc().addr(m[1]), text)


class _Slc:
    def __init__(self):
        self.used: dict[str, int] = {}       # "N7" → elements needed

    def need(self, name: str, index: int) -> None:
        self.used[name] = max(self.used.get(name, 0), index + 1)

    def addr(self, op: str) -> str:
        o = op.strip()
        up = o.upper()
        if up in SLC_STATUS:
            return SLC_STATUS[up]
        m = _SLC_IO_BIT.match(o)
        if m:
            d, slot, word, bit = m[1].upper(), int(m[2]), int(m[3] or 0), int(m[4])
            return PLC.io_name(d, slot, word * 16 + bit)
        m = _SLC_IO_WORD.match(o)
        if m:
            d, slot = m[1].upper(), int(m[2])
            return SLC_ANALOG.get((d, slot)) or PLC.io_name(d, slot)
        m = _SLC_BITFILE.match(o)
        if m:
            name, bit = file_tag("B", int(m[1])), int(m[2])
            self.need(name, bit // 16)
            return f"{name}[{bit // 16}].{bit % 16}"
        m = _SLC_ELEM.match(o)
        if m:
            t, f, el, sep, sub = m[1].upper(), m[2], m[3], m[4], m[5]
            name = file_tag(t, int(f))
            if el.startswith("["):
                index = self.addr(el[1:-1])
                self.need(name, 0)
            else:
                index = el
                self.need(name, int(el))
            out = f"{name}[{index}]"
            if sub:
                out += f".{sub.upper()}" if not sub.isdigit() else f".{int(sub)}"
            return out
        return o


def _from_slc(prog: Program) -> None:
    slc = _Slc()
    sbr_titles = {n: (f.title.strip() if f.title and f.title.strip() and re.fullmatch(r"[A-Za-z_]\w*", f.title.strip())
                      else f"SBR{n}") for n, f in prog.files.items() if n != 2}

    def fix(ins: Instr) -> list[Instr]:
        m = ins.mnemonic
        if m == "SBR":
            return []
        if m == "JSR":
            n = int(ins.operands[0].split(":")[1])
            return [Instr("JSR", [sbr_titles.get(n, f"SBR{n}")])]
        if m == "RET":
            return [Instr("RET", [])]
        ops = [slc.addr(o) for o in ins.operands]
        if m == "OSR":
            return [Instr("ONS", ops)]
        if m in ("TON", "TOF", "RTO"):
            pre = ops[1]
            if re.fullmatch(r"-?\d+", pre):
                pre = str(int(pre) * TIME_BASE_MS)
            return [Instr(m, [ops[0], pre])]
        if m == "SQR":
            return [Instr("SQR", ops)]
        return [Instr(m, ops)]
    _map_rungs(prog, fix)
    for n, f in prog.files.items():
        if n == 2:
            f.kind, f.title = "LAD", "Main"
        else:
            f.kind, f.title = "SBR", sbr_titles[n]
    # drop empty, untitled subroutine files nobody calls
    called = {i.operands[0].lower() for i in _instrs(prog) if i.mnemonic == "JSR"}
    for n in [n for n, f in prog.files.items() if n != 2 and not f.rungs and f.title.lower() not in called]:
        del prog.files[n]
    tables = {"Bits": prog.tables.get("BTBL", []), "Values": prog.tables.get("NTBL", []),
              "Reals": prog.tables.get("FTBL", [])}
    for name, raw in tables.items():
        values = [float(v) if name == "Reals" else int(float(v)) for v in raw]
        while values and not values[-1]:
            values.pop()
        if values:
            slc.need(name, len(values) - 1)
    types = {file_tag(k, n): FILE_TYPES[k] for k, n in DEFAULT_FILES.items()}
    for name, size in sorted(slc.used.items()):
        t = types.get(name) or FILE_TYPES[next(k for k, v in FILE_NAMES.items() if name.startswith(v))]
        decl = {"type": f"{t}[{max(size, 1)}]"}
        raw = tables.get(name, [])
        values = [float(v) if t == "REAL" else int(float(v)) for v in raw][:max(size, 1)]
        while values and not values[-1]:
            values.pop()
        if values:
            decl["value"] = values
        prog.tags[name] = decl
    prog.tables = {}
    prog.symbols = {slc.addr(k): slc_text(v) for k, v in prog.symbols.items()}
    for f in prog.files.values():
        for rung in f.rungs:
            rung.comment = slc_text(rung.comment)
        f.end_comment = slc_text(f.end_comment)


# -- tag style ---------------------------------------------------------------------------------------------
def _from_logix(prog: Program) -> None:
    def fix(ins: Instr) -> list[Instr]:
        ops = [PLC.normalize(o) for o in ins.operands]
        m = ins.mnemonic
        if m in ("CTU", "CTD"):
            ops = ops[:2]
        if m in ("TON", "TOF", "RTO") and len(ops) > 2 and ops[2].strip() == "0":
            ops = ops[:2]
        if m == "PID":
            pid, pv, tie, cv, master, hb, hv = (ops + ["0"] * 7)[:7]
            blank = lambda o: "?" if o.strip() in ("0", "") else o
            ops = [pid, pv, cv, "?", blank(tie), blank(master), blank(hb), blank(hv)]
            while ops and ops[-1] == "?" and len(ops) > 3:
                ops.pop()
        return [Instr(m, ops)]
    _map_rungs(prog, fix)
    for f in prog.files.values():
        if f.language == "ST":
            f.source = re.sub(r"Local:\d+:[IO]\.(?:Data\.\d+|Ch\d+Data|Data)",
                              lambda m: module_to_absolute(m.group()) or m.group(), f.source)
    prog.symbols = {PLC.normalize(k): v for k, v in prog.symbols.items()}
    module = re.compile(r"Local:\d+:[IO]\.(?:Data\.\d+|Ch\d+Data|Data)")
    for f in prog.files.values():
        for rung in f.rungs:
            rung.comment = module.sub(lambda m: module_to_absolute(m.group()) or m.group(), rung.comment)


# -- IEC style ---------------------------------------------------------------------------------------------
S7_TYPES = {"bool": "BOOL", "byte": "SINT", "int": "INT", "dint": "DINT", "real": "REAL", "time": "TIME",
            "iec_timer": "TIMER", "iec_counter": "COUNTER", "pid_compact": "PID"}
S7_PID = {"gain": "KP", "ti": "TI", "td": "TD", "outputupperlimit": "MAXO", "outputlowerlimit": "MINO",
          "manualenable": "MO", "manualvalue": "SO", "invertcontrol": "CA", "setpoint": "SP", "input": "PV",
          "output": "CV"}
S7_INSTR = {"MOVE": "MOV", "CMP==": "EQU", "CMP<>": "NEQ", "CMP<": "LES", "CMP<=": "LEQ", "CMP>": "GRT",
            "CMP>=": "GEQ", "IN_RANGE": "LIM", "RESET_TIMER": "RES"}


def _s7_type(t: str) -> str:
    m = re.match(r"^(Array\s*\[[^\]]*\]\s+of\s+)(\w+)$", t.strip(), re.I)
    if m:
        return m[1] + S7_TYPES.get(m[2].lower(), m[2])
    return S7_TYPES.get(t.strip().lower(), t)


def _from_s7(prog: Program) -> None:
    pids = {n for n, d in prog.tags.items() if str(d.get("type", "")).lower() == "pid_compact"}
    for name, d in prog.tags.items():
        d["type"] = _s7_type(str(d.get("type", "")))
        if name in pids and isinstance(d.get("value"), dict):
            d["value"] = {S7_PID.get(k.lower(), k): v for k, v in d["value"].items()}
    prog.types = {n: {m: _s7_type(t) for m, t in ms.items()} for n, ms in prog.types.items()}
    for f in prog.files.values():
        f.interface = {s: {n: _s7_type(t) for n, t in ms.items()} for s, ms in f.interface.items()}
    pid_member = re.compile(r'("?)(' + "|".join(map(re.escape, pids)) + r')("?)\.(\w+)', re.I) if pids else None

    def member(text: str) -> str:
        if not pid_member:
            return text
        return pid_member.sub(lambda m: f"{m[1]}{m[2]}{m[3]}.{S7_PID.get(m[4].lower(), m[4])}", text)

    def fix(ins: Instr) -> list[Instr]:
        m = S7_INSTR.get(ins.mnemonic, ins.mnemonic)
        ops = [member(o) for o in ins.operands]
        if m == "PID_Compact":
            inst, sp, pv, out = (ops + ["?"] * 4)[:4]
            return [Instr("PID", [inst, pv, out, sp])]
        return [Instr(m, ops)]
    _map_rungs(prog, fix)
    for f in prog.files.values():
        if f.language == "ST":
            f.source = re.sub(r"\.PID_Compact\s*\(([^)]*)\)", _pid_args, member(f.source), flags=re.I)


def _pid_args(m) -> str:
    args = re.sub(r"\bSetpoint\s*:=", "SP :=", m[1], flags=re.I)
    args = re.sub(r"\bInput\s*:=", "PV :=", args, flags=re.I)
    return ".PID(" + re.sub(r"\bOutput\s*=>", "CV =>", args, flags=re.I) + ")"
