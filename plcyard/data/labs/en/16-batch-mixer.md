---
title: Batch mixer sequence
simulation: mixer
level: 5
symbols:
- %I0.0 Start (PB)
- %I0.1 Stop (NC, PB)
---
# 16. Batch mixer sequence

**Goal:** a sequence with steps: fill two ingredients, mix and heat, drain, repeat.

## Inputs and outputs (Batch mixer simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Start (pushbutton) |
| %I0.1 | Stop (pushbutton, **normally closed**) |
| %I0.2, %I0.3, %I0.4 | Low (5 %), middle (50 %) and high (90 %) level switches |
| %IW64 | Temperature, 0-27648 = 0-100 °C |
| %Q0.0, %Q0.1 | Valve A, valve B |
| %Q0.2 | Mixer motor |
| %Q0.3 | Heater |
| %Q0.4 | Drain valve |
| %Q0.5 | Batch done light |

## Requirements

1. Start makes batches one after the other: at least 2 in 2 minutes.
2. Every batch is good: A up to the middle switch, B up to the high switch, mixed at least 5 s,
   drained at 50-60 °C.
3. The batch done light comes on after each batch.
4. No overflow, no heating without liquid, no mixing an empty tank.
5. Stop turns every output off, and nothing restarts until Start.

## Hints

- Keep the step in an integer tag (0 idle, 1 fill A, 2 fill B, 3 mix and heat, 4 drain…). Each
  output is "step = n"; each transition moves to the next step when its condition is true.
- Drain until the tank is empty (the low switch clears, then a little longer).
- Heat with hysteresis, for example on below 54 °C and off above 56 °C.
