---
title: Pump station with duty sharing
simulation: pumps
level: 4
symbols:
- %I0.0 Reset alarm (PB)
- %I0.1 Stop (NC, PB)
---
# 21. Pump station with duty sharing

**Goal:** two pumps empty a sump. They take turns so they wear evenly, the second one helps when
the level keeps rising, and a failed pump is replaced by the other one.

## Inputs and outputs (Pump station simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Reset alarm (pushbutton) |
| %I0.1 | Stop (pushbutton, **normally closed**) |
| %I0.2 | Low level (15 % or more) |
| %I0.3 | Start level (50 % or more) |
| %I0.4 | High level (75 % or more) |
| %I0.5 | Overflow alarm level (95 % or more) |
| %I0.6, %I0.7 | Pump 1 fault, pump 2 fault (TRUE when the pump's protection tripped) |
| %IW64 | Level, 0-27648 = 0-100 % |
| %Q0.0, %Q0.1 | Pump 1, pump 2 |
| %Q0.2 | Alarm lamp |

Each pump takes out 3 % of the sump per second. The inflow slider goes up to 5 % per second, more
than one pump can handle.

## Requirements

1. The pumps keep the level between low and high: a pump starts at the start level and stops at
   the low level.
2. They take turns: each new emptying cycle uses the other pump.
3. Both pumps run when the level keeps rising up to the high level.
4. A failed pump is switched off and the other one takes over.
5. The alarm lamp lights for a pump fault or the overflow level.
6. Reset clears the alarm only once the fault is gone.
7. No overflow and no pump running dry.
8. Stop (held) turns both pumps off.

## Hints

- Remember which pump leads in an integer tag (1 or 2) and switch it at the start of each cycle:
  `Lead := 3 - Lead`.
- A cycle starts when no pump runs and the start level is reached; it ends at the low level.
- At the high level, run every pump that is not faulty.
- Latch the alarm; unlatch it with Reset only when no fault and no overflow level are present.
