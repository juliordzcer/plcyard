"""Subroutines (manual chapter 8)."""

from . import ReturnFromSubroutine, instruction


@instruction("JSR", "Jump to subroutine", "Program Control", ["sub"], ["SBR file"], output=True)
def jsr(ctx, ops, cond):
    if cond:
        ctx.call(int(ops[0].split(":")[1]))
    return cond


@instruction("SBR", "Subroutine", "Program Control", ["sub"], ["SBR file"])
def sbr(ctx, ops, cond):
    return cond


@instruction("RET", "Return", "Program Control", [], [], output=True)
def ret(ctx, ops, cond):
    if cond:
        raise ReturnFromSubroutine()
    return cond
