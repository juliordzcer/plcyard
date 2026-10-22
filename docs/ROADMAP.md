# Roadmap plan

How the items in [TODO.md](../TODO.md) get built, in order. Each phase ships on its own and ends
with the full test suite green.

## Phase 0 — Release 0.1 (small) — done except PyPI, icon, site, trademark

- Ship `labs/` and `samples/` inside the package (`plcyard/data/`), load them with
  `importlib.resources`; a non-editable install and PyPI then work.
- Exercise solutions open read-only: Save on a file under `labs/solutions` asks for a new name.
- GitHub release v0.1.0, issue templates, final icon, `site/` on juliordz.com, trademark screening.

## Phases 1-4 — One PLC, ladder and structured text — done

- Scan engine separate from the PLC it runs (`core/processor.py` + `core/plc/`): input scan →
  execute → output scan, modes, faults, prescan, trace for the live display.
- One PLC with named tags and typed memory: BOOL, SINT, INT, DINT, REAL, TIME, TIMER, COUNTER,
  CONTROL, PID, user data types, one-dimensional arrays, I/O and marker addresses (%I, %Q, %M).
- Two notations over the same program (Tools → Options): mnemonics (XIC, OTE, MOV; timer .PRE
  .ACC .DN; I/O Local:1:I.Data.0) and IEC symbols (NO/NC contacts, MOVE; timer .PT .ET .Q; %I0.0).
  Files keep one canonical form; the notation only changes display and input.
- Instruction set: bits, one shots, edge contacts, timers (boxes pass Q), counters, compare, math
  with overflow, move, logic, BCD, scaling, bit shift, sequencers, array copy/fill, PID, routines
  (JSR/RET), functions and function blocks (CALL) with interfaces and instances.
- PID and analog I/O (raw 0-27648), tank simulation with trend.
- Structured text: parser, checks with line numbers, interpreter with watchdog, block calls on
  their tag, routine and block calls, array indexes by expression.
- UI: project tree, routines and data types in tabs, block interface above its code, tag list as
  a tree with forcing, online bar (Go Online, Upload, Download, forces, edits, LEDs), drag I/O from
  the simulations onto the ladder, examples and 13 exercises.
- Older programs (data-table .rsl files and the earlier tag and IEC project styles) convert on
  load (`formats/convert.py`): N7:5 → Values[5], T4:0 → Timers[0], timer presets to ms.

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
| 1-4 one PLC, LD, ST | L | 0 |
| 7 wiki | M | 1 (for the generated reference) |
| 5 FBD | L | 4 (shared block library) |
| 6 exercises ×3 | M | 4, 5 |

Rule for every phase: failing test first for each behaviour, behaviour checked against PLC
instruction set manuals and IEC 61131-3, and an entry in `DEVLOG.md`.
