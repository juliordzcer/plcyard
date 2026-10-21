"""Math, move/logical and BCD conversion (manual chapters 4 and 5).

Integer results saturate at ±32767 with S:0/1 and the overflow trap S:5/0 set
(S:2/14 clear, the default). S:5/0 still set at END is a major fault (0020h).
"""

from __future__ import annotations

import math as _m

from . import (CARRY, MATH_HIGH, MATH_LOW, OVERFLOW, OVERFLOW_TRAP, instruction,
               round_half_away)

ABC = ["value", "value", "word"]
ABC_LABELS = ["Source A", "Source B", "Dest"]


def _any_float(ctx, *ops):
    return any(ctx.is_float(o) for o in ops)


@instruction("ADD", "Add", "Math", ABC, ABC_LABELS, output=True)
def add(ctx, ops, cond):
    if cond:
        a, b = ctx.value(ops[0]), ctx.value(ops[1])
        carry = not _any_float(ctx, *ops[:2]) and ((int(a) & 0xFFFF) + (int(b) & 0xFFFF)) > 0xFFFF
        ctx.store_int_result(ops[2], a + b, carry=carry)
    return cond


@instruction("SUB", "Subtract", "Math", ABC, ABC_LABELS, output=True)
def sub(ctx, ops, cond):
    if cond:
        a, b = ctx.value(ops[0]), ctx.value(ops[1])
        borrow = not _any_float(ctx, *ops[:2]) and (int(a) & 0xFFFF) < (int(b) & 0xFFFF)
        ctx.store_int_result(ops[2], a - b, carry=borrow)
    return cond


@instruction("MUL", "Multiply", "Math", ABC, ABC_LABELS, output=True)
def mul(ctx, ops, cond):
    if cond:
        a, b = ctx.value(ops[0]), ctx.value(ops[1])
        r = a * b
        if not _any_float(ctx, *ops[:2]):
            r32 = int(r) & 0xFFFFFFFF
            ctx.store(MATH_LOW, r32 & 0xFFFF)
            ctx.store(MATH_HIGH, r32 >> 16)
        ctx.store_int_result(ops[2], r)
    return cond


@instruction("DIV", "Divide", "Math", ABC, ABC_LABELS, output=True)
def div(ctx, ops, cond):
    if not cond:
        return cond
    a, b = ctx.value(ops[0]), ctx.value(ops[1])
    if b == 0:
        if ctx.dt.addr(ops[2]).type != "F":
            ctx.store(ops[2], 32767)
        ctx.flags(overflow=True, value=1)
        return cond
    if _any_float(ctx, *ops[:2]) or ctx.dt.addr(ops[2]).type == "F":
        ctx.store_int_result(ops[2], a / b)
        return cond
    a, b = int(a), int(b)
    q = abs(a) // abs(b) * (1 if (a >= 0) == (b >= 0) else -1)   # truncated toward zero
    rem = a - q * b
    ctx.store(MATH_HIGH, q)
    ctx.store(MATH_LOW, rem)
    rounded = q + (1 if q >= 0 else -1) * (2 * abs(rem) >= abs(b))   # remainder ≥ 0.5 rounds up
    ctx.store_int_result(ops[2], rounded)
    return cond


@instruction("SQR", "Square root", "Math", ["value", "word"], ["Source", "Dest"], output=True)
def sqr(ctx, ops, cond):
    if cond:
        v = ctx.value(ops[0])
        ctx.store_int_result(ops[1], _m.sqrt(abs(v)) if ctx.dt.addr(ops[1]).type == "F"
                             else round_half_away(_m.sqrt(abs(v))))
        ctx.set_bit(CARRY, v < 0)   # manual: negative source uses its absolute value
    return cond


@instruction("NEG", "Negate", "Math", ["value", "word"], ["Source", "Dest"], output=True)
def neg(ctx, ops, cond):
    if cond:
        ctx.store_int_result(ops[1], -ctx.value(ops[0]))
    return cond


@instruction("MOV", "Move", "Move/Logical", ["value", "word"], ["Source", "Dest"], output=True)
def mov(ctx, ops, cond):
    if cond:
        v = ctx.value(ops[0])
        ctx.store_int_result(ops[1], v)
        ctx.set_bit(CARRY, False)
    return cond


@instruction("MVM", "Masked move", "Move/Logical", ["value", "value", "word"],
             ["Source", "Mask", "Dest"], output=True)
def mvm(ctx, ops, cond):
    if cond:
        src, mask, dst = ctx.word(ops[0]), ctx.word(ops[1]), ctx.word(ops[2])
        r = (dst & ~mask) | (src & mask)
        ctx.store(ops[2], r)
        ctx.flags(value=ctx.word(ops[2]))
    return cond


@instruction("CLR", "Clear", "Move/Logical", ["word"], ["Dest"], output=True)
def clr(ctx, ops, cond):
    if cond:
        ctx.store(ops[0], 0)
        ctx.flags(value=0)
    return cond


def _logic(mnemonic, title, op):
    @instruction(mnemonic, title, "Move/Logical", ABC, ABC_LABELS, output=True)
    def run(ctx, ops, cond):
        if cond:
            r = op(ctx.word(ops[0]), ctx.word(ops[1]))
            ctx.store(ops[2], r)
            ctx.flags(value=ctx.word(ops[2]))
        return cond
    return run


_logic("AND", "Bitwise AND", lambda a, b: a & b)
_logic("OR", "Bitwise OR", lambda a, b: a | b)
_logic("XOR", "Bitwise exclusive OR", lambda a, b: a ^ b)


@instruction("NOT", "Bitwise NOT", "Move/Logical", ["value", "word"], ["Source", "Dest"], output=True)
def not_(ctx, ops, cond):
    if cond:
        ctx.store(ops[1], ~ctx.word(ops[0]))
        ctx.flags(value=ctx.word(ops[1]))
    return cond


@instruction("TOD", "Convert to BCD", "Math", ["value", "word"], ["Source", "Dest"], output=True)
def tod(ctx, ops, cond):
    if cond:
        v = ctx.word(ops[0])
        if v < 0 or v > 9999:
            ctx.set_bit(OVERFLOW, True)
            ctx.set_bit(OVERFLOW_TRAP, True)
            return cond
        bcd = int(str(v), 16)
        ctx.store(ops[1], bcd)
        ctx.store(MATH_LOW, bcd)
        ctx.flags(value=v)
    return cond


@instruction("FRD", "Convert from BCD", "Math", ["value", "word"], ["Source", "Dest"], output=True)
def frd(ctx, ops, cond):
    if cond:
        raw = ctx.word(ops[0]) & 0xFFFF
        digits = f"{raw:04X}"
        if not digits.isdigit():
            ctx.set_bit(OVERFLOW, True)
            ctx.set_bit(OVERFLOW_TRAP, True)
            return cond
        v = int(digits)
        ctx.store(ops[1], v)
        ctx.flags(value=v)
    return cond
