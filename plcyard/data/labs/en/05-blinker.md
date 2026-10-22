---
title: Blinking light with timers
simulation: io
level: 2
symbols:
- %I0.0 Enable
- %Q0.0 Blinking light
---
# 5. Blinking light with timers

**Goal:** chain two TON timers to make a periodic signal.

## Requirements

1. With %I0.0 closed, %Q0.0 is on for 1 s and off for 1 s, repeating.
2. Opening %I0.0 turns the light off and restarts the cycle.

## Hints

- Declare two TIMER tags (Ctrl+T opens the tag list). Presets are in milliseconds: 1000 is
  1 s, and T#1s works too.
- The DN bit of the second timer can reset the first one.
- Open a timer in the tag list to watch its EN, TT and DN bits at a low speed.
