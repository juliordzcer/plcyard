<p align="center"><img src="plcyard/ui/assets/icon.svg" width="72" alt=""></p>

<h1 align="center">PLCYard</h1>

<p align="center">A free, open-source PLC trainer. Write ladder logic, run it on simulated machines,
and find out which requirement your program misses, without a teacher.</p>

![PLCYard running a start/stop program: the motor lamp is on and the energized path is green](docs/screenshots/run-light.png)

## Why

Learning PLCs on your own is hard for two reasons: you need a PLC to practise on, and nobody tells
you whether your program is right until something on a real machine goes wrong. PLCYard gives you
both: a simulated SLC 500-style controller with machines to drive, and exercises that check your
program requirement by requirement.

It runs natively on Linux, macOS and Windows, stays sharp on high-resolution screens, and needs
no licence key.

## How it works

1. **Write** a program in the ladder editor: click an instruction, type its address (`I:1/0`,
   `T4:0`, `N7:5`), or drag it where you want.
2. **Run** it: Download, switch to RUN, and flip the switches. Energized paths turn green, timers
   and counters count live, the data table shows every value.
3. **Check** it: open an exercise and press *Check my program*. Each requirement shows ✔ or ✘ with
   the reason.

![Exercise checker listing requirements met and failed](docs/screenshots/check.png)

## Features

- **Check my program**: 10 exercises, from logic gates to a traffic light without crashes, each
  with automatic checks of every written requirement. Runs faster than real time.
- **Simulations**: I/O panel (16 inputs, 16 outputs per card, thumbwheels and a 7-segment BCD
  display), a filling line (silo) and a road crossing (traffic lights).
- **45 instructions** in the SLC 500 style: bits, latches, one-shot, timers (TON, TOF, RTO),
  counters, compare, math, move/logical, BCD, bit shift, sequencers, subroutines.
- **Real scan behaviour**: prescan on entering RUN, first-pass bit S:1/15, outputs off in PGM,
  rung-order effects, major faults with codes.
- **Mistakes caught before you run**: wrong address types, addresses outside the data table,
  unset operands, all with a suggestion.
- **Switch types** from your symbols: write "Stop (NC)" or "Jog (PB)" and the switch is wired that
  way.
- **.rsl files**: open and save the plain-text ladder format used by SLC 500 trainers;
  unchanged programs save byte for byte.
- Light and dark themes, keyboard shortcuts for everything, undo/redo.

| | |
| --- | --- |
| ![Silo filling line](docs/screenshots/silo.png) | ![Traffic light crossing](docs/screenshots/traffic.png) |

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

Open a sample with `plcyard samples/start-stop.rsl`, or press **Ctrl+E** for the exercises.

## Keyboard

| key | does |
| --- | --- |
| Ctrl+D / Ctrl+R / Ctrl+P | download / RUN / program mode |
| F10 | single scan (STEP mode) |
| Insert, Del, F2 | new rung, delete, edit operands |
| Ctrl+T / Ctrl+E | data table / exercises |

## Roadmap

- More simulations (door, elevator, batch mixing, bottle line) and exercises.
- Modern controller profiles (Logix-style tags, S7-1200/1500) with PID and IEC blocks.
- Function block diagram and structured text (ST / SCL), next to ladder.
- A wiki. Full list in [TODO.md](TODO.md).
- More UI languages.

Contributions are welcome: open an issue first for anything large.

## Develop

```bash
.venv/bin/pip install pytest pytest-qt
.venv/bin/python -m pytest              # 216 tests, about 2 minutes
```

Every fixed bug and design decision is in [DEVLOG.md](DEVLOG.md).

## Licence

GPL-3.0-or-later, see [LICENSE](LICENSE). Fonts: Inter and JetBrains Mono, SIL Open Font
Licence (`plcyard/ui/assets/fonts`).

PLCYard is an independent project, not affiliated with or endorsed by Rockwell Automation,
Siemens or any PLC vendor. Product names are used only to describe compatibility.
