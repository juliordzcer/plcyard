# Getting started

## Install

Python 3.11 or newer.

```bash
git clone https://github.com/juliordzcer/plcyard.git
cd plcyard
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/plcyard
```

On Windows use `.venv\Scripts\pip` and `.venv\Scripts\plcyard`.

## Your first program: start/stop

1. **File → New**. The project tree on the left shows the tags, the program with its `MainRoutine`
   and the data types. The routine opens in a tab.
2. Choose **Simulations → I/O panel**. Its first card has switches `%I0.0`…, its output card lamps
   `%Q0.0`….
3. In the ladder, add a rung (Insert). Add a normally open contact on `%I0.0` (Start), a normally
   closed contact on `%I0.1` (Stop) and a coil on `%Q0.0` (Motor). Put a branch around Start with a
   contact on `%Q0.0` to seal it in. You can type the addresses or drag a switch or lamp from the
   simulation onto the instruction.
4. **Download** (Ctrl+D), then **RUN** (Ctrl+R). Flip Start: the lamp lights and the energized path
   turns green. Press Stop: it goes out.

## Exercises

Press **Ctrl+E**. Each exercise names its simulation, lists its inputs and outputs, and has a
**Check my program** button that runs your program faster than real time and marks every
requirement ✔ or ✘ with the reason. **Compare languages** shows the reference solution in LD, ST and
FBD side by side, once you want to see it.

## Examples

**File → Open example** opens a working program for every simulation. Run it, then change it.

## Keyboard

| Key | Does |
| --- | --- |
| Ctrl+D / Ctrl+R / Ctrl+P | Download / RUN / program mode |
| F10 | Single scan (step mode) |
| Insert, Del, F2 | New rung, delete, edit operands |
| Ctrl+T / Ctrl+E | Tag list / exercises |
| Ctrl+K | Go online |
