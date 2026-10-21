---
title: Reversing motor with interlock
simulation: io
level: 2
symbols:
- I:1/0 Forward (NO)
- I:1/1 Reverse (NO)
- I:1/2 Stop (NC)
- O:2/0 Forward contactor
- O:2/1 Reverse contactor
---
# 3. Reversing motor with interlock

**Goal:** run a motor in two directions without both contactors ever being on together.

## Requirements

1. Forward (I:1/0) starts and seals in O:2/0; Reverse (I:1/1) starts and seals in O:2/1.
2. Stop (I:1/2, NC) stops either one.
3. O:2/0 and O:2/1 must **never** be on at the same time.
4. To change direction you must stop first: pressing Reverse while running forward does nothing.

## Hints

- Each contactor's rung includes an XIO contact of the other one (interlock).
