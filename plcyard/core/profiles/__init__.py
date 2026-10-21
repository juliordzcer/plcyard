"""Controller profiles: one per PLC family, all running on the same scan engine."""

from __future__ import annotations

from .base import Diagnostic, IODevice, Profile
from .slc500 import SLC500

DEFAULT = SLC500.name
PROFILES: dict[str, Profile] = {SLC500.name: SLC500}


def get(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown controller profile {name!r}") from None


def register(profile: Profile) -> None:
    PROFILES[profile.name] = profile


__all__ = ["DEFAULT", "PROFILES", "Diagnostic", "IODevice", "Profile", "get", "register"]
