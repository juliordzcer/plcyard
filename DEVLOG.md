# Development log

Every bug found and every significant change. Paths under `replica/` are private planning notes
and are not part of the public repository. If something similar shows up, search here first:

```bash
grep -n -i "segfault\|paint" DEVLOG.md        # by symptom
grep -n "area: rsl" DEVLOG.md                  # by area
```

Entry format:

```
## F-NNN (fault) or C-NNN (change) — short title
date · area: <core|isa|rsl|ui|sims|tests|env> · commit: <hash>
symptom:   what was seen
cause:     why it happened
fix:       what was changed
prevent:   test or rule that keeps it from coming back
keys:      words to grep for
```

Areas: `core` (processor, data table, addresses), `isa` (instructions), `rsl` (files),
`ui` (interface), `sims` (simulations), `tests`, `env` (machine, tools).

---

## Faults

## F-001 — Segfault drawing the 7-segment display
2026-10-21 · area: ui · commit: 57ef05c
symptom:   `python -m plcyard.ui.gallery --shot` ended with "Segmentation fault"; with
           `-X faulthandler` it pointed at `w.grab()`.
cause:     `QPen(color, 3.5, cap=Qt.RoundCap)` raises TypeError (PySide6 does not accept `cap=`).
           An exception inside `paintEvent` leaves the QPainter open and Qt crashes.
fix:       positional arguments: `QPen(color, 3.5, Qt.SolidLine, Qt.RoundCap)`.
prevent:   isolate the widget with `w.grab()` in a script; any exception in paintEvent can look
           like a segfault. Typical message: "Cannot destroy paint device that is being painted".
keys:      segfault, paintEvent, QPen, grab, crash, faulthandler

## F-002 — TON/CTU blocks cut off their last row
2026-10-21 · area: ui · commit: 57ef05c
symptom:   "Accum" not visible in the gallery.
cause:     block height computed as 30 + 17·n with no bottom margin.
fix:       42 + 17·n (now in `ladder_layout.instr_size`).
prevent:   check the gallery in both themes after touching `paint_instruction`.
keys:      block, height, clip, TON, CTU

## F-003 — 7-segment display with a light background in the dark theme
2026-10-21 · area: ui · commit: 57ef05c
symptom:   the display looked light grey in dark mode.
cause:     it used the `rail` token (light in dark mode) as background.
fix:       its own `display-bg` token in both themes.
prevent:   every new surface gets its own token; do not reuse tokens meant for something else.
keys:      dark theme, token, display, background

## F-004 — Insufficient contrast for an off lamp (dark)
2026-10-21 · area: ui · commit: 57ef05c
symptom:   `contrast.py` reported 2.56:1 for `lamp-off` on `sim-bg`.
fix:       `lamp-off` #7d8590 in the dark theme.
prevent:   `python3 contrast.py tokens.dark.json` after changing colours (must report 0 failures).
keys:      contrast, WCAG, AA, colour

## F-005 — An .rsl without tables was not written back identically
2026-10-21 · area: rsl · commit: 5ead119
symptom:   41/42 samples identical; `Batch-Mix-min-2-product.rsl` differed at line 40.
cause:     that file has no BTBL/NTBL/FTBL and the writer always added them.
fix:       only tables that were read are written; `Program.new()` creates them empty.
prevent:   round-trip test with the 42 local samples (`PLCYARD_SAMPLES`).
keys:      rsl, round-trip, BTBL, NTBL, FTBL, byte-identical

## F-006 — pytest would not start (yaml / launch_testing)
2026-10-21 · area: env · commit: —
symptom:   `ModuleNotFoundError: No module named 'yaml'` from `/opt/ros/jazzy/...`.
cause:     ROS adds its `PYTHONPATH` and pytest loads ROS plugins.
fix:       run `env -u PYTHONPATH .venv/bin/python -m pytest`.
prevent:   use that command on machines with ROS installed.
keys:      pytest, ROS, PYTHONPATH, plugin, yaml, launch

