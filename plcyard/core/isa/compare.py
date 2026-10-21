"""Comparison instructions (manual chapter 3). Inputs: they only gate the rung."""

from . import instruction


def _cmp(mnemonic, title, test):
    @instruction(mnemonic, title, "Compare", ["value", "value"], ["Source A", "Source B"])
    def run(ctx, ops, cond):
        return cond and test(ctx.value(ops[0]), ctx.value(ops[1]))
    return run


_cmp("EQU", "Equal", lambda a, b: a == b)
_cmp("NEQ", "Not equal", lambda a, b: a != b)
_cmp("LES", "Less than", lambda a, b: a < b)
_cmp("LEQ", "Less than or equal", lambda a, b: a <= b)
_cmp("GRT", "Greater than", lambda a, b: a > b)
_cmp("GEQ", "Greater than or equal", lambda a, b: a >= b)


@instruction("LIM", "Limit test", "Compare", ["value", "value", "value"], ["Low limit", "Test", "High limit"])
def lim(ctx, ops, cond):
    low, test, high = (ctx.value(o) for o in ops)
    if low <= high:
        inside = low <= test <= high
    else:   # manual: low > high makes the instruction true outside the band
        inside = test >= low or test <= high
    return cond and inside


@instruction("MEQ", "Masked equal", "Compare", ["value", "value", "value"], ["Source", "Mask", "Compare"])
def meq(ctx, ops, cond):
    src, mask, ref = (ctx.word(o) & 0xFFFF for o in ops)
    return cond and (src & mask) == (ref & mask)
