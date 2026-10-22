---
title: Tank level with a PID loop
simulation: tank
level: 4
---
# 12. Tank level with a PID loop

**Goal:** hold the level exactly at the setpoint by moving a proportional valve, and tune the PID.

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

1. Add tags (Ctrl+T): `LevelPID` of type PID, and REAL tags `Level` and `ValveOut`.
2. Raw counts to percent: `DIV %IW64 276.48 Level` (27648 / 100), and the knob into `LevelPID.SP`.
3. `PID LevelPID Level ValveOut` (PID, process variable, control variable; the setpoint, tieback,
   master loop and inhold operands are optional), then `MUL ValveOut 276.48 %QW64`.
4. Tune: set `LevelPID.KP` and `LevelPID.TI` (seconds) with a `MOV` on the first scan
   (`XIC FirstScan`), or as start values: open `LevelPID` in the tag list. Start with KP 1 and TI 0
   (proportional only): the level settles below the setpoint. Then add integral action (TI 30,
   then 15) and watch the trend.

## Think about it

Why does a proportional-only controller leave an offset here? What does the integral term add?
