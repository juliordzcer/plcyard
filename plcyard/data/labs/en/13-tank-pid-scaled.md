---
title: Tank level PID, scaled inside the block
simulation: tank
level: 4
---
# 13. Tank level PID, scaled inside the block

**Goal:** the loop of exercise 12, but the PID converts the raw analog values itself.

## Inputs and outputs (Tank simulation)

| Address | Device |
| --- | --- |
| %IW64 | Level, 0-27648 = 0-100 % |
| %IW66 | Setpoint knob, 0-27648 = 0-100 % |
| %QW64 | Inlet valve, 0-27648 = closed to fully open |

## Requirements

1. The level follows the setpoint knob: within ±2 % of it no later than 60 s after a change.
2. Overshoot no more than 5 %.
3. When the outlet opens wider (a disturbance), the level is back within ±2 % in 60 s.
4. The tank never overflows.

## How to

1. Add the tags `LevelPID` (PID) and `Setpoint` (REAL).
2. PID Setup → Scaling: PV unscaled 0 to 27648, engineering units 0 to 100, CV 0 to 27648. Tuning:
   KP 4, KI 0.27.
3. The PV is the raw input and the CV the raw output: `PID LevelPID %IW64 %QW64 Setpoint`.
4. The knob into percent for the setpoint: `SCP %IW66 0 27648 0 100 Setpoint`.

Try it in all three languages: in structured text `LevelPID.PID(PV := %IW64, SP := Setpoint,
CV => %QW64);`, in function block diagram a SCALE block feeding the PID block's SP pin. "Compare
languages" shows the reference solution in each.
