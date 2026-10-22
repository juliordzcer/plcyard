---
title: Sorting boxes by size
simulation: sorter
level: 5
symbols:
- %I0.0 Start (PB)
- %I0.1 Stop (NC, PB)
---
# 19. Sorting boxes by size

**Goal:** measure each box with two light beams and push it into the bin for its size, further down
the belt, while other boxes are already on the way.

## Inputs and outputs (Sorting conveyor simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Start (pushbutton) |
| %I0.1 | Stop (pushbutton, **normally closed**) |
| %I0.2 | Box at the measuring point |
| %I0.3 | Low beam blocked (medium or large box) |
| %I0.4 | High beam blocked (large box) |
| %I0.5, %I0.6, %I0.7 | Box in front of pusher 1, 2, 3 |
| %Q0.0 | Conveyor |
| %Q0.1, %Q0.2, %Q0.3 | Pusher 1 (small), pusher 2 (medium), pusher 3 (large) |
| %Q0.4 | Run lamp |

Boxes come small, large, medium, medium, small, large, … A box that reaches the end of the belt
falls off.

## Requirements

1. Start runs the belt: at least 15 boxes sorted in 90 seconds.
2. Every box goes into the bin for its size.
3. No box falls off the end of the belt.
4. The run lamp is on while the belt runs.
5. Stop stops the belt and turns the run lamp off.

## Hints

- Several boxes are between the beams and the pushers at once, so remember the sizes in order:
  a queue (an array and a write index) for each stretch of belt.
- When a new box reaches the measuring point (rising edge), its size is 1, or 2 if the low beam is
  blocked, or 3 if the high beam is blocked too; write it into the queue for pusher 1.
- When a box reaches pusher k (rising edge), read the next size from queue k: push it if it is
  size k, otherwise write it into queue k+1.
- Indexed addresses work everywhere: `Q1[W1]` in a MOV, a MOVE block or structured text.