## F-007 — The start/stop sample never started
2026-10-21 · area: sims · commit: a833e13
symptom:   with Stop not pressed, the motor did not turn on.
cause:     Stop is examined with XIC because it is NC, but the I/O panel created every switch as
           NO, so the input stayed at 0.
fix:       `IoPanelModel.configure_from_symbols`: NC/N.C. → normally closed;
           PB/pushbutton (and Spanish pulsador/botón) → pushbutton. Sample symbol: "Stop (NC)".
prevent:   `test_shipped_start_stop_sample`; state NO/NC in the symbol of every input.
keys:      stop, NC, NO, normally closed, XIC, XIO, seal-in, switch

## F-008 — RuntimeError "Internal C++ object (IoPanelView) already deleted"
2026-10-21 · area: ui · commit: a833e13
symptom:   opening a program closed the window with that error.
cause:     `QScrollArea.setWidget()` already deletes the previous widget; `old.deleteLater()` was
           then called on a destroyed object.
fix:       do not delete by hand what `setWidget` replaces.
keys:      deleteLater, already deleted, shiboken, QScrollArea, setWidget

## F-009 — Long comments and symbols overlapping in the ladder
2026-10-21 · area: ui · commit: a833e13
symptom:   a two-line comment covered the rung; long symbols ran into each other.
cause:     comment height computed from line breaks, not word wrap; symbols not clipped.
fix:       `QFontMetrics.boundingRect(... TextWordWrap)`; `elidedText` for symbols.
keys:      comment, wrap, symbol, overlap, elide

## F-010 — OTE not reset on entering RUN; S:1/15 missing
2026-10-21 · area: core · commit: bcf4791
symptom:   a seal-in stayed on after PGM → RUN.
cause:     the manual's prescan was missing (OTE resets, OTL/OTU are kept).
fix:       `Processor._prescan`; first-scan bit S:1/15.
prevent:   `test_seal_in_drops_when_returning_to_run`, `test_first_pass_bit_only_on_first_scan`.
keys:      prescan, RUN, OTE, OTL, retentive, first scan, first pass, S:1/15

## F-011 — SQO with 5 operands rejected
2026-10-21 · area: isa · commit: 2be5b58
symptom:   `sequencer.rsl`: "SQO needs 6 operand(s), has 5".
cause:     some files omit Position.
fix:       `Spec.optional`; Position optional in SQO/SQC/SQL.
prevent:   run the 42 samples (download + 5 s) after touching `isa`.
keys:      SQO, SQC, SQL, operands, position, sequencer

## F-012 — Counters "did not count" in tests (not an engine bug)
2026-10-21 · area: tests · commit: 2be5b58
symptom:   a CTU with its input already pressed on the first scan stayed at 0.
cause:     correct SLC behaviour: CU/CD are set before entering RUN, so it does not count on the
           first scan.
fix:       tests run one scan before pressing.
keys:      CTU, CTD, CU, first scan, does not count, counter

## F-013 — 2-scan all-off gap in the traffic lights (not a bug)
2026-10-21 · area: isa · commit: 2be5b58
symptom:   in Traffic-TON-Exercise-1 all three lights go off for 20 ms when the cycle restarts.
cause:     the program drives the lights from TT; the DN scan and the reset scan leave everything
           off. A real SLC does the same.
keys:      traffic, gap, flicker, TT, DN, cascade

## F-014 — The major fault cleared itself
2026-10-21 · area: ui · commit: 4fd6d29
symptom:   on a FAULT the panel went back to "PGM" and the Clear fault button never showed.
cause:     `_tick` set the selector to PGM, which called `set_mode(PGM)` and left FAULT.
fix:       in FAULT, `MainWindow.set_mode` does not change the processor; only "Clear fault" leaves.
keys:      fault, clear fault, PGM, selector, mode

## F-015 — The letter O in O:2/0 looked like a zero
2026-10-21 · area: ui · commit: 4fd6d29
cause:     no bundled monospace font; the system fallback drew O and 0 the same.
fix:       Inter and JetBrains Mono (OFL) in `plcyard/ui/assets/fonts`, loaded in `theme.load_fonts`.
keys:      font, O, zero, monospace, JetBrains

