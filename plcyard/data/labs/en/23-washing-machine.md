---
title: Washing machine program
simulation: washer
level: 5
symbols:
- %I0.0 Start (PB)
- %I0.1 Stop (NC, PB)
---
# 23. Washing machine program

**Goal:** a timed sequence with safety interlocks: lock the door, fill, wash turning both ways,
drain, spin, wait for the drum to stop, unlock.

## Inputs and outputs (Washing machine simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Start (pushbutton) |
| %I0.1 | Stop (pushbutton, **normally closed**) |
| %I0.2 | Door closed |
| %I0.3 | Door locked |
| %I0.4 | Water present (10 % or more) |
| %I0.5 | Water full (80 % or more) |
| %I0.6 | Drum stopped |
| %Q0.0 | Door lock |
| %Q0.1 | Fill valve |
| %Q0.2, %Q0.3 | Wash turning left, wash turning right |
| %Q0.4 | Spin |
| %Q0.5 | Drain pump |
| %Q0.6 | Done lamp |

The drum speeds up and slows down at 400 rpm per second: after a spin it takes a few seconds to
stop.

## Requirements

1. Start with the door closed runs a whole wash within 2 minutes.
2. The clothes turn in water at least 10 s each way.
3. The water is drained before a spin of at least 5 s.
4. The done lamp lights at the end.
5. Start does nothing with the door open.
6. Stop during a wash stops the drum and unlocks the door once the drum has stopped.
7. The door never unlocks while the drum turns, and the machine never floods.

## Hints

- One step number: 0 idle, 1 lock, 2 fill, 3 wash, 4 drain, 5 spin, 6 wait for the drum, 7 done.
- In the wash step a timer of a few seconds that restarts itself flips the direction.
- Drain until the "water present" switch clears, then a little longer.
- Stop jumps to "wait for the drum" from any step that runs something.
