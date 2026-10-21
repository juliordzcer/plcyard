---
title: On and off with one button
simulation: io
level: 2
symbols:
- I:1/0 Button (NO, pushbutton)
- O:2/0 Lamp
---
# 4. On and off with one button

**Goal:** use an edge (OSR) so that every press changes the state of a lamp.

## Requirements

1. Every press of I:1/0 changes O:2/0 (on ↔ off).
2. Holding the button down must **not** make the lamp flicker.

## Hints

- OSR gives a one-scan pulse when its rung goes from false to true.
- With that pulse and the lamp's current state you can build a two-branch flip-flop.
