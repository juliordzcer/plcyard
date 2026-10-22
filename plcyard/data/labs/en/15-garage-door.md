---
title: Garage door with a safety photo-eye
simulation: garage
level: 3
symbols:
- %I0.0 Open (PB)
- %I0.1 Close (PB)
- %I0.2 Stop (NC, PB)
---
# 15. Garage door with a safety photo-eye

**Goal:** open and close a door safely: end-of-travel limits, a stop button, a photo-eye that
protects a car in the doorway, a warning light and a courtesy light.

## Inputs and outputs (Garage door simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Open (pushbutton) |
| %I0.1 | Close (pushbutton) |
| %I0.2 | Stop (pushbutton, **normally closed**) |
| %I0.3 | Open limit (door fully up) |
| %I0.4 | Closed limit (door fully down) |
| %I0.5 | Photo-eye: TRUE while the beam is clear |
| %Q0.0, %Q0.1 | Motor up, motor down |
| %Q0.2 | Warning light |
| %Q0.3 | Courtesy light |

## Requirements

1. Open runs the door up and stops at the open limit; Close runs it down to the closed limit.
2. Stop halts the door where it is.
3. If the beam breaks while the door is closing, the door goes back up; Close does nothing while
   something is in the doorway.
4. The warning light flashes while the door moves.
5. The courtesy light is on while the door moves and for some seconds after it stops.
6. The motor never keeps pushing at an end stop and never runs both ways at once.

## Hints

- Seal-in each direction like a motor starter; the opposite direction and the limit break it.
- Remember "reversing" with a latch that the open limit clears.
- A self-resetting timer and a compare on its accumulator make a blinker; a TOF keeps the courtesy
  light on.