## F-016 — Tools: the reference app under Wine cannot be driven from scripts
2026-10-21 · area: env · commit: —
symptom:   `xdotool` did not click the menus; menu screenshots came out empty.
cause:     Wayland session: Wine menus are separate windows and XWayland does not get the clicks.
fix:       screenshots taken by hand; Wine isolated in its own prefix with no network (`unshare -n`).
keys:      wine, xdotool, wayland, screenshot

## F-017 — UI tests took ~30 s to close
2026-10-21 · area: tests · commit: b13cafe
symptom:   `--durations` showed 3–28 s in the teardown of every UI test.
cause:     `qtbot.addWidget` (pytest-qt) closing the main window; the real close is instant.
fix:       the fixture stops the QTimers and closes the window by hand (`close`, `deleteLater`,
           `processEvents`).
prevent:   run `pytest --durations=5` if the suite gets slow.
keys:      slow, teardown, qtbot, pytest-qt, QTimer

## F-018 — The operand editor appeared outside the view
2026-10-21 · area: ui · commit: b13cafe
symptom:   double-clicking a block near the right rail: the editor was not visible.
cause:     positioned with the full canvas width, not the visible part of the scroll area
           (opening the data table narrows the ladder).
fix:       `visibleRegion().boundingRect()` bounds the editor's x/y.
keys:      editor, operands, popup, off screen, scroll, position

## F-019 — TON accepted a negative preset at download
2026-10-21 · area: isa · commit: b13cafe
symptom:   preset -5 downloaded and then raised major fault 0034h when running.
fix:       `validate` rejects literal presets outside 0..32767 in TON/TOF/RTO.
           A negative preset written at run time (MOV to .PRE) still gives 0034h, like the SLC.
keys:      preset, negative, TON, 0034, validation, download

## F-020 — With both lights green the cars never crashed
2026-10-21 · area: sims · commit: 44f066b
symptom:   `test_traffic_both_green_crashes` failed: 10 s of green both ways and no crash.
cause:     both cars had the same speed and a fixed offset; they never met at the crossing.
fix:       car B at 80 % speed and a closer start position (crashes in ~2.5 s).
prevent:   simulations with several moving objects must avoid moving in phase.
keys:      traffic, crash, cars, speed, phase

## F-021 — Simulations clipped in the left pane
2026-10-21 · area: ui · commit: 44f066b
symptom:   the silo motor and the crossing labels were cut off; crossing sign B on top of light A.
cause:     canvas minimum size (520/460 px) larger than the pane; fixed positions that overlapped.
fix:       320 px minimums (the drawing scales), initial pane 620 px, light A below the road.
keys:      clip, silo, traffic, layout, minimum size

## F-022 — Exercise tests: silo boxes "disappeared"
2026-10-21 · area: tests · commit: 5c71570
symptom:   exercise 8 counted only 1 full box after 40 s.
cause:     boxes are removed when they leave the conveyor; the test only saw those still on it.
fix:       `SiloModel.shipped` keeps the fill level of every box shipped.
keys:      silo, boxes, shipped, count, test

## F-023 — Start/stop test expected the motor off with Start still pressed
2026-10-21 · area: tests · commit: 5c71570
cause:     releasing Stop with Start still pressed restarts the motor (correct).
fix:       the test checks the motor while Stop is pressed.
keys:      stop, start, priority, test

## F-024 — Characters outside Latin-1 lost on save without warning (BUG-001)
2026-10-21 · area: rsl · commit: abcc82d
symptom:   emoji or "✓" in comments/symbols were saved as "?" silently.
cause:     silent `encode("latin-1", errors="replace")`.
fix:       `rsl.save` returns the replaced characters; the window shows a warning.
prevent:   tests/test_bugs.py::test_bug001, tests/e2e F05-E1.
keys:      latin-1, emoji, save, replace, rsl

