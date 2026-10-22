---
title: Sorting by range with comparators
simulation: io
level: 2
symbols:
- %Q0.0 Low
- %Q0.1 Normal
- %Q0.2 High
---
# 7. Sorting by range with comparators

**Goal:** read a number from the thumbwheels (%IW4, BCD) and classify it.

## Requirements

1. Convert the value of %IW4 to binary in an INT tag (for example `Value`).
2. %Q0.0 (Low) when the value is less than 100.
3. %Q0.1 (Normal) when it is between 100 and 500, inclusive.
4. %Q0.2 (High) when it is greater than 500.
5. Only one of the three outputs may be on.

## Hints

- `FRD` converts from BCD to binary.
- `LIM` handles "between" in a single instruction.
