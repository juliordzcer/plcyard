---
title: Tank level PID in structured text
simulation: tank
level: 4
---
# 13. Tank level PID in structured text

**Goal:** the same loop as exercise 12, written in structured text.

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

1. File → New in structured text, then add the tags `LevelPID` (PID) and `Level`, `Valve` (REAL).
2. Give `LevelPID` start values in the tag list: KP 4, TI 15.
3. Call the block on its tag and scale on the way in and out:

```
Level := INT_TO_REAL(%IW64) / 276.48;
LevelPID.PID(PV := Level, SP := INT_TO_REAL(%IW66) / 276.48, CV => Valve);
%QW64 := REAL_TO_INT(Valve * 276.48);
```
