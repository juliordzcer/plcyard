# Function block diagram

A routine in FBD is a sheet of **blocks** wired pin to pin. Inputs are on the left of a block,
outputs on the right.

- **Add a block** from the palette, then drag it into place.
- **Wire** by dragging from an output pin to an input pin. An output can feed many inputs.
- **Operands on pins**: an input pin with no wire takes a tag, an address or a constant; an output
  pin may also write a tag. Drag an I/O point from the simulation onto a pin.
- **Instances**: timer, counter and PID blocks keep their state in a tag of that type, shown above
  the block.
- **More inputs**: AND, OR, ADD… take more inputs (right-click → Add input).

Blocks run in **data-flow order**: a block runs after every block wired to its inputs. A loop of
wires is reported as an error.

Online, every pin shows its live value and BOOL wires turn green when TRUE.

See the [block reference](reference/function-blocks.md).
