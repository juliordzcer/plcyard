---
title: Tank level with on/off control
simulation: tank
level: 3
symbols:
- I:1/1 Stop (NC)
---
# 11. Tank level with on/off control

**Goal:** keep a tank between two levels with a pump, using the analog level signal. This is how a
thermostat works: on below one value, off above another.

## Inputs and outputs (Tank simulation)

| Address | Device |
| --- | --- |
| I:1/0 | Start (NO pushbutton) |
| I:1/1 | Stop (NC pushbutton) |
| I:1/2 | High level switch (level ≥ 90 %) |
| I:7 | Level, analog: 0-16383 = 0-100 % |
| O:2/0 | Pump |
| O:2/1 | Run light |
| O:2/2 | High alarm light |

## Requirements

1. Start and Stop control the system; the Run light shows it is running.
2. While running, the pump starts when the level falls below 40 % and stops above 60 %.
3. The level then stays between about 35 % and 65 %, whatever the outlet opening.
4. Stop turns the pump off.
5. The High alarm light is on whenever the high level switch is on, running or not.

## Hints

- 40 % of 16383 is 6553; 60 % is 9830.
- Compare with LES and GRT, and remember the pump state with OTL/OTU (or a seal-in): between
  40 % and 60 % neither condition is true, and the pump must keep doing what it was doing. That
  gap is the *hysteresis*; without it the pump would chatter on and off.