## F-025 — SYMBOLS added to files that did not have it (BUG-002)
2026-10-21 · area: rsl · commit: abcc82d
cause:     `dumps` always wrote the section.
fix:       `Program.symbols_section` remembers whether the file had it.
prevent:   test_bug002 (byte-for-byte round trip).
keys:      symbols, round-trip, rsl

## F-026 — Addresses outside the data table accepted at download (BUG-003, BUG-004)
2026-10-21 · area: core · commit: abcc82d
symptom:   MOV 1 N7:256, XIC O:9/0, XIC F8:0/1 downloaded.
fix:       `Processor._range_problems` checks direct addresses at download (indirect ones in RUN);
           `isa._check` rejects bits of F elements.
prevent:   test_bug003, test_bug004.
keys:      out of range, download, validate, float, bit

## F-027 — Data table cells accepted invalid values (BUG-005, BUG-006)
2026-10-21 · area: ui · commit: abcc82d
symptom:   "2" in a bit set it to 1; 40000 or 12345h were truncated to 16 bits; 1e40 in F8 gave inf.
fix:       `TableModel.setData` accepts only 0/1 for bits, the signed range in decimal, 0..FFFF in
           binary/octal/hex and ±3.4e38 for floats.
prevent:   tests/test_bugs_ui.py.
keys:      data table, radix, range, edit cell

## F-028 — Download kept the previous program's data and outputs on (BUG-007, BUG-008)
2026-10-21 · area: core · commit: abcc82d
fix:       `download` clears the data table (keeps I/O) and timer marks; if it was in RUN it turns
           outputs off.
prevent:   test_bug007, test_bug008.
keys:      download, clear, outputs, RUN, counter

---

## Changes

## C-001 — Recon, architecture and design system
2026-10-21 · commit: 57ef05c · `replica/recon.md`, `architecture.md`, `design/`

## C-002 — First deliverable
2026-10-21 · commit: 5ead119 · engine, byte-identical .rsl round trip, I/O panel, read-only ladder

## C-003 — Ladder semantics per the manual
2026-10-21 · commit: bcf4791 · prescan, S:1/15, 15 pattern tests (seal-in, interlock, OSR)

## C-004 — Switches configured from symbols
2026-10-21 · commit: a833e13 · see F-007

## C-005 — Full instruction set
2026-10-21 · commit: 2be5b58 · 45 instructions in `plcyard/core/isa/`, 98 tests

## C-006 — Powered wires, live values, fonts, Clear fault
2026-10-21 · commit: 4fd6d29
- The processor keeps a trace (in/out) for every rung node: `Processor.trace`.
- Every wire in the layout carries a label (path, "in"/"out"); it is painted green when that
  segment conducts. The trace is only used if the PLC runs the same program that is shown.
- Timer/counter blocks show Accum live and the EN/TT/DN (or CU/CD/DN) bits.
- "Clear fault" button; I:1, I:3, O:2, O:4 words on the panel.

## C-007 — Ladder editor (S02, S03, S05, S07, S08, S09)
2026-10-21 · commit: b13cafe
- `plcyard/core/edit.py`: pure operations (insert, delete, move, branch, leg, XIC↔XIO, operands),
  with the same paths as the processor trace.
- Editable canvas: select with click and arrows, Del, Insert, F2/Enter, Ctrl+C/X/V,
  Ctrl+Z/Y (undo by program snapshots), context menu, drag instructions,
  double-click a rung for its comment.
- Instruction bar by family (click inserts, drag drops where you want).
- Inline operand editor with validation and address completion.
- Data table as a dock (Ctrl+T): files O..F, binary/octal/decimal/hex radix, editing.
- Unsaved changes (• in the title, asks on close); "edited, download to apply" when the editor
  no longer matches what was downloaded.

## C-008 — Silo (S11) and Traffic lights (S12) simulations
2026-10-21 · commit: 44f066b
- `sims/silo.py`: conveyor, boxes, hopper, proximity sensor I:1/3, level I:1/4, selector A/B/C,
  Run/Fill/Full lamps; spill if product falls with no box or a box overfills. Idle input word 0022h.
