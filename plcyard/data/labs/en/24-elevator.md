---
title: Three-floor elevator
simulation: elevator
level: 5
symbols: []
---
# 24. Three-floor elevator

**Goal:** serve hall and car calls on three floors: remember every call, travel to it, stop level
with the floor, open and close the door safely.

## Inputs and outputs (Elevator simulation)

| Address | Device |
| --- | --- |
| %I0.0, %I0.1, %I0.2 | Hall call buttons, floors 1-3 |
| %I0.3, %I0.4, %I0.5 | Car buttons, floors 1-3 |
| %I0.6, %I0.7, %I1.0 | Car at floor 1, 2, 3 |
| %I1.1 | Door open limit |
| %I1.2 | Door closed limit |
| %I1.3 | Door safety edge clear (TRUE unless someone is in the doorway) |
| %I1.4 | Top overtravel OK |
| %I1.5 | Bottom overtravel OK |
| %Q0.0, %Q0.1 | Motor up, motor down |
| %Q0.2, %Q0.3 | Door open, door close |
| %Q0.4, %Q0.5, %Q0.6 | Position lamps, floors 1-3 |

The car starts at floor 1 with the door closed. It travels one floor in 3 s; the door opens or
closes in 2 s.

## Requirements

1. A hall call brings the car and opens the door at that floor.
2. A car button takes the car to its floor.
3. Calls are remembered (the buttons are only pressed for a moment) and all served.
4. The door reopens, or stays open, while someone is in the doorway.
5. The position lamps show the floor the car is at.
6. The car never moves with the door open, the door never opens between floors and never closes
   on someone.

## Hints

- Latch a call bit per floor from its hall and car buttons; clear it when the door is fully open
  at that floor.
- Keep the last floor the car passed in an integer tag (it starts at 1).
- "Here" is a call at the floor the car is at; "above" and "below" are calls further up or down.
- Steps: 0 idle, 1 opening, 2 open (wait), 3 going up, 4 going down, 5 closing. Close only while
  the doorway is clear; if it is not, open again.
