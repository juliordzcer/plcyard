# Ladder

A routine is a list of **rungs**. Each rung has conditions on the left (contacts, compare boxes,
timers…) and outputs against the right rail (coils, move and math boxes…). Power flows from the
left rail through every condition that is TRUE.

- **Add**: pick an instruction in the instruction bar above the editor (grouped by family), or
  press Insert for a new rung. Branches put conditions in parallel.
- **Operands**: F2 or double-click. Type a tag, an address or a constant; the editor checks it
  and suggests the closest tag if it does not exist. Drag a switch or lamp from the simulation onto
  an instruction to fill it in.
- **Boxes pass power**: every box has an output, so a coil can follow a timer or a compare.
- **Comments** on rungs and on tags.
- **Undo/redo** per routine.

Online, energized paths are green, and boxes show live values (a timer's accumulated time, a
counter's count). Right-click an instruction to force its I/O point, go to its tag, or open
**PID Setup** on a PID box.

See the [instruction reference](reference/instructions.md).
