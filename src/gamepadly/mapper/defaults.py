from __future__ import annotations

from .actions import ClickAction, KeyAction
from .ecodes import ec
from .profile import Hotkey, MouseAxisConfig, Profile

DEFAULT_COOLDOWN = 0.5


def default_profile() -> Profile:
    hotkeys = (
        Hotkey(
            trigger=("hotkey", "start"),
            action=KeyAction([ec.KEY_LEFTALT, ec.KEY_F4]),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "select"),
            action=KeyAction([ec.KEY_LEFTMETA]),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "a"),
            action=KeyAction([ec.KEY_ESC]),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "b"),
            action=KeyAction([ec.KEY_ENTER]),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "pageup"),
            action=KeyAction([ec.KEY_LEFTCTRL, ec.KEY_LEFTALT, ec.KEY_T]),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "up"),
            action=KeyAction([ec.KEY_VOLUMEUP]),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "down"),
            action=KeyAction([ec.KEY_VOLUMEDOWN]),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "r3"),
            action=ClickAction(ec.BTN_LEFT),
            cooldown=DEFAULT_COOLDOWN,
        ),
        Hotkey(
            trigger=("hotkey", "l3"),
            action=ClickAction(ec.BTN_RIGHT),
            cooldown=DEFAULT_COOLDOWN,
        ),
    )

    mouse = (
        MouseAxisConfig(
            axis_x="joystick2left",
            axis_y="joystick2up",
            speed=800.0,
            deadzone=0.15,
            acceleration=1.5,
            condition=("hotkey",),
        ),
    )

    return Profile(
        hotkeys=hotkeys,
        mouse=mouse,
        scroll=(),
        global_cooldown=DEFAULT_COOLDOWN,
    )
