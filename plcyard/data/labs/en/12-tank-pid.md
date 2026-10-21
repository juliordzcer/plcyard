---
title: Tank level with a PID loop
simulation: tank
controller: logix
level: 4
---
# 12. Tank level with a PID loop (Logix)

**Goal:** hold the level exactly at the setpoint by moving a proportional valve, and tune the PID.

This exercise uses the **Logix** controller (tags). "New program for this exercise" starts one.

## Inputs and outputs (Tank simulation)

| Tag | Device |
| --- | --- |
| Local:7:I.Ch0Data | Level, 0-10 V = 0-100 % (REAL) |
| Local:7:I.Ch1Data | Setpoint knob, 0-10 V = 0-100 % (REAL) |
| Local:8:O.Ch0Data | Inlet valve, 0-10 V = closed to fully open (REAL) |

## Requirements

1. The level follows the setpoint knob: within ±2 % of it no later than 60 s after a change.
2. Overshoot no more than 5 %.
3. When the outlet opens wider (a disturbance), the level is back within ±2 % in 60 s.
4. The tank never overflows.

## How to

1. Add tags: `LevelPID` of type PID, and REAL tags for the level and the valve output.
2. Convert volts to percent: `MUL Local:7:I.Ch0Data 10.0 Level` (and the knob into `LevelPID.SP`).
3. `PID LevelPID Level ValveOut`, then `DIV ValveOut 10.0 Local:8:O.Ch0Data`.
4. Tune: set `LevelPID.KP` and `LevelPID.TI` (seconds) with a MOV on the first scan
   (`XIC S:FS`). Start with KP 1 and TI 0 (proportional only): the level settles below the
   setpoint. Then add integral action (TI 30, then 15) and watch the trend.
