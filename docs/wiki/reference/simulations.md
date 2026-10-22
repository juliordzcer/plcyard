# Simulations

Every simulation, its inputs and outputs as the PLC sees them (canonical addresses; the
mnemonic notation shows them as `Local:<slot>:I.Data.<point>`). Choose one in the
Simulations menu.

## I/O panel

Menu key `io`.

Generic I/O trainer: 2 input cards of switches, 2 output cards of lamps,
4 BCD thumbwheels on %IW4 and a 4-digit BCD display on %QW4.

## Silo

Menu key `silo`.

Silo filling line: boxes ride a conveyor, stop under a hopper, fill, move on.

I/O:
  %I0.0 Start (NO pushbutton)   %I0.1 Stop (NC pushbutton)
  %I0.3 Prox sensor (box under the hopper)   %I0.4 Level sensor (box full)
  %I0.5 / %I0.6 / %I0.7 Selector A / B / C
  %Q0.0 Conveyor motor   %Q0.1 Fill solenoid   %Q0.2 Run lamp   %Q0.3 Fill lamp   %Q0.4 Full lamp
Idle input word is 0022h: Stop is NC (closed) and the selector rests on A.

## Traffic lights

Menu key `traffic`.

Intersection with two traffic directions, crosswalk buttons and two cars.

I/O:
  %Q0.0 Red A   %Q0.1 Amber A   %Q0.2 Green A   %Q0.3 Walk (crossing A)
  %Q0.4 Red B   %Q0.5 Amber B   %Q0.6 Green B   %Q0.7 Walk (crossing B)
  %I0.0 Crosswalk button A   %I0.1 Crosswalk button B
  %I0.2 Car waiting at A     %I0.3 Car waiting at B
Car A drives along road A (lights %Q0.0-%Q0.2), car B along road B (%Q0.4-%Q0.6).
A car stops at its stop line unless its light is green; on amber it keeps going if it is
already close to the line. Two cars inside the junction at the same time is a crash.

## Tank level

Menu key `tank`.

Tank level process: an analog loop to control with on/off or PID.

Water enters through a pump (on/off) or a proportional inlet valve (0-10 V) and leaves through an
outlet whose opening the user sets (the disturbance). The level is measured 0-100 % and sent as
0-10 V; a setpoint knob sends 0-10 V on a second analog input.

Digital I/O (slot words, like the other simulations):
  %I0.0 Start (NO pushbutton)   %I0.1 Stop (NC pushbutton)
  %I0.2 High level switch (level >= 90 %)   %I0.3 Low level switch (level <= 10 %)
  %Q0.0 Pump (fixed flow)   %Q0.1 Run lamp   %Q0.2 High alarm lamp
Analog: AI0 level (0-10 V = 0-100 %), AI1 setpoint knob (0-10 V), AO0 inlet valve (0-10 V = 0-100 %).

## Two tanks

Menu key `two_tanks`.

Two tanks in series: an analog process for two loops or a cascade.

Water enters the upper tank 1 through a proportional inlet valve (or an on/off pump), flows down
into tank 2 through a proportional transfer valve, and leaves tank 2 through an outlet whose
opening the user sets (the disturbance). Flows through the valves fall with the square root of
the level above them, as in a real gravity-fed tank.

Digital (slot words): %I0.0 Start (NO)  %I0.1 Stop (NC)  %I0.2 Tank 1 high (>= 90 %)
  %I0.3 Tank 2 high (>= 90 %)  %I0.4 Tank 2 low (<= 10 %)
  %Q0.0 Feed pump (fixed flow)  %Q0.1 Run lamp  %Q0.2 Alarm lamp
Analog: AI0 tank 1 level, AI1 tank 2 level, AI2 setpoint knob (0-10 V = 0-100 %);
  AO0 inlet valve, AO1 transfer valve (0-10 V = 0-100 %).

## Garage door

Menu key `garage`.

Garage door: a motor that opens and closes a sectional door, end-of-travel switches, a safety
photo-eye across the doorway and a flashing warning light.

Digital (slot words):
  %I0.0 Open button (NO)   %I0.1 Close button (NO)   %I0.2 Stop button (NC)
  %I0.3 Open limit (door fully up)   %I0.4 Closed limit (door fully down)
  %I0.5 Photo-eye beam clear (TRUE when nothing is in the doorway: fails safe)
  %Q0.0 Motor up   %Q0.1 Motor down   %Q0.2 Warning light   %Q0.3 Courtesy light
The door travels 0-100 % in 10 s. A car parked in the doorway is hit if the door reaches 30 %
while closing on it.

## Batch mixer

Menu key `mixer`.

Batch mixer: fill with two ingredients, mix and heat, then drain the batch.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Low level (>= 5 %)   %I0.3 Middle level (>= 50 %)
  %I0.4 High level (>= 90 %)
  %Q0.0 Valve A   %Q0.1 Valve B   %Q0.2 Mixer motor   %Q0.3 Heater   %Q0.4 Drain valve
  %Q0.5 Batch done lamp
Analog: AI0 temperature, 0-10 V = 0-100 °C.

A good batch: ingredient A up to the middle level, ingredient B on top up to the high level,
mixed at least 5 s and at 50-60 °C before it is drained. Every drained batch is graded.

## Elevator

Menu key `elevator`.

Elevator for three floors: hall and car buttons, floor sensors, a door with limits and a safety
edge, overtravel limits at both ends of the shaft.

