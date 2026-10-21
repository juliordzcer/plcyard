"""Controller profiles: one per PLC family, all running on the same scan engine."""

from __future__ import annotations

from .base import Diagnostic, IODevice, Profile
from .logix import LOGIX
from .s7 import S7_PROFILE
from .slc500 import SLC500

DEFAULT = SLC500.name
PROFILES: dict[str, Profile] = {p.name: p for p in (SLC500, LOGIX, S7_PROFILE)}


def get(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown controller profile {name!r}") from None


def register(profile: Profile) -> None:
    PROFILES[profile.name] = profile


__all__ = ["DEFAULT", "PROFILES", "Diagnostic", "IODevice", "Profile", "get", "register"]
