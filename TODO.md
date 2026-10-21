# TODO

Planned after the first release. The current SLC 500-style ladder trainer stays as it is until then.
How and in what order: [docs/ROADMAP.md](docs/ROADMAP.md).

## Before announcing
- [ ] Trademark screening for "PLCYard": USPTO (classes 9 and 42), EUIPO/TMview, WIPO.
- [ ] Read 20-30 learner threads by hand (r/PLC, r/PLCProgramming, plctalk.net) to confirm what
      people need; adjust the README and site copy.
- [ ] Final icon and wordmark (draft: `plcyard/ui/assets/icon.svg`): SVG, 1024 px PNG, favicons,
      1200x630 social image.
- [ ] Upload `site/` to juliordz.com.
- [x] Open exercise solutions read-only (Save asks for a new name): one was overwritten by accident.
- [x] GitHub release v0.1.0 with notes and screenshots; issue templates (bug, exercise idea).
- [x] Ship `labs/` and `samples/` inside the package so a non-editable install works.
- [ ] Publish to PyPI as `plcyard` (needs a PyPI account and API token: `python -m build`,
      `twine upload dist/*`).
- [ ] Post where learners ask how to practise without hardware (see the subreddit rules first),
      Show HN.

## Modern PLC models
- [x] Phase 1: controller profiles on a shared scan engine, `.plcy` project files.
- [x] Phase 2: Logix and S7 profiles in ladder, tag list, controller-aware editor and simulations.
- [x] Phase 3: PID (Logix PID, S7 PID_Compact), analog I/O, tank simulation with trend, exercises 11-12.
- [x] Phase 4: structured text (ST / SCL) for Logix and S7, editor with live watch list.
- [ ] **Next — Phase 5:** function block diagram (FBD), see docs/ROADMAP.md.
- [ ] SLC 500 PID instruction (control block in an N file); a PID exercise for S7.
- [ ] Forcing I/O from the tag list; arrays and user structures; Logix routines (JSR); S7 FBs/DBs.
- [ ] Controller profiles beyond SLC 500: a Logix-style controller (tags instead of file addresses,
      as in Studio 5000) and an S7-1200/1500-style controller (Siemens TIA Portal).
- [ ] New instruction blocks those controllers have: PID, scaling (SCP), ramps, edge detection
      (R_TRIG / F_TRIG), IEC timers and counters (TON/TOF/TP, CTU/CTD/CTUD), string and date/time.
- [x] PID exercise with a process simulation (tank level) to tune against.

## Three programming languages (IEC 61131-3)
- [x] Ladder (LD): done.
- [ ] Function block diagram (FBD): both Allen-Bradley (Studio 5000) and Siemens (TIA Portal) have it.
- [x] Structured text: Allen-Bradley calls it ST, Siemens calls it SCL. Same language family,
      Pascal-like; one dialect close to both.
- [ ] Same exercises solvable in all three, so a learner can compare them.

## Documentation
- [ ] Wiki: getting started, every instruction with an example, how the scan works, how to write an
      exercise and its checks, how to add a simulation.

## Later
- [ ] More UI languages (main languages); English only for now.
- [ ] More simulations: door, elevator, batch mixing, bottle line.
