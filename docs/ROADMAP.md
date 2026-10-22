# Roadmap plan

How the items in [TODO.md](../TODO.md) get built, in order. Each phase ships on its own, keeps the
current SLC 500 ladder trainer working, and ends with the full test suite green.

## Phase 0 — Release 0.1 (small) — done except PyPI, icon, site, trademark

- Ship `labs/` and `samples/` inside the package (`plcyard/data/`), load them with
  `importlib.resources`; a non-editable install and PyPI then work.
- Exercise solutions open read-only: Save on a file under `labs/solutions` asks for a new name.
- GitHub release v0.1.0, issue templates, final icon, `site/` on juliordz.com, trademark screening.

## Phase 1 — Controller profiles (foundation, M) — done

Today the processor, the data table (`N7:0`, `T4:0`) and the instruction set are all SLC 500.
Split what is shared from what belongs to a controller family:

| shared (scan engine) | per profile |
| --- | --- |
| input scan → execute → output scan, modes, faults, prescan, trace for animation | memory model, address/tag syntax, instruction set, file format |

- `plcyard/core/profiles/`: `slc500` (today's code, moved, no behaviour change),
  later `logix` and `s7`.
- Memory interface: `read(ref)`, `write(ref, value)`, `bit(ref)`, element types. SLC keeps the
  file data table; Logix and S7 get a **tag table** (named variables with a type).
- The instruction registry (`@instruction`) gets a `profiles=` field, so the instruction bar and
  validation show only what the selected controller has.
- Project format `.plcy` (JSON): profile, tags, programs in any language, symbols, exercise id.
  `.rsl` stays as import/export for SLC ladder.
- Gate: all 216 tests pass unchanged with `slc500`.
- Done as: one instruction dict per profile (`Profile.specs`) instead of a `profiles=` field, since
  the same mnemonic (TON) means different things in SLC, Logix and S7. A toy tag-based profile in
  `tests/test_profiles.py` proves the engine has no SLC assumptions left.
- Carried to Phase 2: the ladder editor (`ui/ladder_view.py`, `core/edit.py`) still looks up
  `isa.SPECS`; it takes the program's profile when the second real profile lands.

## Phase 2 — Modern controllers in ladder (L) — done

- **Logix-style profile** (Studio 5000): tags `Start`, `Motor`, `Tank.Level`; types BOOL, DINT,
  REAL, TIMER, COUNTER, user structures later. Instructions: XIC/XIO/OTE/OTL/OTU, ONS/OSR/OSF,
  TON/TOF/RTO (preset in ms), CTU/CTD/RES, MOV/CPT, compare, math, SCP (scale), JSR.
- **S7-style profile** (TIA Portal): `%I0.0`, `%Q0.0`, `%MW10` plus symbolic tags; IEC timers and
  counters as instances (TON, TOF, TP, CTU, CTD, CTUD), R_TRIG/F_TRIG, NORM_X/SCALE_X, MOVE.
- Tag editor dock (replaces the data table for these profiles), with live values and forcing.
- The existing simulations get I/O maps per profile, so every machine works with every controller.
- Done: Logix (tags, ms timers, DINT math, Local:<slot>:I/O.Data) and S7 (%I/%Q/%M, PLC tags,
  IEC_TIMER/IEC_COUNTER instances, boxes passing ENO/Q). Left for later: forcing from the tag list,
  arrays and user structures, routines (JSR) on Logix, function blocks/DBs on S7.

## Phase 3 — PID and analog process (M) — done

- Analog I/O in the scan (raw counts → engineering units with SCP / NORM_X+SCALE_X).
- PID block per profile: Logix `PIDE`-like (simplified), S7 `PID_Compact`-like; Kp, Ti, Td,
  setpoint, output limits, manual/auto, anti-windup.
- Process simulation: tank level with inlet pump and outlet valve (first-order + delay),
  disturbance button.
- Trend chart: setpoint, process value, output over time.
- Exercises: on/off control with hysteresis, then PID tuning with checks on overshoot and
  settling time.
- Done as: shared `core/pid.py` (dependent form, derivative on PV, anti-windup, bumpless manual),
  Logix `PID` (PID tag) and S7 `PID_Compact` (instance), SLC without PID for now (on/off with
  analog compares). Exercises 11 (on/off, SLC) and 12 (PID, Logix).

## Phase 4 — Structured text (L) — done

- One language core: the IEC 61131-3 ST subset shared by Allen-Bradley **ST** and Siemens **SCL**:
  assignments, IF/ELSIF/CASE, FOR/WHILE/REPEAT, expressions, function and function-block calls
  (TON, CTU, PID…), comments.
- Hand-written parser (no new dependencies) → AST → interpreter run once per scan; errors with
  line and column; runaway-loop watchdog raises a major fault.
- Dialect switches per profile for the small differences (SCL `#local` and `"Tag"` quoting,
  `:=` everywhere, AB tag names).
- Editor: syntax highlighting, error markers, live values next to variables while running.
- Done as: `core/st/` (lexer, parser, checks, interpreter, watchdog 100 000 loop iterations per
  scan), `Instance.BLOCK(IN := …, Q => …)` calls (TIA syntax) mapped to each profile's executors,
  `ui/st_editor.py` (colours, line numbers, problems as you type, watch list). SLC 500 has no ST, as
  on the real controller. Not yet: Studio 5000's own TONR/FBD_TIMER, user functions, arrays.

## Phase 4b — Several routines, data types, forcing (L) — done

- Logix: routines in the MainProgram called with `JSR` (ladder and `JSR(Name);` in ST), `RET`;
  user-defined types and one-dimensional arrays (`Pump.Speed`, `Recipe[Step]`, indexes by tag in
  ladder, by expression in ST); `PID` with Studio 5000's seven operands (tieback, cascade master,
  inhold).
