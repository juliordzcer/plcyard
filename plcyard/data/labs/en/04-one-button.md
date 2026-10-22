---
title: On and off with one button
simulation: io
level: 2
symbols:
- %I0.0 Button (NO, pushbutton)
- %Q0.0 Lamp
---
# 4. On and off with one button

**Goal:** use a one shot (`ONS`) so that every press changes the state of a lamp.

## Requirements

1. Every press of %I0.0 changes %Q0.0 (on ↔ off).
2. Holding the button down must **not** make the lamp flicker.

## Hints

- `ONS` gives a one-scan pulse when its rung goes from false to true.
- With that pulse and the lamp's current state you can build a two-branch flip-flop.
