"""The controller profile interface (base.py) and its registry. The PLC (core/plc) is the profile
every program uses; the registry lets tests run other profiles on the same engine."""

from __future__ import annotations

from .base import Diagnostic, IODevice, Profile

DEFAULT = "plcyard"
PROFILES: dict[str, Profile] = {}


def get(name: str | None = None) -> Profile:
    """A profile by name; the PLC by default. Programs of earlier controller styles are converted
    on load (formats/convert.py)."""
    if DEFAULT not in PROFILES:
        from ..plc import PLC
        PROFILES[DEFAULT] = PLC
    try:
        return PROFILES[name or DEFAULT]
    except KeyError:
        raise ValueError(f"unknown controller {name!r}") from None


def register(profile: Profile) -> None:
    PROFILES[profile.name] = profile


__all__ = ["DEFAULT", "PROFILES", "Diagnostic", "IODevice", "Profile", "get", "register"]
