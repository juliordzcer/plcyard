---
title: Continuous filling on the silo line
simulation: silo
level: 2
---
# 8. Continuous filling on the silo line

**Goal:** control a real process: conveyor, position sensor, valve and level sensor.

## Inputs and outputs (Silo simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Start (NO pushbutton) |
| %I0.1 | Stop (NC pushbutton) |
| %I0.3 | Proximity sensor: box under the hopper |
| %I0.4 | Level sensor: box full |
| %Q0.0 | Conveyor motor |
| %Q0.1 | Fill valve |
| %Q0.2 | Run light · %Q0.3 Fill light · %Q0.4 Full light |

## Requirements

1. Start and Stop control the system at any time; the Run light shows it is running.
2. Each box stops under the hopper, fills, and moves on by itself.
3. The Fill light is on while filling; the Full light from the moment the box is full until it leaves the sensor.
4. No product may be spilled.
5. Stop turns off the motor, the valve and the Run light.