- S7: functions (FC) and function blocks (FB) with an interface (Input, Output, InOut, Static,
  Temp), called with a `CALL` box (`Start:=Button`, `Run=>Lamp`) or `"Block"(…)` in SCL; FB
  instances are data blocks (tags of the FB's type), multi-instances inside FBs, `#local` and
  `"global"` names; PLC data types and arrays (`Array[1..5] of Int`); `Count.%X3`.
- SLC 500: `PID` with a 23-word control block in an N file (RSLogix 500 layout), exercise 13 PID on
  S7 with `PID_Compact`.
- Forcing I/O (all three controllers) from the tag list or the ladder, "I/O FORCED" on the panel.
- UI laid out like the controller's software: Controller Organizer / Project tree / Project on the
  left, every routine or data type in its own tab (several open at once, any language), the
  block interface above its code as in TIA Portal, the tag list as a tree with members.
- Examples: traffic lights (SLC; Logix with an ST sequence and a ladder routine), silo (SLC; S7 FB
  and instance DB), two motor starters (S7 FB instances), recipes (Logix UDT array), SLC PID tank.

## Phase 5 — Function block diagram (L)

- Model: blocks (instances of the same function blocks ST uses), pins, wires, execution order
  (left to right, top to bottom, editable).
- Editor canvas reusing the ladder canvas pieces: drag blocks from the bar, draw wires, live values
  on pins, energized BOOL wires in green.
- One block library for LD, ST and FBD, so a TON behaves identically in all three.

## Phase 6 — Exercises in three languages (M)

- The checker already talks only to the simulation's inputs and outputs, so it works for any
  language once `grader.Rig` loads a `.plcy` program.
- Each exercise gets reference solutions in LD, ST and FBD; tests prove all three pass the same
  checks. A "compare languages" view shows them side by side.

## Phase 7 — Wiki (M, can run in parallel from Phase 1)

- `docs/` with MkDocs, published on GitHub Pages (versioned with the code; the GitHub Wiki
  cannot be reviewed in pull requests).
- Pages: getting started, how a scan works, each simulation, writing an exercise and its checks,
  adding a simulation, contributing.
- Instruction reference **generated** from the instruction registry (title, operands, family) plus
  a hand-written example per instruction, so it never drifts from the code.

## Later

- UI languages (Qt translations; exercises as `labs/<lang>/`).
- More simulations: door, elevator, batch mixing, bottle line.
- Real hardware: an Arduino and/or ESP32 as remote I/O over USB serial (later Wi-Fi), so a program
  running in PLCYard reads real switches and drives real LEDs/relays. A small firmware sketch
  speaks a line protocol (input word in, output word out each scan), and an `IODevice` on the PC
  side replaces the simulation. Watchdog: outputs off when the link drops.

## Order and size

| phase | size | depends on |
| --- | --- | --- |
| 0 release | S | — |
| 1 profiles | M | 0 |
| 7 wiki | M | 1 (for the generated reference) |
| 2 modern ladder | L | 1 |
| 3 PID | M | 2 |
| 4 ST | L | 2 |
| 5 FBD | L | 4 (shared block library) |
| 6 exercises ×3 | M | 4, 5 |

Rule for every phase: failing test first for each behaviour, behaviour checked against the vendor
manuals (Rockwell 1756-RM003 for Logix, Siemens S7-1200/1500 system manual), an entry in
`DEVLOG.md`, and no change to how existing `.rsl` programs run.
