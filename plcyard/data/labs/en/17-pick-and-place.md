---
title: Pick and place cycle
simulation: pick_place
level: 4
symbols:
- %I0.0 Start (PB)
- %I0.1 Stop (NC, PB)
---
# 17. Pick and place cycle

**Goal:** a two-axis pneumatic arm with a vacuum gripper moves parts from the infeed to a tray, one
cycle after the other, in a safe order of moves.

## Inputs and outputs (Pick and place simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Start (pushbutton) |
| %I0.1 | Stop (pushbutton, **normally closed**) |
| %I0.2, %I0.3 | Arm at the pick side, arm at the place side (horizontal cylinder) |
| %I0.4, %I0.5 | Arm up, arm down (vertical cylinder) |
| %I0.6 | Part waiting at the pick point |
| %I0.7 | Vacuum OK: the gripper holds a part |
| %Q0.0 | Horizontal cylinder: extend to the place side |
| %Q0.1 | Vertical cylinder: down |
| %Q0.2 | Vacuum |
| %Q0.3 | Cycle lamp |

Each cylinder takes one second from end to end. A new part arrives one second after the last one
was picked.

## Requirements

1. Start runs cycles while parts come: down, grip, up, across, down, release, up, back. At least
   5 parts placed in a minute.
2. No part is dropped outside the tray.
3. The arm never moves sideways while it is down.
4. The cycle lamp is on during a cycle.
5. Stop lets the current cycle finish with the arm back home, and no new cycle starts.

## Hints

- A step number (0 home, 1 down, 2 grip, …) makes the sequence easy to follow; each step waits for
  its sensor (arm down, vacuum OK, arm up…) before the next one.
- Every output is a list of steps: "down" is on in the steps where the arm goes or stays down.
- Give the release a short timer (a few hundred ms) before lifting the arm.
- Only the home step looks at Run: Stop then ends the work after the current cycle.