- `sims/traffic.py`: two directions (A O:2/0..2, B O:2/4..6), crossing signs O:2/3 and O:2/7,
  buttons I:1/0–1, waiting-car sensors I:1/2–3, two cars (can be parked); crash if both are in
  the crossing. On amber a car goes through if it is already near the line: without an all-red
  phase there are crashes.
- Simulations menu: I/O panel / Silo / Traffic lights, Reset simulation.

## C-009 — 10 original exercises with verified solutions (S14)
2026-10-21 · commit: 5c71570
- `labs/en/NN-*.md`: logic gates, start/stop, reversing, one button (OSR), blinker, batch counter
  with BCD display, comparators with thumbwheels, continuous silo, silo with selector, traffic
  light without crashes. Header with title, simulation, level and symbols.
- `labs/solutions/NN-*.rsl` (same name as the exercise): reference solution. `tests/test_labs.py` checks every written
  requirement (truth table, timing, no spills, no crashes…).
- Exercises dock (Ctrl+E): list, text, "Load simulation" and "New program for this exercise"
  (empty program with the symbols, so NC/pushbutton switches come configured).
- Solutions stay public: the project is open source and aimed at self-learners.

## C-010 — All app text in English
2026-10-21 · commit: 471af57
- Exercises: `labs/es` → `labs/en`, translated; header keys in English (title, simulation,
  level, symbols). Solutions: `labs/soluciones` → `labs/solutions`.
- Samples: `samples/start-stop.rsl` and `samples/timer-counter.rsl` (comments and symbols in English).
- "pulsador"/"botón" are still recognised in symbols for files written in Spanish.

## C-011 — Test pass: plan, e2e per flow and 8 bugs fixed
2026-10-21 · commit: abcc82d
- `docs/testing/test-plan.md` (28 cases), `docs/testing/bugs.md` (S2: 4, S3: 4, all fixed).
- `tests/e2e/test_flows.py`: F01–F08 with pytest-qt driving the window; scans are advanced by the
  test (`plc.tick`), not the clock.

## C-012 — "Check my program": automatic checking of exercises
2026-10-21 · commit: 81d659e
- `plcyard/grader.py`: each written requirement of the 10 exercises is a check that runs the
  editor's program against a fresh simulation, faster than real time (< 0.5 s). Download or run
  faults are reported, not raised.
- Exercises dock: "Check my program" button and a ✔/✘ list with the reason. It does not touch
  the PLC on screen.
- Checks that depend on something starting (stop, spill, shutdown) fail with "never started"
  instead of passing vacuously: an empty program scores 0.
- Tests: `tests/test_grader.py` (solutions pass everything, empty gets no credit), e2e F09.

## C-013 — Repository in English; open-source direction
2026-10-21 · commit: 69276ca
- `BITACORA.md` → `DEVLOG.md`, translated. All repository text is now English.
- Direction: open source for anyone learning on their own; no classroom/teacher features.
  More UI languages may come later; English only for now.

## C-014 — Name PLCYard, GPL-3.0, icon
2026-10-21 · commit: 3911c55
- Package `plcsim` → `plcyard`; window title and app name "PLCYard". Paths in this log updated.
  "plc-sim" dropped: too close to Siemens S7-PLCSIM.
- `LICENSE` GPL-3.0; `pyproject.toml` with project metadata and the `plcyard` GUI script.
- Draft icon `plcyard/ui/assets/icon.svg` (NO contact with an energized dot), set as window icon.
- `replica/brand.md` / `brand.json`; diff images derived from the original's screenshots untracked.

## C-015 — README, website page, launch plan
2026-10-21 · commit: 4ac06e1
- `README.md` (GitHub landing), `site/index.html` + `site/img/` (static page for juliordz.com,
  light/dark), `docs/screenshots/` taken offscreen from the real app.
- `replica/launch/`: landing copy, pricing (free, GPL), launch plan. No store listing (desktop app
  from GitHub). No testimonials or counts.

