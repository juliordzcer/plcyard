# The scan cycle

The PLC repeats one cycle, the **scan**, over and over:

1. **Input scan**: the state of every input card is copied into the input image (`%I`, `%IW`).
   Forced inputs take their forced value here.
2. **Program scan**: the main routine runs from the first rung to the last (or the ST statements,
   or the FBD blocks in data-flow order). Called routines and blocks run where they are called.
   Instructions read and write the images and tags, never the cards directly.
3. **Output scan**: the output image (`%Q`, `%QW`) is copied to the output cards. Forced outputs
   take their forced value here.

Because of this a rung sees what earlier rungs wrote in the same scan, and an output written twice
ends with the last value written: the rung order matters.

## Modes

- **Program**: the program does not run and the outputs are off. Edit freely.
- **Run**: entering RUN does a **prescan** (non-retentive outputs and timers reset), then the
  first scan runs with `FirstScan` TRUE.
- **Test** (single scan): F10 runs one scan at a time, to follow a sequence step by step.
- **Faulted**: a major fault (an array index out of range, a division by zero in some cases, a
  routine that calls itself…) stops the PLC. The fault code and the rung are shown; clear the
  fault and go back to RUN.

## Online and offline

The online bar shows whether the editor is connected to the PLC (**Go Online**, Ctrl+K). Online,
the editors show live values and power flow. **Download** sends the program; **Upload** reads the
program back from the PLC. Offline the PLC keeps running what it has.

## Timing

The simulated scan runs every 10 ms. Timers count real milliseconds; the exercise checker runs the
same scans faster than real time.

## Analog values

Analog inputs and outputs are 16-bit words: raw 0-27648 is 0-10 V. Use `NORM_X` and `SCALE_X`
(or `SCP`) to turn them into engineering units.
