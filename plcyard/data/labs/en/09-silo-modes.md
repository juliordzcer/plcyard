---
title: Operating modes with a selector
simulation: silo
level: 3
---
# 9. Operating modes with a selector

**Goal:** one process, three modes chosen with the A/B/C selector (%I0.5, %I0.6, %I0.7).

## Requirements

1. **A — continuous:** as in exercise 8.
2. **B — manual restart:** the full box stays under the hopper until the operator presses Start
   once (a tap, not held); then it moves on and the next box stops.
3. **C — no filling:** the conveyor runs continuously and boxes pass empty.
4. In all three modes Start/Stop and the Run light work the same, and no product is ever spilled.

## Hints

- In mode B you must remember the Start tap until the box leaves the sensor (`OTL`/`OTU` on a BOOL tag).
