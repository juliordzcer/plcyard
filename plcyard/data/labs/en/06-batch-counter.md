---
title: Batch counter with display
simulation: io
level: 2
symbols:
- I:1/0 Part sensor (NO, pushbutton)
- I:1/1 Reset batch (NO, pushbutton)
- O:2/0 Batch complete
---
# 6. Batch counter with display

**Goal:** count parts with CTU, signal a complete batch and show the count on the BCD display.

## Requirements

1. Each pulse on I:1/0 counts one part (one pulse = one part, however long it lasts).
2. At 5 parts, O:2/0 (batch complete) turns on.
3. I:1/1 resets the count and turns O:2/0 off.
4. Display O:6 always shows the number of parts.

## Hints

- The display expects BCD: convert the accumulator with TOD.
