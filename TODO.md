# TODO

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

## The PLC
- [x] One PLC with tags, data types, arrays, routines, functions and function blocks; two notations
      (mnemonics / IEC symbols) chosen in Tools → Options; older programs converted on load.
- [x] Ladder and structured text, several routines per program in either language.
- [x] PID, analog I/O, tank simulation with trend; exercises 1-13.
- [x] Forcing I/O; online bar; drag I/O from the simulations onto the ladder; examples.
- [x] PID setup dialog (tuning, configuration, alarms, scaling) for the PID instruction.
- [x] Phase 5: function block diagram (FBD) editor and runtime, sharing the instructions with ladder and ST.
- [ ] **Next — Phase 6:** the same exercises solved in ladder, structured text and FBD.
- [ ] Instructions still missing: ramps, CTUD, R_TRIG / F_TRIG boxes, strings, date/time;
      routines with parameters; function return values.

## Documentation
- [ ] Wiki: getting started, every instruction with an example, how the scan works, how to write an
      exercise and its checks, how to add a simulation.

## Later
- [ ] Real hardware I/O: Arduino and/or ESP32 as remote I/O over USB serial (then Wi-Fi), to test
      programs with real switches and lamps (docs/ROADMAP.md, "Later").
- [ ] More UI languages (main languages); English only for now.
- [ ] More simulations: door, elevator, batch mixing, bottle line.
