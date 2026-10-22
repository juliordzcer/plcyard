---
title: Tank level with PID_Compact
simulation: tank
controller: s7
level: 4
---
# 13. Tank level with PID_Compact (S7-1200/1500)

**Goal:** the same loop as exercise 12, on a Siemens controller: hold the level at the setpoint with
the `PID_Compact` box and raw analog values.

This exercise uses the **S7** controller. "New program for this exercise" starts one.

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

1. Add tags: `LevelPID` of type `PID_Compact`, and `Real` tags `Level`, `Setpoint`, `Valve`.
2. Raw to percent: `DIV %IW64 276.48 Level` (27648 / 100) and the same for the knob.
3. `PID_Compact LevelPID Setpoint Level Valve`, then `MUL Valve 276.48 %QW64`.
4. Tune `LevelPID.Gain` and `LevelPID.Ti` (seconds): give them start values in the tag list
   (open `LevelPID` with the arrow) or MOVE them on `FirstScan`. Proportional only leaves an
   offset; integral action removes it.
5. Same in SCL: a new program in structured text, `"LevelPID"(Setpoint := ..., Input := ..., Output => ...);`.
