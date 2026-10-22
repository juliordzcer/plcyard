---
title: Reversing motor with interlock
simulation: io
level: 2
symbols:
- %I0.0 Forward (NO)
- %I0.1 Reverse (NO)
- %I0.2 Stop (NC)
- %Q0.0 Forward contactor
- %Q0.1 Reverse contactor
---
# 3. Reversing motor with interlock

**Goal:** run a motor in two directions without both contactors ever being on together.

## Requirements

1. Forward (%I0.0) starts and seals in %Q0.0; Reverse (%I0.1) starts and seals in %Q0.1.
2. Stop (%I0.2, NC) stops either one.
3. %Q0.0 and %Q0.1 must **never** be on at the same time.
4. To change direction you must stop first: pressing Reverse while running forward does nothing.

## Hints

- Each contactor's rung includes an `XIO` contact of the other one (interlock).
