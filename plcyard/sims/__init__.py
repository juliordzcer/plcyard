"""Simulated machines, wired to the PLC rack. MODELS lists them for the window, the exercise checker
and the tests: key → (menu name, model class)."""

from __future__ import annotations

from .garage import GarageModel
from .io_panel import IoPanelModel
from .mixer import MixerModel
from .silo import SiloModel
from .tank import TankModel
from .traffic import TrafficModel
from .two_tanks import TwoTankModel

MODELS = {
    "io": ("I/O panel", IoPanelModel),
    "silo": ("Silo", SiloModel),
    "traffic": ("Traffic lights", TrafficModel),
    "tank": ("Tank level", TankModel),
    "two_tanks": ("Two tanks", TwoTankModel),
    "garage": ("Garage door", GarageModel),
    "mixer": ("Batch mixer", MixerModel),
}
