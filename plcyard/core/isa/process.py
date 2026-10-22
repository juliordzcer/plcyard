"""PID (manual chapter 9): a 23-word control block in an integer file, PV and CV 0-16383.

Control block words used here (offset from the first word):
  0  flags: /1 AM manual, /2 CM reverse (E = PV - SP), /3 OL output limits, /4 RG gain range ×0.01,
     /13 DN computed this scan, /15 EN rung true
  1  error code (11h: loop update time not set)
  2  SP setpoint (0-16383, or in Smin..Smax when scaling is set)
  3  Kc gain ×0.1 (×0.01 with RG)       4  Ti reset, minutes/repeat ×0.1 (×0.01 with RG); 0 = none
  5  Td rate, minutes ×0.01             7  Smax   8  Smin (setpoint scaling, both 0 = none)
  11 CV max %   12 CV min % (with OL)   13 loop update, 0.01 s units
  14 PV scaled  15 error scaled         16 output CV % (written by you in manual)
"""

from . import Address, PlcFault, instruction  # noqa: F401
from .. import pid

FULL = 16383
AM, CM, OL, RG, DN, EN = 1, 2, 3, 4, 13, 15
UPDATE_NOT_SET = 0x11


def _words(ctx, block: str):
    a = ctx.dt.addr(block)
    base = f"{a.type}{a.file}:"
    return lambda k: f"{base}{a.element + k}"


def _prescan(ctx, ops):
    ctx.timer_marks.pop("pid:" + ops[0], None)
    ctx.pid_state.pop(ops[0], None)


@instruction("PID", "Proportional integral derivative", "Process", ["word", "word", "word"],
             ["Control block", "Process variable", "Control variable"], output=True, on_prescan=_prescan)
def pid_(ctx, ops, cond):
    w = _words(ctx, ops[0])
    flag = lambda b: ctx.bit(f"{w(0)}/{b}")
    ctx.set_bit(f"{w(0)}/{EN}", cond)
    ctx.set_bit(f"{w(0)}/{DN}", False)
    key = "pid:" + ops[0]
    if not cond:
        ctx.timer_marks.pop(key, None)
        return cond
    update_ms = ctx.word(w(13)) * 10
    if update_ms <= 0:
        ctx.store(w(1), UPDATE_NOT_SET)
        return cond
    last = ctx.timer_marks.get(key)
    if last is not None and ctx.now_ms - last < update_ms:
        return cond
    ctx.timer_marks[key] = ctx.now_ms
    dt = 0.0 if last is None else (ctx.now_ms - last) / 1000.0
    ctx.store(w(1), 0)
    smax, smin = ctx.word(w(7)), ctx.word(w(8))
    scaled = smax != smin
    pv_raw = min(max(ctx.word(ops[1]), 0), FULL)
    sp = ctx.word(w(2))
    if scaled:
        pv_eng = smin + pv_raw * (smax - smin) / FULL
        sp_pct, pv_pct = (sp - smin) * 100.0 / (smax - smin), pv_raw * 100.0 / FULL
    else:
        pv_eng = pv_raw
        sp_pct, pv_pct = sp * 100.0 / FULL, pv_raw * 100.0 / FULL
    range_ = 0.01 if flag(RG) else 0.1
    lo, hi = (ctx.word(w(12)), ctx.word(w(11))) if flag(OL) else (0, 100)
    state = ctx.pid_state.setdefault(ops[0], {"CV": float(ctx.word(w(16))), "I": float(ctx.word(w(16)))})
    cv = pid.step(state, sp_pct, pv_pct, dt, kc=ctx.word(w(3)) * range_, ti=ctx.word(w(4)) * range_ * 60.0,
                  td=ctx.word(w(5)) * 0.01 * 60.0, out_min=lo, out_max=hi, manual=flag(AM),
                  manual_value=float(ctx.word(w(16))), reverse=flag(CM))
    ctx.store(w(14), round(pv_eng))
    ctx.store(w(15), round(sp - pv_eng if not flag(CM) else pv_eng - sp))
    ctx.store(w(16), round(cv))
    ctx.store(ops[2], round(cv * FULL / 100.0))
    ctx.set_bit(f"{w(0)}/{DN}", True)
    return cond
