from __future__ import annotations

from .exceptions import GamepadlyError

try:
    import pygame
    import pygame.joystick  # noqa: F401
except ImportError as exc:
    raise GamepadlyError(
        "pygame missing.\n"
        "Install through pip or your OS package manager (apt, dnf...)"
    ) from exc
