# Adding a simulation

A simulation is two classes: a **model** (the physics, no UI) and a **view** (the drawing).

## The model

`plcyard/sims/my_machine.py`. Its module docstring documents the I/O: it becomes the
[simulation reference](reference/simulations.md).

```python
"""Conveyor with a photo-eye.

Digital (slot words):
  %I0.0 Start (NO)   %I0.1 Stop (NC)   %I0.2 Photo-eye
  %Q0.0 Motor
"""

@dataclass
class ConveyorModel:
    name = "Conveyor"
    position: float = 0.0
    start_pressed: bool = False
    stop_pressed: bool = False
    outputs: int = 0
    events: list[str] = field(default_factory=list)

    def input_words(self) -> dict[int, int]:          # slot → 16-bit word, read every input scan
        return {1: int(self.start_pressed) | int(not self.stop_pressed) << 1}

    def set_output_words(self, words: dict[int, int]) -> None:   # written every output scan
        self.outputs = words.get(2, 0) & 0xFFFF

    def step(self, dt_ms: float) -> None:              # advance the physics after each scan
        ...
```

- Slot 1 is `%I0.x`, slot 2 is `%Q0.x`.
- Analog: `analog_inputs()` returns `{channel: volts}` (0-10 V, channel 0 is `%IW64`);
  `set_analog_outputs(volts)` receives the outputs.
- Append a line to `events` for misuse (a crash, an overflow).

Register it in `MODELS` in `plcyard/sims/__init__.py`: `"conveyor": ("Conveyor", ConveyorModel)`.

## The view

A `QWidget` that takes the model and repaints it (see `plcyard/ui/sim_views3.py` for examples
built on the shared canvas and control panel), registered in `VIEWS`. Give every labelled device
its address so it can be dragged onto a program.

## The example and the tests

Add a working example in `plcyard/data/samples/` and a test that runs it on the model and checks the
machine does its job. Then regenerate the reference:

```bash
python -m plcyard.docgen
```