Digital (slot words):
  %I0.0-%I0.2 Hall call floors 1-3   %I0.3-%I0.5 Car buttons floors 1-3
  %I0.6 %I0.7 %I1.0 Car at floor 1, 2, 3   %I1.1 Door open limit   %I1.2 Door closed limit
  %I1.3 Door safety edge clear (TRUE unless someone is in the doorway)
  %I1.4 Top overtravel OK   %I1.5 Bottom overtravel OK (TRUE unless the car passed the end)
  %Q0.0 Motor up   %Q0.1 Motor down   %Q0.2 Door open   %Q0.3 Door close
  %Q0.4-%Q0.6 Position lamps floors 1-3
The car travels a floor in 3 s, the door opens or closes in 2 s. A call is served when the door
opens at its floor.

## Bottle line

Menu key `bottles`.

Bottle line: a conveyor carries empty bottles past a filler, a capper and an inspection station
with a reject pusher. Every fifth bottle gets a bad cap from the capper and must be rejected.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Bottle at the filler   %I0.3 Bottle full
  %I0.4 Bottle at the capper   %I0.5 Bottle at inspection   %I0.6 Bottle at inspection is good
  %Q0.0 Conveyor   %Q0.1 Fill valve   %Q0.2 Capper press   %Q0.3 Reject pusher   %Q0.4 Run lamp
A bottle stops under a station only if the conveyor stops while the station's sensor sees it.

## Sorting conveyor

Menu key `sorter`.

Sorting conveyor: boxes of three heights pass two light beams that measure them, then three
pushers send each box into the bin for its size.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Box at the measuring point
  %I0.3 Low beam blocked (medium or large box)   %I0.4 High beam blocked (large box)
  %I0.5 %I0.6 %I0.7 Box in front of pusher 1, 2, 3
  %Q0.0 Conveyor   %Q0.1 Pusher 1 (small)   %Q0.2 Pusher 2 (medium)   %Q0.3 Pusher 3 (large)
  %Q0.4 Run lamp
Boxes arrive in the order small, large, medium, medium, small, large, …; a box that reaches the end
of the belt falls off.

## Pick and place

Menu key `pick_place`.

Pick and place: a two-axis pneumatic arm moves parts from an infeed to a tray with a vacuum
gripper.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Arm at pick side (horizontal retracted)
  %I0.3 Arm at place side (horizontal extended)   %I0.4 Arm up   %I0.5 Arm down
  %I0.6 Part waiting at the pick point   %I0.7 Vacuum OK (a part is held)
  %Q0.0 Horizontal cylinder: extend   %Q0.1 Vertical cylinder: down   %Q0.2 Vacuum
  %Q0.3 Cycle lamp
Each cylinder takes 1 s from end to end. Moving sideways while the arm is down knocks things over.

## Parking garage

Menu key `parking`.

Parking garage: entry and exit barriers with car detectors, a car counter and a FULL sign.
Ten spaces.

Digital (slot words):
  %I0.0 Car waiting at the entry   %I0.1 Car passed the entry barrier (beam)
  %I0.2 Car waiting at the exit   %I0.3 Car passed the exit barrier (beam)
  %I0.4 Entry barrier up   %I0.5 Exit barrier up
  %Q0.0 Raise entry barrier   %Q0.1 Raise exit barrier   %Q0.2 FULL sign
  %QW4 Free spaces on the display (BCD)
Cars arrive from the "Car arrives" and "Car leaves" buttons, or every few seconds with "Traffic".
A barrier rises in 1 s and stays up while its output is on.

## Pump station

Menu key `pumps`.

Pump station: a sump fills with an inflow you set; two pumps empty it. They should take turns
(equal running hours), the second one helps when the level keeps rising, and a failed pump is
replaced by the other.

Digital (slot words):
  %I0.0 Reset alarm (NO)   %I0.1 Stop (NC)   %I0.2 Low level (>= 15 %)   %I0.3 Start level (>= 50 %)
  %I0.4 High level (>= 75 %)   %I0.5 Overflow alarm level (>= 95 %)
  %I0.6 Pump 1 fault   %I0.7 Pump 2 fault (TRUE when the pump's protection tripped)
  %Q0.0 Pump 1   %Q0.1 Pump 2   %Q0.2 Alarm lamp
Analog: AI0 level, 0-10 V = 0-100 %.

## Room climate

Menu key `hvac`.

Room climate: temperature with a heater and a cooler (analog), a fan they need, an outside
temperature and a window that can be opened.

Digital (slot words):
  %I0.0 System on (NO)   %I0.1 System off (NC)   %I0.2 Window open   %I0.3 Airflow (fan running)
  %Q0.0 Fan   %Q0.1 Heating lamp   %Q0.2 Cooling lamp
Analog: AI0 room temperature 0-10 V = 0-50 °C, AI1 setpoint knob 0-10 V = 0-50 °C,
  AO0 heater 0-10 V = 0-100 %, AO1 cooler 0-10 V = 0-100 %.
Heating or cooling without the fan overheats the coil; heating and cooling together wastes energy.

## Washing machine

Menu key `washer`.

Washing machine: lock the door, fill, wash turning left and right, drain, spin, unlock.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Door closed   %I0.3 Door locked
  %I0.4 Water present (level >= 10 %)   %I0.5 Water full (>= 80 %)   %I0.6 Drum stopped
  %Q0.0 Door lock   %Q0.1 Fill valve   %Q0.2 Wash left   %Q0.3 Wash right   %Q0.4 Spin
  %Q0.5 Drain pump   %Q0.6 Done lamp
A good wash: the clothes turn in water at least 10 s each way, the water is drained before the
spin, the spin lasts at least 5 s, and the door unlocks only once the drum has stopped.
