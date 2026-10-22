---
title: Two tanks in series
simulation: two_tanks
level: 5
---
# 14. Two tanks in series

**Goal:** hold the level of the lower tank 2 at the setpoint. You can only open the inlet of the
upper tank 1 and the valve between the tanks: a slow process with two lags.

## Inputs and outputs (Two tanks simulation)

| Address | Device |
| --- | --- |
| %IW64 | Tank 1 level, 0-27648 = 0-100 % |
| %IW66 | Tank 2 level, 0-27648 = 0-100 % |
| %IW68 | Setpoint knob, 0-27648 = 0-100 % |
| %QW64 | Inlet valve of tank 1, 0-27648 = 0-100 % |
| %QW66 | Transfer valve between the tanks, 0-27648 = 0-100 % |
| %I0.2, %I0.3, %I0.4 | Tank 1 high, tank 2 high, tank 2 low switches |

## Requirements

1. Tank 2 holds the setpoint (±3 %) within 3 minutes.
2. It is back on the setpoint after the outlet of tank 2 opens wider.
3. It follows a new setpoint.
4. Neither tank overflows.

## Hints

- A single PID from tank 2 to the inlet valve works, but slowly. A **cascade** is better: the outer
  PID on tank 2 gives the setpoint of an inner PID on tank 1 (the `PID` instruction's master loop
  operand, or wire one PID's CV into the other's SP in FBD).
- Set the transfer valve to a fixed opening, for example 60 % (`MOV 16589 %QW66`).
- Let each PID scale the raw values: PID Setup → Scaling, unscaled 0-27648.
