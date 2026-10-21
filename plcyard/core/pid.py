"""PID shared by the controller profiles (Logix PID, S7 PID_Compact).

Ideal (dependent) form, as PID_Compact and the Logix dependent equation use:
    CV = Kc * (e + 1/Ti * ∫e dt - Td * dPV/dt)
with e = SP - PV, times in seconds, derivative on the process variable (no kick on setpoint
changes) and anti-windup by conditional integration: the integral stops growing while the output
is held at a limit in the same direction. Manual mode copies the manual value to CV and loads the
integral so the switch back to automatic is bumpless.
"""

from __future__ import annotations


def step(state: dict, sp: float, pv: float, dt_s: float, *, kc: float, ti: float, td: float,
         out_min: float = 0.0, out_max: float = 100.0, manual: bool = False, manual_value: float = 0.0,
         reverse: bool = False) -> float:
    """Advance one evaluation. `state` keeps "I" (integral term) and "PV1" (last PV) between calls.
    `reverse` acts for processes where more output lowers PV (cooling): e = PV - SP."""
    e = (pv - sp) if reverse else (sp - pv)
    last_pv = state.get("PV1", pv)
    state["PV1"] = pv
    if manual:
        cv = min(max(manual_value, out_min), out_max)
        p = kc * e
        state["I"] = cv - p                 # bumpless return to automatic
        return cv
    if dt_s <= 0:
        return min(max(state.get("CV", out_min), out_min), out_max)
    p = kc * e
    d = -kc * td * ((pv - last_pv) * (-1 if reverse else 1)) / dt_s if td > 0 else 0.0
    i = state.get("I", 0.0)
    if ti > 0:
        candidate = i + kc * e * dt_s / ti
        unclamped = p + candidate + d
        winding_up = (unclamped > out_max and e > 0) or (unclamped < out_min and e < 0)
        if not winding_up:
            i = candidate
    else:
        i = 0.0
    state["I"] = i
    cv = min(max(p + i + d, out_min), out_max)
    state["CV"] = cv
    return cv
