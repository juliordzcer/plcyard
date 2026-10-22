---
title: Parking garage barriers and counter
simulation: parking
level: 3
symbols: []
---
# 20. Parking garage barriers and counter

**Goal:** let cars in and out with two barriers, count them and show the free spaces; keep cars
out when the garage is full.

## Inputs and outputs (Parking garage simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Car waiting at the entry |
| %I0.1 | Car passing the entry barrier (beam) |
| %I0.2 | Car waiting at the exit |
| %I0.3 | Car passing the exit barrier (beam) |
| %I0.4, %I0.5 | Entry barrier up, exit barrier up |
| %Q0.0 | Raise the entry barrier |
| %Q0.1 | Raise the exit barrier |
| %Q0.2 | FULL sign |
| %QW4 | Free spaces display (BCD) |

The garage has ten spaces and **three cars are parked when it starts**. Cars come with the "Car
arrives" and "Car leaves" buttons (or with Traffic).

## Requirements

1. The display shows the free spaces from the start (7).
2. A car waiting at the entry gets the barrier; it comes down once the car is in.
3. Cars coming in are counted on the display.
4. A car leaving gets the exit barrier and is counted.
5. FULL lights with ten cars in.
6. With the garage full the entry barrier stays down for a waiting car.
7. When a car leaves, the waiting car comes in.
8. No barrier comes down on a car.

## Hints

- Keep the number of cars in an integer tag that starts at 3 (its initial value in the tag list).
- Latch "raise" when a car waits (at the entry only if there is room), unlatch it on the falling
  edge of the beam: that is when the car has passed, and the moment to count it.
- Show `10 - count` with a BCD conversion (TOD) on the display word.
