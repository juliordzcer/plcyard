"""Bit instructions (manual chapter 2)."""

from . import instruction


@instruction("XIC", "Examine if closed", "Bit", ["bit"], ["Bit"])
def xic(ctx, ops, cond):
    return cond and ctx.bit(ops[0])


@instruction("XIO", "Examine if open", "Bit", ["bit"], ["Bit"])
def xio(ctx, ops, cond):
    return cond and not ctx.bit(ops[0])


@instruction("OTE", "Output energize", "Bit", ["bit"], ["Bit"], output=True)
def ote(ctx, ops, cond):
    ctx.set_bit(ops[0], cond)
    return cond


@instruction("OTL", "Output latch", "Bit", ["bit"], ["Bit"], output=True)
def otl(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], True)
    return cond


@instruction("OTU", "Output unlatch", "Bit", ["bit"], ["Bit"], output=True)
def otu(ctx, ops, cond):
    if cond:
        ctx.set_bit(ops[0], False)
    return cond


@instruction("OSR", "One-shot rising", "Bit", ["bit"], ["Storage bit"])
def osr(ctx, ops, cond):
    # The storage bit remembers the rung condition before the OSR; output is the rising edge.
    prev = ctx.bit(ops[0])
    ctx.set_bit(ops[0], cond)
    return cond and not prev


@instruction("NOP", "No operation", "Bit", [], [])
def nop(ctx, ops, cond):
    return cond
