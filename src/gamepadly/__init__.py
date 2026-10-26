"""Gamepadly: Linux gamepad-to-keyboard/mouse mapper."""

from __future__ import annotations

from importlib import metadata as _metadata

try:
    __version__ = _metadata.version("gamepadly")
except _metadata.PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0+unknown"

from .manager import GamepadManager, find_profile

__all__ = ["GamepadManager", "find_profile", "__version__"]
