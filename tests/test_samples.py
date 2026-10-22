"""Bundled examples: each one downloads and does what its comments say."""

import pytest

from plcyard import formats, grader, labs
from plcyard.core.processor import Processor
from plcyard.sims.io_panel import IoPanelModel
from plcyard.sims.tank import TankModel

SAMPLES = sorted([*labs.SAMPLES.glob("*.rsl"), *labs.SAMPLES.glob("*.plcy")])
LABS = {lab.id: lab for lab in labs.load_all()}


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.stem)
def test_every_example_downloads_and_runs(path):
    plc = Processor()
    plc.device = IoPanelModel()
    assert plc.download(formats.load(path)) == []
    plc.set_mode(Processor.RUN)
    for _ in range(300):
        plc.tick(10)
    assert plc.mode == Processor.RUN, plc.fault


@pytest.mark.parametrize("name,lab", [("traffic-lights-routines.plcy", "10"), ("traffic-lights.plcy", "10"),
                                      ("silo-function-block.plcy", "08"), ("silo.plcy", "08")])
def test_examples_pass_the_matching_exercise_checks(name, lab):
    report = grader.grade(LABS[lab], formats.load(labs.SAMPLES / name))
    assert report.passed, (report.error, [(c.requirement, c.detail) for c in report.checks if not c.passed])


def test_motor_starter_instances_are_independent():
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    assert plc.download(formats.load(labs.SAMPLES / "motor-starters-function-block.plcy")) == []
    plc.set_mode(Processor.RUN)
    panel.set_pressed(1, 0, True)
    for _ in range(5):
        plc.tick(10)
    panel.set_pressed(1, 0, False)
    for _ in range(320):
        plc.tick(10)
    assert panel.lamp(2, 0) and panel.lamp(2, 1) and not panel.lamp(2, 2) and not panel.lamp(2, 3)


def test_recipe_example_times_come_from_the_array():
    plc, panel = Processor(), IoPanelModel()
    plc.device = panel
    assert plc.download(formats.load(labs.SAMPLES / "recipes-data-type.plcy")) == []
    plc.set_mode(Processor.RUN)
    panel.set_pressed(1, 1, True)                # recipe 1: fill 4 s
    panel.set_pressed(1, 0, True)
    plc.tick(20)
    panel.set_pressed(1, 0, False)
    for _ in range(350):
        plc.tick(10)
    assert panel.lamp(2, 0), "still filling after 3.5 s"
    for _ in range(100):
        plc.tick(10)
    assert panel.lamp(2, 1) and not panel.lamp(2, 0), "mixing after 4 s"


def test_pid_example_holds_the_level():
    plc, tank = Processor(), TankModel()
    plc.device = tank
    tank.level, tank.setpoint_knob = 30.0, 50.0
    assert plc.download(formats.load(labs.SAMPLES / "tank-pid-structured-text.plcy")) == []
    plc.set_mode(Processor.RUN)
    for _ in range(12000):
        plc.tick(10)
    assert abs(tank.level - 50.0) <= 2.0
