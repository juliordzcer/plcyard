"""PID algorithm of the PID instruction (positional form, gains on the error in % of span).

Independent gains:  CV = KP·E + KI·∫E dt + KD·dE/dt + BIAS            (KI in 1/s, KD in s)
Dependent gains:    CV = KC·(E + 1/(60·TI)·∫E dt + 60·TD·dE/dt) + BIAS (TI min/repeat, TD min)
The derivative acts on the error or, by default, on the process variable (no kick when the setpoint
moves). The integral stops growing while the output sits at a limit and pushes further (anti-reset
windup). Manual mode copies the manual output and back-calculates the integral (or the bias when
there is no integral action) so the return to automatic is bumpless.
"""

from __future__ import annotations


def dependent_to_independent(kc: float, ti_min: float, td_min: float) -> tuple[float, float, float]:
    """KC, TI (min/repeat), TD (min) → KP, KI (1/s), KD (s)."""
    return kc, (kc / (60.0 * ti_min) if ti_min > 0 else 0.0), kc * td_min * 60.0


def step(state: dict, sp: float, pv: float, dt_s: float, *, kp: float, ki: float, kd: float,
         bias: float = 0.0, out_min: float = 0.0, out_max: float = 100.0, manual: bool = False,
         manual_value: float = 0.0, reverse: bool = False, d_on_error: bool = False,
         back_calc_bias: bool = True) -> float:
    """Advance one evaluation; returns the output in %. `state` keeps "I" (integral term), "E1" and
    "PV1" (last error and PV) and "BIAS" (back-calculated bias). `reverse`: E = PV - SP (more output
    lowers PV, e.g. cooling or a drain valve)."""
    e = (pv - sp) if reverse else (sp - pv)
    last_e, last_pv = state.get("E1", e), state.get("PV1", pv)
    state["E1"], state["PV1"] = e, pv
    b = state.get("BIAS", bias) if ki == 0 else bias        # bias kept from manual when there is no I
    if manual:
        cv = min(max(manual_value, out_min), out_max)
        if ki > 0:
            state["I"] = cv - kp * e - b
        elif back_calc_bias:
            state["BIAS"] = cv - kp * e
        state["CV"] = cv
        return cv
    if dt_s <= 0:
        return min(max(state.get("CV", out_min), out_min), out_max)
    p = kp * e
    if d_on_error:
        d = kd * (e - last_e) / dt_s
    else:
        d = -kd * (pv - last_pv) * (-1 if reverse else 1) / dt_s
    i = state.get("I", 0.0)
    if ki > 0:
        candidate = i + ki * e * dt_s
        unclamped = p + candidate + d + b
        winding_up = (unclamped > out_max and e > 0) or (unclamped < out_min and e < 0)
        if not winding_up:
            i = candidate
    else:
        i = 0.0
    state["I"] = i
    cv = min(max(p + i + d + b, out_min), out_max)
    state["CV"] = cv
    return cv
