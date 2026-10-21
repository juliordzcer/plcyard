---
title: Sorting by range with comparators
simulation: io
level: 2
symbols:
- O:2/0 Low
- O:2/1 Normal
- O:2/2 High
---
# 7. Sorting by range with comparators

**Goal:** read a number from the thumbwheels (I:5, BCD) and classify it.

## Requirements

1. Convert the value of I:5 to binary in N7:0.
2. O:2/0 (Low) when the value is less than 100.
3. O:2/1 (Normal) when it is between 100 and 500, inclusive.
4. O:2/2 (High) when it is greater than 500.
5. Only one of the three outputs may be on.

## Hints

- FRD converts from BCD to binary.
- LIM handles "between" in a single instruction.
