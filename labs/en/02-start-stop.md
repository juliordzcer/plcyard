---
title: Start/stop with seal-in
simulation: io
level: 1
symbols:
- I:1/0 Start (NO)
- I:1/1 Stop (NC)
- O:2/0 Motor
- O:2/1 Running light
- O:2/2 Stopped light
---
# 2. Start/stop with seal-in

**Goal:** keep a motor running after the start button is released.

## Inputs and outputs

| Address | Device | Type |
| --- | --- | --- |
| I:1/0 | Start | normally open |
| I:1/1 | Stop | **normally closed** |
| O:2/0 | Motor | |
| O:2/1 | Running light | |
| O:2/2 | Stopped light | |

## Requirements

1. Closing and opening Start leaves the motor running.
2. Opening Stop (pressing it) turns the motor off, even if Start is still closed.
3. If the Stop wire breaks, the motor must also turn off.
4. The running light follows the motor; the stopped light is on while the motor is off.

## Hints

- Stop is NC: when not pressed it delivers a 1. Which instruction examines it?
- The motor's own contact, in parallel with Start, is the seal-in.

## Think about it

What happens to the motor if you switch the PLC to PGM and back to RUN? Why?