## C-016 — Public repository
2026-10-21 · commit: 7ffdfef
- Test plan and bug reports moved to `docs/testing/` (they ship publicly); `replica/` stays in the
  private development repository only.
- Public repository juliordzcer/plcyard created from a clean export (no `replica/`, no history).

## C-017 — Exercises and examples inside the package; bundled files protected
2026-10-21 · commit: 8bd2efb
- `labs/` → `plcyard/data/labs`, `samples/` → `plcyard/data/samples` (`labs.DATA`, `labs.SAMPLES`);
  `package-data` includes them, so a wheel install has the exercises (checked with a built wheel).
- File → Open example lists the bundled samples.
- Save on a bundled file (example or exercise solution) opens Save as instead: a solution had been
  overwritten with an empty program by accident.
- GitHub issue templates: bug, exercise idea.

## C-018 — Phase 1: controller profiles and .plcy projects
2026-10-21 · commit: 251b25b
- `core/profiles/`: `Profile` (memory, instruction set, download check, prescan, status bits,
  faults, I/O image) and `slc500` with the code that was in the processor, moved without
  behaviour changes. `Processor(profile)` is the shared scan engine; downloading a program of
  another profile switches the controller (a rejected download does not).
- `Program.profile` (default `slc500`). `Processor.reset_timers_counters`, `outputs_off` public.
- `formats/plcy.py`: JSON project, version 1; ladder rungs as .rsl token text; unknown profile,
  newer version, unsupported language and broken rungs are reported. `formats.load/save` pick the
  format by extension; Save as offers .plcy (default) or .rsl; .rsl refuses non-SLC programs.
