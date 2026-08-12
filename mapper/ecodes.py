from __future__ import annotations

from .exceptions import GamepadlyError

try:
    from evdev import ecodes as ec
except ImportError as exc:
    raise GamepadlyError(
        "python3-evdev missing.\n"
        "Install through pip or your OS package manager (apt, dnf...)"
    ) from exc


# Rango de códigos BTN_* en el kernel.
BTN_MIN = 0x100
BTN_MAX = 0x2E7


def resolve_ecode(name: str) -> int:
    """
    Convierte un nombre de ecodes ('KEY_F4', 'BTN_LEFT', ...)
    a su valor entero.
    """
    value = getattr(ec, name, None)
    if value is None:
        raise ValueError(
            f"Nombre de ecodes desconocido: '{name}'. "
            "Consulta `python3 -c \"from evdev import ecodes; help(ecodes)\"`"
        )
    return int(value)


def is_button(code: int) -> bool:
    return BTN_MIN <= code <= BTN_MAX