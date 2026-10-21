---
title: Two-way traffic light without crashes
simulation: traffic
level: 3
---
# 10. Two-way traffic light without crashes

**Goal:** sequence two traffic lights with cascaded timers and an all-red interval.

## Inputs and outputs (Traffic lights simulation)

| Address | Use |
| --- | --- |
| O:2/0, O:2/1, O:2/2 | direction A: red, amber, green |
| O:2/4, O:2/5, O:2/6 | direction B: red, amber, green |

## Requirements

1. A: green 6 s, amber 2 s; then red while B runs its cycle.
2. B: green 6 s, amber 2 s; then red while A runs its cycle.
3. Between one direction's amber and the other's green there is **1 s with both red**.
4. At every moment each direction has exactly one light on.
5. Cars cross without crashing (run it for at least 2 minutes).

## Think about it

Remove the all-red second and watch: why do the cars sometimes crash?
