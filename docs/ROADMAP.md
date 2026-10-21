# Roadmap plan

How the items in [TODO.md](../TODO.md) get built, in order. Each phase ships on its own, keeps the
current SLC 500 ladder trainer working, and ends with the full test suite green.

## Phase 0 — Release 0.1 (small)

- Ship `labs/` and `samples/` inside the package (`plcyard/data/`), load them with
  `importlib.resources`; a non-editable install and PyPI then work.
- Exercise solutions open read-only: Save on a file under `labs/solutions` asks for a new name.
- GitHub release v0.1.0, issue templates, final icon, `site/` on juliordz.com, trademark screening.

## Phase 1 — Controller profiles (foundation, M)

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

## Phase 2 — Modern controllers in ladder (L)

- **Logix-style profile** (Studio 5000): tags `Start`, `Motor`, `Tank.Level`; types BOOL, DINT,
  REAL, TIMER, COUNTER, user structures later. Instructions: XIC/XIO/OTE/OTL/OTU, ONS/OSR/OSF,
  TON/TOF/RTO (preset in ms), CTU/CTD/RES, MOV/CPT, compare, math, SCP (scale), JSR.
- **S7-style profile** (TIA Portal): `%I0.0`, `%Q0.0`, `%MW10` plus symbolic tags; IEC timers and
  counters as instances (TON, TOF, TP, CTU, CTD, CTUD), R_TRIG/F_TRIG, NORM_X/SCALE_X, MOVE.
- Tag editor dock (replaces the data table for these profiles), with live values and forcing.
- The existing simulations get I/O maps per profile, so every machine works with every controller.

## Phase 3 — PID and analog process (M)

- Analog I/O in the scan (raw counts → engineering units with SCP / NORM_X+SCALE_X).
- PID block per profile: Logix `PIDE`-like (simplified), S7 `PID_Compact`-like; Kp, Ti, Td,
  setpoint, output limits, manual/auto, anti-windup.
- Process simulation: tank level with inlet pump and outlet valve (first-order + delay),
  disturbance button.
- Trend chart: setpoint, process value, output over time.
- Exercises: on/off control with hysteresis, then PID tuning with checks on overshoot and
  settling time.

## Phase 4 — Structured text (L)

- One language core: the IEC 61131-3 ST subset shared by Allen-Bradley **ST** and Siemens **SCL**:
  assignments, IF/ELSIF/CASE, FOR/WHILE/REPEAT, expressions, function and function-block calls
  (TON, CTU, PID…), comments.
- Hand-written parser (no new dependencies) → AST → interpreter run once per scan; errors with
  line and column; runaway-loop watchdog raises a major fault.
- Dialect switches per profile for the small differences (SCL `#local` and `"Tag"` quoting,
  `:=` everywhere, AB tag names).
- Editor: syntax highlighting, error markers, live values next to variables while running.

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
