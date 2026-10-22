"""Simulated machines, wired to the PLC rack. MODELS lists them for the window, the exercise checker
and the tests: key → (menu name, model class)."""

from __future__ import annotations

from .bottles import BottleModel
from .elevator import ElevatorModel
from .garage import GarageModel
from .hvac import HvacModel
from .io_panel import IoPanelModel
from .mixer import MixerModel
from .parking import ParkingModel
from .pick_place import PickPlaceModel
from .pump_station import PumpStationModel
from .silo import SiloModel
from .sorter import SorterModel
from .tank import TankModel
from .traffic import TrafficModel
from .two_tanks import TwoTankModel
from .washer import WasherModel

MODELS = {
    "io": ("I/O panel", IoPanelModel),
    "silo": ("Silo", SiloModel),
    "traffic": ("Traffic lights", TrafficModel),
    "tank": ("Tank level", TankModel),
    "two_tanks": ("Two tanks", TwoTankModel),
    "garage": ("Garage door", GarageModel),
    "mixer": ("Batch mixer", MixerModel),
    "elevator": ("Elevator", ElevatorModel),
    "bottles": ("Bottle line", BottleModel),
    "sorter": ("Sorting conveyor", SorterModel),
    "pick_place": ("Pick and place", PickPlaceModel),
    "parking": ("Parking garage", ParkingModel),
    "pumps": ("Pump station", PumpStationModel),
    "hvac": ("Room climate", HvacModel),
    "washer": ("Washing machine", WasherModel),
}
