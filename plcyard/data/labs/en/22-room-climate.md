---
title: Room climate with heating and cooling
simulation: hvac
level: 5
symbols:
- %I0.0 On (PB)
- %I0.1 Off (NC, PB)
---
# 22. Room climate with heating and cooling

**Goal:** keep a room at the temperature of the setpoint knob with a heater and a cooler, both
analog, never both at once and never without the fan.

## Inputs and outputs (Room climate simulation)

| Address | Device |
| --- | --- |
| %I0.0 | System on (pushbutton) |
| %I0.1 | System off (pushbutton, **normally closed**) |
| %I0.2 | Window open |
| %I0.3 | Airflow: the fan is running |
| %IW64 | Room temperature, 0-27648 = 0-50 °C |
| %IW66 | Setpoint knob, 0-27648 = 0-50 °C |
| %Q0.0 | Fan |
| %Q0.1 | Heating lamp |
| %Q0.2 | Cooling lamp |
| %QW64 | Heater, 0-27648 = 0-100 % |
| %QW66 | Cooler, 0-27648 = 0-100 % |

The room starts at 16 °C with 8 °C outside. Heating or cooling without the fan overheats the coil
(the simulation ignores it and reports it); heating and cooling together only wastes energy.

## Requirements

1. On starts the fan and brings the room to the setpoint (±0.5 °C) within 2 minutes.
2. It holds the temperature (±1 °C) with the window open and 18 °C outside.
3. It cools when it is hot outside (35 °C), within ±1 °C.
4. It follows a new setpoint (24 °C) within ±1 °C.
5. The heating and cooling lamps show what is working.
6. It never heats and cools at once, and never without the fan.
7. Off stops the fan, the heater and the cooler.

## Hints

- One PID can drive both: let its output run from -100 % (full cooling) to +100 % (full heating)
  with the output minimum of the PID tag set to -100. The heater gets the positive part, the
  cooler the negative part.
- Scale the room and the setpoint to °C (0-27648 → 0-50) and the outputs back (0-100 % →
  0-27648).
- No airflow, no heating or cooling: force the demand to 0 when the fan is not proven.
