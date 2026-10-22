# Writing exercises

An exercise has three parts: its text, its checks and its reference solutions.

## 1. The text

`plcyard/data/labs/en/NN-short-name.md`, a Markdown file with a header:

```markdown
---
title: Garage door with a safety photo-eye
simulation: garage
level: 3
symbols:
- %I0.0 Open (PB)
- %I0.2 Stop (NC, PB)
---
# 15. Garage door with a safety photo-eye

**Goal:** …

## Inputs and outputs (Garage door simulation)
| Address | Device |
…

## Requirements
1. …
```

- `simulation` is a key of the [simulation reference](reference/simulations.md).
- `level` is 1 to 3.
- `symbols` name the inputs and wire the switches: `(NC)` makes a normally closed switch, `(PB)`
  a pushbutton that springs back.
- Write the requirements as a numbered list. Each one becomes one check.

## 2. The checks

In `plcyard/grader.py`, a function per exercise, registered in `CHECKS` under its number:

```python
def _15(new, out):
    r = new()                       # a fresh PLC running the program, wired to the simulation
    r.ms(100)
    r.sim.open_pressed = True       # act on the machine
    r.ms(100)
    r.sim.open_pressed = False
    r.ms(12000)
    opened = r.sim.position >= 100.0
    out("Open runs the door up and stops at the open limit", opened, f"door at {r.sim.position:.0f} %")
```

`r.ms(n)` runs n milliseconds of scans (faster than real time). `out(requirement, passed, reason)`
reports one line; the reason is shown when it fails. Make each check fail for an empty program.

## 3. The solutions

`plcyard/data/labs/solutions/NN-short-name.plcy` (ladder), `.st.plcy` and `.fbd.plcy`. The tests
grade all three and expect every check to pass; **Compare languages** shows them.

Run the tests (see [Contributing](contributing.md)).