- Instruction bar shows the instruction set of the program's controller.
- Tests: `tests/test_profiles.py` (toy tag controller on the same engine: runs, check blocks
  download, memory error → fault with the profile's code, switch back to SLC), `tests/test_plcy.py`
  (every bundled program rsl → plcy → rsl identical and downloadable), e2e F05-H2/N2.
keys:      profile, controller, plcy, project, json, Logix, S7

## F-029 — Test suite grew from 2 to 7 minutes
2026-10-21 · area: tests · commit: 9b996d1
symptom:   UI test setup took 4 s alone and ~20 s late in the full run; growing with test order.
cause:     fixtures called `deleteLater()` then `processEvents()`, which does not run deferred
           deletes: every MainWindow stayed alive, and each `theme.apply` restyled all of them.
fix:       `QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)` after `deleteLater()`.
prevent:   `pytest --durations=5`; full suite should stay under a minute.
keys:      slow, setup, deleteLater, DeferredDelete, leak, theme, pytest-qt

## C-019 — Phase 2a/2b: editor per controller, Logix profile, tag list
2026-10-21 · commit: 9b996d1
- `isa.Spec.shape/letter` (contact, contact_nc, coil, small, block): the ladder draws by shape, so
  any profile can reuse the glyphs. `Profile.validate/normalize/kinds/is_output/live/io_name/io_image`;
  `core/edit.py`, `ui/ladder_layout.py`, `ui/ladder_view.py` take the program's profile.
- `core/profiles/logix/`: `TagTable` (BOOL, INT, DINT, REAL, TIMER, COUNTER; `Tag.Member`,
  `Tag.5` bits, `Local:<slot>:I/O.Data` module tags, `S:FS`, `S:V`; names case-insensitive),
  instructions XIC XIO OTE OTL OTU ONS OSR OSF TON TOF RTO CTU CTD RES EQU NEQ LES LEQ GRT GEQ LIM
  ADD SUB MUL DIV MOV CLR SCP NOP. Timers in ms; integer math wraps and sets S:V; DIV by 0 stores
  the extreme value and sets S:V (minor fault on a real controller, no stop); negative timer
  preset → major fault 0422h. JSR/routines not yet.
- `Program.tags` (saved in .plcy). File → New for controller. Tags dock (add, rename, retype,
  description, live values, live edit). Simulations and the I/O panel name points per controller
  (`Local:1:I.Data.0`); NC/pushbutton wiring reads descriptions of those names.
- Long operands widen contacts instead of being cut; Logix TON/CTU show the live Accum in the
  Accum operand row.
- Tests: `tests/test_logix.py` (23), e2e F10 (new Logix program from scratch to a lit lamp,
  unknown tag, back to SLC).
keys:      Logix, Studio 5000, tags, TIMER, ms, Local:1:I.Data

## C-020 — Phase 2c: S7-1200/1500 profile
2026-10-21 · commit: ab4e60a
- `core/profiles/s7/`: `S7Memory` (areas I, Q, M of 128 bytes, big-endian words like the real CPU,
  `%I0.0` / `%MW10` / `%MD20`, symbolic tags with or without an address, `"Quoted"` names,
  IEC_TIMER/IEC_COUNTER instances, `FirstScan`), time literals `T#1m30s`, `T#500ms`.
- Instructions: contacts and coils (S/R), P/N edge contacts, TON/TOF/TP, CTU (R)/CTD (LD),
  RESET_TIMER, CMP== <> < <= > >=, IN_RANGE, ADD SUB MUL DIV MOD, MOVE, NORM_X, SCALE_X. Boxes return
  ENO or Q so a coil can follow them; overflow or divide by zero gives ENO = 0 (no stop).
- Rack: input slots 1/3 = %IB0-1/%IB2-3 (channel 8 = %I1.0), thumbwheels %IW4; outputs %QB0-3, BCD
  display %QW4.
- Tag list is per profile (`Profile.tag_types/tag_fields/check_tags/tag_value`): S7 adds an Address
  column; bad addresses are refused with the reason. Instruction bar glyphs come from the shape
  (S7 coils show S and R). Block values use the full width except next to status pins.
- Tests: `tests/test_s7.py` (26), e2e F11.
keys:      S7, TIA Portal, Siemens, %I0.0, IEC_TIMER, ENO, big endian

## C-021 — Phase 3: PID, analog I/O, tank simulation, exercises 11-12
2026-10-21 · commit: 5714c17
- `core/pid.py`: CV = Kc·(e + 1/Ti·∫e − Td·dPV/dt), seconds, derivative on PV (no setpoint kick),
  conditional-integration anti-windup, bumpless manual, reverse action.
- Logix: `PID` tag type (SP, PV, CV, KP, TI, TD, MAXO, MINO, SO, MO, CA) and `PID` instruction;
  analog modules `Local:7:I.Ch0Data/Ch1Data`, `Local:8:O.Ch0Data` in volts. Struct tags accept start
  values for members (`{"type": "PID", "value": {"KP": 4}}`).
- S7: `PID_Compact` instance (Gain, Ti, Td, limits, ManualEnable/ManualValue, InvertControl) and
  box; analog `%IW64/%IW66`, `%QW64` raw 0-27648.
- SLC: analog `I:7` (level) and `I:6` (knob) 0-16383, `O:7` (valve) 0-32767; no PID yet.
- `sims/tank.py`: level 0-100 %, pump (on/off) and proportional inlet valve, 1 s pipe dead time,
  outlet as disturbance (√level), high/low switches, setpoint knob, overflow event, 2-minute trend.
  `ui/tank_view.py`: drawing, sliders, trend chart (setpoint dashed, level, valve).
- Profiles name analog channels (`Profile.analog_name`); devices with `analog_inputs` /
  `set_analog_outputs` are wired by the profile in the I/O scan.
- Exercises: 11 on/off with hysteresis (SLC), 12 PID tuning (Logix, `controller:` header in the
  exercise file, solution as .plcy). Checks: band 35-65 %, no chattering, ±2 % in 60 s, overshoot
  ≤ 5 %, disturbance rejection, new setpoint, no overflow.
- Blocks widen for long operands; live rows for PID blocks.
keys:      PID, PID_Compact, analog, tank, level, trend, hysteresis, Ch0Data, %IW64
