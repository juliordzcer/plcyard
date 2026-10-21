---
title: Blinking light with timers
simulation: io
level: 2
symbols:
- I:1/0 Enable
- O:2/0 Blinking light
---
# 5. Blinking light with timers

**Goal:** chain two TON timers to make a periodic signal.

## Requirements

1. With I:1/0 closed, O:2/0 is on for 1 s and off for 1 s, repeating.
2. Opening I:1/0 turns the light off and restarts the cycle.

## Hints

- The time base is 0.1 s: a preset of 10 is 1 s.
- The DN bit of the second timer can reset the first one.
- Watch the EN, TT and DN bits in the data table (Ctrl+T) at a low speed.
