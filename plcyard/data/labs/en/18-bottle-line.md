---
title: Bottle filling and capping line
simulation: bottles
level: 4
symbols:
- %I0.0 Start (PB)
- %I0.1 Stop (NC, PB)
---
# 18. Bottle filling and capping line

**Goal:** a conveyor carries bottles under a filler, a capper and an inspection station; stop the
belt for each station, and push the bad bottles off.

## Inputs and outputs (Bottle line simulation)

| Address | Device |
| --- | --- |
| %I0.0 | Start (pushbutton) |
| %I0.1 | Stop (pushbutton, **normally closed**) |
| %I0.2 | Bottle at the filler |
| %I0.3 | Bottle full (the bottle at the filler is at 95 % or more) |
| %I0.4 | Bottle at the capper |
| %I0.5 | Bottle at inspection |
| %I0.6 | The bottle at inspection is good |
| %Q0.0 | Conveyor |
| %Q0.1 | Fill valve |
| %Q0.2 | Capper press |
| %Q0.3 | Reject pusher |
| %Q0.4 | Run lamp |

A bottle stays under a station only if the conveyor stops while the station's sensor sees it. The
press needs half a second on a bottle to cap it. Every fifth bottle gets a bad cap.

## Requirements

1. Start runs the line: at least 8 good bottles shipped in 2 minutes.
2. No bad bottle is shipped.
3. Bad bottles are rejected at inspection; good ones are not.
4. No spill, no overflow, no capping a moving bottle.
5. The run lamp is on while the line runs.
6. Stop turns the conveyor, the filler, the capper and the run lamp off.

## Hints

- The conveyor runs unless a station is working: "filling" is a bottle at the filler that is not
  full yet; "capping" is a bottle at the capper during the first 0.6 s (a TON on the sensor).
- Fill only while the conveyor is stopped.
- The reject pusher is simply "a bottle at inspection that is not good".
