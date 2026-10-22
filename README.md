<p align="center"><img src="plcyard/ui/assets/icon.svg" width="72" alt=""></p>

<h1 align="center">PLCYard</h1>

<p align="center">A free, open-source PLC trainer. Write ladder logic, run it on simulated machines,
and find out which requirement your program misses, without a teacher.</p>

![PLCYard running a start/stop program: the motor lamp is on and the energized path is green](docs/screenshots/run-light.png)

## Why

Learning PLCs on your own is hard for two reasons: you need a PLC to practise on, and nobody tells
you whether your program is right until something on a real machine goes wrong. PLCYard gives you
both: a simulated PLC with machines to drive, and exercises that check your program requirement by
requirement.

It runs natively on Linux, macOS and Windows, stays sharp on high-resolution screens, and needs
no licence key.

## How it works

1. **Write** a program in ladder, structured text or function block diagram: click an instruction, type its operand (`%I0.0`,
   `Motor`, `Delay`), or drag a switch or lamp from the simulation onto the rung.
2. **Run** it: Download, switch to RUN, and flip the switches. Energized paths turn green, timers
   and counters count live, the tag list shows every value.
3. **Check** it: open an exercise and press *Check my program*. Each requirement shows ✔ or ✘ with
   the reason.

![Exercise checker listing requirements met and failed](docs/screenshots/check.png)

## Features

- **One PLC, two notations**: pick in Tools → Options how instructions and addresses are written:
  mnemonics (`XIC`, `OTE`, `MOV`, timer `.PRE` `.ACC` `.DN`, I/O as `Local:1:I.Data.0`) or IEC
  symbols (NO/NC contacts, `MOVE`, timer `.PT` `.ET` `.Q`, I/O as `%I0.0`). The program is the same
  in both, so you can switch at any time and read either style of documentation.
- **Check my program**: 13 exercises, from logic gates to tuning a PID level loop, each with
  automatic checks of every written requirement. Runs faster than real time. **Compare
  languages** shows each reference solution in ladder, structured text and function block diagram.
- **Simulations**: I/O panel (16 inputs, 16 outputs per card, thumbwheels and a 7-segment BCD
  display), a filling line (silo), a road crossing (traffic lights), an analog **tank level**
  process with a live trend, **two tanks in series** (cascade control), a **garage door** with
  limit switches and a safety photo-eye, and a **batch mixer** with ingredients, mixer, heater and
  temperature. Every label with an address can be dragged onto the program.
- **Tags, data types and arrays**: BOOL, INT, DINT, REAL, TIME, TIMER, COUNTER, CONTROL, PID, your
  own data types and arrays (`Recipe[Step].FillTime`); marker and I/O addresses (`%M10.0`, `%MW20`).
- **Instructions**: contacts and coils, set/reset, one shots and edge contacts, TON/TOF/RTO/TP,
  CTU/CTD, compare and range, math, move and masked move, bitwise logic, BCD, scaling, bit shift,
  sequencers, array copy and fill, PID. Every box passes power on (a coil can follow a timer).
- **Several routines per program, in any language**: routines called with `JSR`, functions and
  function blocks with their interface (inputs, outputs, static data) called with a `CALL` box or
  from structured text; each function block instance keeps its own data.
- **Function block diagram**: logic, flip-flops, edges, timers, counters, compare, math, select,
  scale and PID blocks; wire pin to pin, or put a tag or I/O point on a pin (drag it from the
  simulation). Live values on every pin.
- **Structured text** next to ladder: IF, CASE, FOR, WHILE, REPEAT, math and conversion functions,
  timer, counter and PID blocks called on their tag (`Delay.TON(IN := Start, PT := T#2s)`). Syntax
  colours, line numbers, errors as you type and a watch list with live values.
- **Laid out like PLC software**: project tree on the left, each routine or data type in its own
  tab, an online bar (Go Online, Upload, Download, forces, edits, status LEDs) that folds away.
- **Forcing** I/O points from the tag list or the ladder, with the FORCE light on.
- **Examples**: traffic lights (one routine, or a ladder main calling a structured-text sequence),
  silo filling line (plain ladder, or a function block), motor starters as function block
  instances, recipes in an array of a data type, PID tank loops.
- **Real scan behaviour**: prescan on entering RUN, first scan bit, outputs off in program mode,
  rung-order effects, major faults with codes.
- **Mistakes caught before you run**: unknown tags, wrong types, unset operands, all with a
  suggestion.
- **Switch types** from your descriptions: write "Stop (NC)" or "Jog (PB)" and the switch is wired
  that way.
- **Projects (.plcy)**: readable JSON. Older data-table ladder files (.rsl) open and are converted.
- Light and dark themes, keyboard shortcuts for everything, undo/redo per routine.

| | |
| --- | --- |
| ![Silo filling line](docs/screenshots/silo.png) | ![Traffic light crossing](docs/screenshots/traffic.png) |
| ![PID level loop on the tank with its trend](docs/screenshots/tank-pid.png) | ![The same loop in structured text with live values](docs/screenshots/st-scl.png) |

## Install

Python 3.11 or newer.

```bash
git clone https://github.com/juliordzcer/plcyard.git
cd plcyard
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/plcyard                      # or: .venv/bin/python -m plcyard
```

On Windows use `.venv\Scripts\pip` and `.venv\Scripts\plcyard`.

Open a sample from **File → Open example**, or press **Ctrl+E** for the exercises.

## Keyboard

| key | does |
| --- | --- |
| Ctrl+D / Ctrl+R / Ctrl+P | download / RUN / program mode |
| F10 | single scan (STEP mode) |
| Insert, Del, F2 | new rung, delete, edit operands |
| Ctrl+T / Ctrl+E | tag list / exercises |
| Ctrl+K | go online |

## Roadmap

- More simulations (door, elevator, batch mixing, bottle line) and exercises.
- A wiki. Full list in [TODO.md](TODO.md).
- More UI languages.

Contributions are welcome: open an issue first for anything large.

## Develop

```bash
.venv/bin/pip install pytest pytest-qt
.venv/bin/python -m pytest              # about 290 tests, under a minute
```

Every fixed bug and design decision is in [DEVLOG.md](DEVLOG.md).

## Licence

GPL-3.0-or-later, see [LICENSE](LICENSE). Fonts: Inter and JetBrains Mono, SIL Open Font
Licence (`plcyard/ui/assets/fonts`).

PLCYard is an independent project, not affiliated with or endorsed by any PLC vendor.
