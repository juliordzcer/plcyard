# TODO

Planned after the first release. The current SLC 500-style ladder trainer stays as it is until then.

## Modern PLC models
- [ ] Controller profiles beyond SLC 500: a Logix-style controller (tags instead of file addresses,
      as in Studio 5000) and an S7-1200/1500-style controller (Siemens TIA Portal).
- [ ] New instruction blocks those controllers have: PID, scaling (SCP), ramps, edge detection
      (R_TRIG / F_TRIG), IEC timers and counters (TON/TOF/TP, CTU/CTD/CTUD), string and date/time.
- [ ] PID exercise with a process simulation (tank level or temperature) to tune against.

## Three programming languages (IEC 61131-3)
- [x] Ladder (LD): done.
- [ ] Function block diagram (FBD): both Allen-Bradley (Studio 5000) and Siemens (TIA Portal) have it.
- [ ] Structured text: Allen-Bradley calls it ST, Siemens calls it SCL. Same language family,
      Pascal-like; start with one dialect close to both.
- [ ] Same exercises solvable in all three, so a learner can compare them.

## Documentation
- [ ] Wiki: getting started, every instruction with an example, how the scan works, how to write an
      exercise and its checks, how to add a simulation.

## Later
- [ ] More UI languages (main languages); English only for now.
- [ ] More simulations: door, elevator, batch mixing, bottle line.
