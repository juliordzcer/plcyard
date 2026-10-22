"""Structured text: a subset of IEC 61131-3 ST.

    Motor := (Start OR Motor) AND NOT Stop;          // assignments, AND OR XOR NOT, = <> < <= > >=
    IF Level > 90.0 THEN Alarm := TRUE; ELSIF ... ELSE ... END_IF;
    CASE Step OF 0: ...; 1, 2: ...; 3..5: ...; ELSE ... END_CASE;
    FOR i := 1 TO 10 BY 1 DO ... END_FOR;  WHILE ... DO ... END_WHILE;  REPEAT ... UNTIL ... END_REPEAT;
    EXIT; RETURN;
    Delay.TON(IN := Start, PT := T#2s);  Lamp := Delay.Q;     // block calls on an instance tag
    Recipe[Step + 1] := 0;  Pump.Speed := 50.0;              // arrays and structures
    JSR(Filling);  "Scale"(Raw := x, Out => y);  "Motor_DB"(Start := b);   // routines, FC, FB instances
    x := LIMIT(0, ABS(y) * 2, 100);  r := INT_TO_REAL(n);  (* comments *) /* too */

Variables are the controller's tags and addresses (`Motor`, `"Motor"`, `#Motor`, `Delay.DN`,
`Flags.3`, `Local:1:I.Data.0`, `%MW10`). Inside a function or function block, `#Name` is a local variable and
`"Name"` a global one. The program runs top to bottom once per scan.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ..isa import PlcFault

MAX_LOOP = 100_000          # iterations per scan before the watchdog trips


class StError(Exception):
    def __init__(self, line: int, message: str):
        super().__init__(f"line {line}: {message}")
        self.line, self.message = line, message


# -- lexer ---------------------------------------------------------------------------------------
KEYWORDS = {"IF", "THEN", "ELSIF", "ELSE", "END_IF", "CASE", "OF", "END_CASE", "FOR", "TO", "BY", "DO",
            "END_FOR", "WHILE", "END_WHILE", "REPEAT", "UNTIL", "END_REPEAT", "EXIT", "RETURN",
            "AND", "OR", "XOR", "NOT", "MOD", "TRUE", "FALSE"}

_TOKEN = re.compile(r"""
    (?P<ws>[ \t\r]+) | (?P<nl>\n)
  | (?P<comment>//[^\n]*|\(\*.*?\*\)|/\*.*?\*/)
  | (?P<time>(?:T|TIME)\#[0-9A-Za-z_.]+)
  | (?P<based>(?:2|8|16)\#[0-9A-Fa-f_]+)
  | (?P<real>\d[\d_]*\.\d[\d_]*(?:[eE][+-]?\d+)?|\d[\d_]*[eE][+-]?\d+)
  | (?P<int>\d[\d_]*)
  | (?P<module>Local:\d+:[IOio]|S:FS|S:V)
  | (?P<addr>%[IQMiqm][BWDbwd]?\d+(?:\.\d)?)
  | (?P<quoted>"[^"\n]*")
  | (?P<name>\#?[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>:=|=>|\.\.|<>|<=|>=|\*\*|[-+*/=<>(),;:.&\[\]])
""", re.X | re.S)


@dataclass
class Tok:
    kind: str
    text: str
    line: int


def tokens(src: str) -> list[Tok]:
    out, pos, line = [], 0, 1
    while pos < len(src):
        m = _TOKEN.match(src, pos)
        if not m:
            raise StError(line, f"unexpected character {src[pos]!r}")
        kind, text = m.lastgroup, m.group()
        if kind == "name" and text.upper() in KEYWORDS:
            kind, text = "kw", text.upper()
        elif kind == "quoted":                 # kept quoted ("global"), as #local keeps its #
            kind = "name"
        if kind not in ("ws", "nl", "comment"):
            out.append(Tok(kind, text, line))
        line += text.count("\n") if kind == "comment" else (1 if kind == "nl" else 0)
        pos = m.end()
    out.append(Tok("eof", "", line))
    return out


def parse_time(text: str) -> int:
    body = text.split("#", 1)[1].upper().replace("_", "")
    total, ok = 0.0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)(MS|D|H|M|S)", body):
        total += float(num) * {"D": 86400000, "H": 3600000, "M": 60000, "S": 1000, "MS": 1}[unit]
        ok = True
    if not ok or re.sub(r"(\d+(?:\.\d+)?)(MS|D|H|M|S)", "", body):
        raise ValueError(text)
    return int(total)


# -- AST -------------------------------------------------------------------------------------------
@dataclass
class Num:
    value: object
    line: int


@dataclass
class Var:
    ref: str            # what the controller's memory understands: "Delay.DN", "%I0.0"
    line: int
    index: list = field(default_factory=list)    # expressions for the [{}] holes of ref: Recipe[{}]


@dataclass
class Unary:
    op: str
    arg: object
    line: int


@dataclass
class Binary:
    op: str
    left: object
    right: object
    line: int


@dataclass
class Func:
    name: str
    args: list
    line: int


@dataclass
class Assign:
    target: Var
    expr: object
    line: int


@dataclass
class Call:
    instance: str
    block: str                       # TON, TOF, TP, RTO, CTU, CTD, PID
    inputs: dict                     # name → expression
    outputs: dict                    # name → Var  (Q => Lamp)
    line: int
    index: list = field(default_factory=list)    # holes of an instance like Timers[{}]


@dataclass
class RoutineCall:
    name: str                        # a routine (JSR), a function or a function block instance
    inputs: dict
    outputs: dict
    line: int


@dataclass
class If:
    branches: list                   # [(condition, body)]
    orelse: list
    line: int


@dataclass
class Case:
    selector: object
    arms: list                       # [([(lo, hi)], body)]
    orelse: list
    line: int


@dataclass
class For:
    var: Var
    start: object
    stop: object
    step: object
    body: list
    line: int


@dataclass
class While:
    cond: object
    body: list
    line: int


@dataclass
class Repeat:
    body: list
    until: object
    line: int


@dataclass
class Exit:
    line: int


@dataclass
class Return:
    line: int


FUNCS = {"ABS": 1, "SQRT": 1, "MIN": 2, "MAX": 2, "LIMIT": 3, "SEL": 3, "TRUNC": 1, "ROUND": 1,
         "LN": 1, "EXP": 1, "SIN": 1, "COS": 1, "TAN": 1}
_CAST = re.compile(r"^(?:BOOL|SINT|INT|DINT|LINT|REAL|LREAL|TIME|WORD|DWORD|BYTE)_TO_"
                   r"(BOOL|SINT|INT|DINT|LINT|REAL|LREAL|TIME|WORD|DWORD|BYTE)$")


# -- parser ------------------------------------------------------------------------------------------
class Parser:
    def __init__(self, src: str):
        self.t = tokens(src)
        self.i = 0

    @property
    def cur(self) -> Tok:
        return self.t[self.i]

    def take(self) -> Tok:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def at(self, kind: str, text: str | None = None) -> bool:
        return self.cur.kind == kind and (text is None or self.cur.text == text)

    def expect(self, kind: str, text: str | None = None) -> Tok:
        if not self.at(kind, text):
            want = text or kind
            got = self.cur.text or "the end of the program"
            raise StError(self.cur.line, f"expected {want}, found {got!r}")
        return self.take()

    def program(self) -> list:
        body = self.block(())
        if not self.at("eof"):
            raise StError(self.cur.line, f"unexpected {self.cur.text!r}")
        return body

    def block(self, enders: tuple) -> list:
        out = []
        while not self.at("eof") and not (self.cur.kind == "kw" and self.cur.text in enders):
            if self.at("op", ";"):
                self.take()
                continue
            out.append(self.statement())
        return out

    def statement(self):
        tok = self.cur
        if tok.kind == "kw":
            k = tok.text
            if k == "IF":
                return self.if_()
            if k == "CASE":
                return self.case()
            if k == "FOR":
                return self.for_()
            if k == "WHILE":
                self.take()
                cond = self.expr()
                self.expect("kw", "DO")
                body = self.block(("END_WHILE",))
                self.expect("kw", "END_WHILE")
                self.semi()
                return While(cond, body, tok.line)
            if k == "REPEAT":
                self.take()
                body = self.block(("UNTIL",))
                self.expect("kw", "UNTIL")
                cond = self.expr()
                self.expect("kw", "END_REPEAT")
                self.semi()
                return Repeat(body, cond, tok.line)
            if k in ("EXIT", "RETURN"):
                self.take()
                self.semi()
                return Exit(tok.line) if k == "EXIT" else Return(tok.line)
            raise StError(tok.line, f"{k} cannot start a statement")
        target = self.reference()
        if self.at("op", "(") and "." in target.ref and not target.ref.endswith("]"):   # Instance.TON(…)
            inst, _, block = target.ref.rpartition(".")
            call = self.call(inst, block, tok.line)
            call.index = target.index
            return call
        if self.at("op", "(") and not target.index:                 # JSR(Name); "Fc"(…); "Fb_DB"(…);
            if target.ref.upper() == "JSR":
                self.take()
                name = self.reference()
                if self.at("op", ","):                              # JSR(Name, 0): no parameters
                    self.take()
                    self.expect("int")
                self.expect("op", ")")
                self.semi()
                return RoutineCall(name.ref, {}, {}, tok.line)
            c = self.call(target.ref, "", tok.line)
            return RoutineCall(c.instance, c.inputs, c.outputs, tok.line)
        self.expect("op", ":=")
        expr = self.expr()
        self.semi()
        return Assign(target, expr, tok.line)

    def semi(self) -> None:
        if not self.at("op", ";"):
            raise StError(self.t[self.i - 1].line, "missing ; at the end of the statement")
        self.take()

    def call(self, inst: str, block: str, line: int) -> Call:
        self.expect("op", "(")
        inputs, outputs = {}, {}
        while not self.at("op", ")"):
            name = self.expect("name").text
            if self.at("op", ":="):
                self.take()
                inputs[name.upper()] = self.expr()
            elif self.at("op", "=>"):
                self.take()
                outputs[name.upper()] = self.reference()
            else:
                raise StError(self.cur.line, f"write {name} := value (input) or {name} => variable (output)")
            if not self.at("op", ")"):
                self.expect("op", ",")
        self.take()
        self.semi()
        return Call(inst, block.upper(), inputs, outputs, line)

    def if_(self) -> If:
        line = self.take().line
        branches = []
        cond = self.expr()
        self.expect("kw", "THEN")
        branches.append((cond, self.block(("ELSIF", "ELSE", "END_IF"))))
        orelse = []
        while self.at("kw", "ELSIF"):
            self.take()
            cond = self.expr()
            self.expect("kw", "THEN")
            branches.append((cond, self.block(("ELSIF", "ELSE", "END_IF"))))
        if self.at("kw", "ELSE"):
            self.take()
            orelse = self.block(("END_IF",))
        self.expect("kw", "END_IF")
        self.semi()
        return If(branches, orelse, line)

    def case(self) -> Case:
        line = self.take().line
        sel = self.expr()
        self.expect("kw", "OF")
        arms, orelse = [], []
        while not self.at("kw", "END_CASE") and not self.at("kw", "ELSE"):
            labels = [self.case_label()]
            while self.at("op", ","):
                self.take()
                labels.append(self.case_label())
            self.expect("op", ":")
            arms.append((labels, self.case_body()))
        if self.at("kw", "ELSE"):
            self.take()
            orelse = self.block(("END_CASE",))
        self.expect("kw", "END_CASE")
        self.semi()
        return Case(sel, arms, orelse, line)

    def case_body(self) -> list:
        """Statements until the next case label (an integer followed by : , or ..), ELSE or END_CASE."""
        out = []
        while not (self.at("kw", "END_CASE") or self.at("kw", "ELSE") or self.at("eof")):
            if self.at("op", ";"):
                self.take()
                continue
            if self.cur.kind in ("int", "based") or (self.at("op", "-") and self.t[self.i + 1].kind == "int"):
                j = self.i + (2 if self.at("op", "-") else 1)
                if self.t[j].kind == "op" and self.t[j].text in (":", ",", ".."):
                    break
            out.append(self.statement())
        return out

    def case_label(self) -> tuple[int, int]:
        lo = self.const_int()
        hi = lo
        if self.at("op", ".."):
            self.take()
            hi = self.const_int()
        return lo, hi

    def const_int(self) -> int:
        neg = False
        if self.at("op", "-"):
            self.take()
            neg = True
        tok = self.take()
        if tok.kind == "int":
            v = int(tok.text.replace("_", ""))
        elif tok.kind == "based":
            base, digits = tok.text.split("#")
            v = int(digits.replace("_", ""), int(base))
        else:
            raise StError(tok.line, f"a CASE label must be a whole number, not {tok.text!r}")
        return -v if neg else v

    def for_(self) -> For:
        line = self.take().line
        var = self.reference()
        self.expect("op", ":=")
        start = self.expr()
        self.expect("kw", "TO")
        stop = self.expr()
        step = Num(1, line)
        if self.at("kw", "BY"):
            self.take()
            step = self.expr()
        self.expect("kw", "DO")
        body = self.block(("END_FOR",))
        self.expect("kw", "END_FOR")
        self.semi()
        return For(var, start, stop, step, body, line)

    # expressions, lowest precedence first: OR, XOR, AND/&, comparison, + -, * / MOD, **, unary
    def expr(self):
        return self.binary(0)

    LEVELS = [("OR",), ("XOR",), ("AND", "&"), ("=", "<>", "<", "<=", ">", ">="), ("+", "-"), ("*", "/", "MOD")]

    def binary(self, level: int):
        if level == len(self.LEVELS):
            return self.power()
        left = self.binary(level + 1)
        while self.cur.text in self.LEVELS[level] and self.cur.kind in ("op", "kw"):
            tok = self.take()
            op = "AND" if tok.text == "&" else tok.text
            left = Binary(op, left, self.binary(level + 1), tok.line)
        return left

    def power(self):
        left = self.unary()
        if self.at("op", "**"):
            tok = self.take()
            return Binary("**", left, self.power(), tok.line)
        return left

    def unary(self):
        if self.at("op", "-") or self.at("kw", "NOT"):
            tok = self.take()
            return Unary("NOT" if tok.text == "NOT" else "-", self.unary(), tok.line)
        if self.at("op", "+"):
            self.take()
        return self.primary()

    def primary(self):
        tok = self.cur
        if tok.kind == "int":
            self.take()
            return Num(int(tok.text.replace("_", "")), tok.line)
        if tok.kind == "real":
            self.take()
            return Num(float(tok.text.replace("_", "")), tok.line)
        if tok.kind == "based":
            self.take()
            base, digits = tok.text.split("#")
            return Num(int(digits.replace("_", ""), int(base)), tok.line)
        if tok.kind == "time":
            self.take()
            try:
                return Num(parse_time(tok.text), tok.line)
            except ValueError:
                raise StError(tok.line, f"{tok.text} is not a time; write it like T#5s or T#1m30s") from None
        if tok.kind == "kw" and tok.text in ("TRUE", "FALSE"):
            self.take()
            return Num(tok.text == "TRUE", tok.line)
        if self.at("op", "("):
            self.take()
            e = self.expr()
            self.expect("op", ")")
            return e
        if tok.kind == "name" and self.t[self.i + 1].text == "(" and (tok.text.upper() in FUNCS
                                                                   or _CAST.match(tok.text.upper())):
            self.take()
            self.take()
            args = []
            while not self.at("op", ")"):
                args.append(self.expr())
                if not self.at("op", ")"):
                    self.expect("op", ",")
            self.take()
            name = tok.text.upper()
            want = FUNCS.get(name, 1)
            if len(args) != want:
                raise StError(tok.line, f"{name} takes {want} argument(s), got {len(args)}")
            return Func(name, args, tok.line)
        if tok.kind in ("name", "module", "addr"):
            return self.reference()
        raise StError(tok.line, f"expected a value, found {tok.text or 'the end of the program'!r}")

    def reference(self) -> Var:
        tok = self.cur
        if tok.kind not in ("name", "module", "addr"):
            raise StError(tok.line, f"expected a variable, found {tok.text or 'the end of the program'!r}")
        self.take()
        ref = tok.text
        if tok.kind == "addr":
            return Var(ref.upper(), tok.line)
        index = []
        while self.at("op", ".") or self.at("op", "["):
            if self.take().text == "[":
                e = self.expr()
                self.expect("op", "]")
                if isinstance(e, Num) and isinstance(e.value, int) and not isinstance(e.value, bool):
                    ref += f"[{e.value}]"
                else:
                    ref += "[{}]"
                    index.append(e)
                continue
            part = self.take()
            if part.kind not in ("name", "int"):
                raise StError(part.line, f"expected a member or bit after '.', found {part.text!r}")
            ref += "." + part.text
        return Var(ref, tok.line, index)


def parse(src: str) -> list:
    return Parser(src).program()


# -- checks and execution -------------------------------------------------------------------------------
def children(n) -> list:
    if isinstance(n, Var):
        return list(n.index)
    if isinstance(n, Assign):
        return [n.target, n.expr]
    if isinstance(n, Call):
        return [*n.index, *n.inputs.values(), *n.outputs.values()]
    if isinstance(n, RoutineCall):
        return [*n.inputs.values(), *n.outputs.values()]
    if isinstance(n, If):
        return [x for cond, body in n.branches for x in (cond, *body)] + n.orelse
    if isinstance(n, Case):
        return [n.selector, *(x for _, body in n.arms for x in body), *n.orelse]
    if isinstance(n, For):
        return [n.var, n.start, n.stop, n.step, *n.body]
    if isinstance(n, While):
        return [n.cond, *n.body]
    if isinstance(n, Repeat):
        return [*n.body, n.until]
    if isinstance(n, Unary):
        return [n.arg]
    if isinstance(n, Binary):
        return [n.left, n.right]
    if isinstance(n, Func):
        return list(n.args)
    return []


def walk(nodes: list):
    """Every node of a statement list, depth first."""
    stack = list(reversed(nodes))
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(children(n)))


@dataclass
class Program:
    """A parsed ST routine, checked against the controller's memory."""
    body: list
    calls: list = field(default_factory=list)       # Call nodes (for prescan)


class _Exit(Exception):
    pass


class _Return(Exception):
    pass


def is_bool(memory, ref: str) -> bool:
    return memory.ref(ref).type.lower() == "bool"


class Runner:
    """Executes a parsed routine against a controller memory and its block calls."""

    def __init__(self, memory, call_block, call_routine=None):
        self.m = memory
        self.call_block = call_block          # (instance, block, inputs, line) → outputs dict
        self.call_routine = call_routine      # (name, inputs, line) → outputs dict
        self.budget = 0

    def run(self, body: list) -> None:
        self.budget = MAX_LOOP
        try:
            self.block(body)
        except (_Return, _Exit):
            pass
        except (TypeError, ValueError, OverflowError) as e:
            raise PlcFault(0x0601, f"structured text: {e}") from None

    def block(self, body: list) -> None:
        for s in body:
            self.stmt(s)

    def tick(self, line: int) -> None:
        self.budget -= 1
        if self.budget < 0:
            raise PlcFault(0x0601, f"line {line}: loop ran more than {MAX_LOOP} times in one scan (watchdog)")

    def ref(self, v) -> str:
        """A variable's reference with its array indexes evaluated."""
        if not v.index:
            return v.ref
        return v.ref.format(*(int(self.eval(i)) for i in v.index))

    def stmt(self, s) -> None:
        if isinstance(s, Assign):
            self.store(self.ref(s.target), self.eval(s.expr))
        elif isinstance(s, If):
            for cond, body in s.branches:
                if self.truth(cond):
                    return self.block(body)
            self.block(s.orelse)
        elif isinstance(s, Case):
            v = int(self.eval(s.selector))
            for labels, body in s.arms:
                if any(lo <= v <= hi for lo, hi in labels):
                    return self.block(body)
            self.block(s.orelse)
        elif isinstance(s, For):
            i, stop, step = int(self.eval(s.start)), int(self.eval(s.stop)), int(self.eval(s.step))
            if step == 0:
                raise PlcFault(0x0601, f"line {s.line}: FOR with BY 0 never ends")
            try:
                while (i <= stop) if step > 0 else (i >= stop):
                    self.tick(s.line)
                    self.store(self.ref(s.var), i)
                    self.block(s.body)
                    i = int(self.m.read_word(self.ref(s.var))) + step
            except _Exit:
                pass
        elif isinstance(s, While):
            try:
                while self.truth(s.cond):
                    self.tick(s.line)
                    self.block(s.body)
            except _Exit:
                pass
        elif isinstance(s, Repeat):
            try:
                while True:
                    self.tick(s.line)
                    self.block(s.body)
                    if self.truth(s.until):
                        break
            except _Exit:
                pass
        elif isinstance(s, Exit):
            raise _Exit()
        elif isinstance(s, Return):
            raise _Return()
        elif isinstance(s, Call):
            ins = {k: self.eval(v) for k, v in s.inputs.items()}
            inst = s.instance.format(*(int(self.eval(i)) for i in s.index)) if s.index else s.instance
            outs = self.call_block(inst, s.block, ins, s.line)
            for name, var in s.outputs.items():
                if name not in outs:
                    raise PlcFault(0x0601, f"line {s.line}: {s.block} has no output {name}")
                self.store(self.ref(var), outs[name])
        elif isinstance(s, RoutineCall):
            ins = {k: self.eval(v) for k, v in s.inputs.items()}
            outs = self.call_routine(s.name, ins, s.line)
            for name, var in s.outputs.items():
                if name not in outs:
                    raise PlcFault(0x0601, f"line {s.line}: {s.name} has no output {name}")
                self.store(self.ref(var), outs[name])

    def truth(self, e) -> bool:
        return bool(self.eval(e))

    def store(self, ref: str, value) -> None:
        if is_bool(self.m, ref):
            self.m.write_bit(ref, bool(value))
        else:
            self.m.write_word(ref, value)

    def eval(self, e):
        if isinstance(e, Num):
            return e.value
        if isinstance(e, Var):
            ref = self.ref(e)
            return self.m.read_bit(ref) if is_bool(self.m, ref) else self.m.read_word(ref)
        if isinstance(e, Unary):
            v = self.eval(e.arg)
            return (not v) if e.op == "NOT" else -v
        if isinstance(e, Binary):
            op = e.op
            if op == "AND":
                return self.truth(e.left) and self.truth(e.right)
            if op == "OR":
                return self.truth(e.left) or self.truth(e.right)
            a, b = self.eval(e.left), self.eval(e.right)
            if op == "XOR":
                return bool(a) != bool(b)
            if op in ("/", "MOD"):
                if b == 0:
                    raise PlcFault(0x0601, f"line {e.line}: division by zero")
                if op == "MOD":
                    return math.fmod(a, b) if isinstance(a, float) or isinstance(b, float) else int(math.fmod(a, b))
                if isinstance(a, float) or isinstance(b, float):
                    return a / b
                q = abs(a) // abs(b)
                return q if (a >= 0) == (b >= 0) else -q
            return {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "**": lambda: float(a) ** b,
                    "=": lambda: a == b, "<>": lambda: a != b, "<": lambda: a < b, "<=": lambda: a <= b,
                    ">": lambda: a > b, ">=": lambda: a >= b}[op]()
        if isinstance(e, Func):
            args = [self.eval(a) for a in e.args]
            n = e.name
            m = _CAST.match(n)
            if m:
                t = m.group(1)
                v = args[0]
                if t == "BOOL":
                    return bool(v)
                if t in ("REAL", "LREAL"):
                    return float(v)
                return int(round(v)) if isinstance(v, float) else int(v)
            if n == "ABS":
                return abs(args[0])
            if n == "SQRT":
                if args[0] < 0:
                    raise PlcFault(0x0601, f"line {e.line}: square root of a negative number")
                return math.sqrt(args[0])
            if n == "MIN":
                return min(args)
            if n == "MAX":
                return max(args)
            if n == "LIMIT":
                return min(max(args[1], args[0]), args[2])
            if n == "SEL":
                return args[2] if args[0] else args[1]
            if n == "TRUNC":
                return int(args[0])
            if n == "ROUND":
                return int(math.floor(args[0] + 0.5)) if args[0] >= 0 else -int(math.floor(-args[0] + 0.5))
            return {"LN": math.log, "EXP": math.exp, "SIN": math.sin, "COS": math.cos, "TAN": math.tan}[n](args[0])
        raise PlcFault(0x0601, f"cannot evaluate {e!r}")


def static_ref(var: Var) -> str:
    """A reference with computed indexes left open, for checking before it runs."""
    return var.ref.format(*("*" for _ in var.index)) if var.index else var.ref


def check(body: list, memory, blocks: dict[str, tuple[str, ...]], routine=None) -> list[tuple[int, str]]:
    """Problems (line, message) with the variables and block calls of a parsed routine.
    `blocks` maps a block name to the instance types it accepts; `routine(name, inputs, outputs)`
    gives the problem with a routine or block call, or None."""
    problems = []
    seen = set()

    def ref_ok(var: Var, write: bool = False):
        text = static_ref(var)
        key = (text, write, var.line)
        if key in seen:
            return
        seen.add(key)
        try:
            r = memory.ref(text, True)
        except Exception as e:
            problems.append((var.line, str(e)))
            return
        if not memory.is_scalar(r.type):
            hint = "use a member like {0}.Q or call it".format(var.ref) if r.type.lower() in (
                "timer", "counter", "control", "pid") else "use one of its members or elements"
            problems.append((var.line, f"{var.ref} is a {r.type}; {hint}"))

    for n in walk(body):
        if isinstance(n, Assign):
            ref_ok(n.target, True)
        elif isinstance(n, For):
            ref_ok(n.var, True)
        elif isinstance(n, Var):
            ref_ok(n)
        elif isinstance(n, Call):
            types = blocks.get(n.block)
            if types is None:
                problems.append((n.line, f"{n.block} cannot be called here (blocks: {', '.join(sorted(blocks))})"))
                continue
            try:
                inst = n.instance.format(*("*" for _ in n.index)) if n.index else n.instance
                t = memory.ref(inst, True).type
            except Exception as e:
                problems.append((n.line, str(e)))
                continue
            if t not in types:
                problems.append((n.line, f"{n.instance} is a {t}; {n.block} needs a {' or '.join(types)}"))
            for v in n.outputs.values():
                ref_ok(v, True)
        elif isinstance(n, RoutineCall):
            msg = routine(n.name, list(n.inputs), list(n.outputs)) if routine else f"{n.name} cannot be called here"
            if msg:
                problems.append((n.line, msg))
            for v in n.outputs.values():
                ref_ok(v, True)
    return problems


def calls(body: list) -> list[Call]:
    return [n for n in walk(body) if isinstance(n, Call)]
