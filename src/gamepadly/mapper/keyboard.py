"""Keyboard hotkeys: the ``actions_keyboard`` section of a profile.

One process watches every keyboard (evdev, read-only: nothing is grabbed,
the focused window still gets every key) and fires the section's mappings
with the same engine as the controllers. Triggers are evdev key names; the
right-hand modifiers count as the left-hand ones, so ``KEY_LEFTSHIFT``
means either Shift:

.. code-block:: json

    "actions_keyboard": [
        {"trigger": ["KEY_LEFTSHIFT", "KEY_ESC"], "type": "exec",
         "target": "retrobox-emukill"}
    ]

``key`` mappings press their keys on a virtual keyboard of their own;
``exec``, ``mode``, ``hold``, ``tap`` and ``cooldown`` work as for the
controllers. Mouse and scroll mappings make no sense here and are ignored.
Gamepadly's own virtual devices are never read, so a mapping cannot trigger
itself. New keyboards are picked up while running.
"""

from __future__ import annotations

import logging
import select
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from ..manager import KEYBOARD_SECTION
from .actions import reap_children
from .ecodes import ec, resolve_ecode
from .engine import LOOP_DT, REAP_EVERY, MapperEngine
from .exceptions import GamepadlyError, ProfileError
from .profile import load_profile
from .resolver import ResolvedHotkey, ResolvedProfile, ResolvedSequence
from .uinput_backend import build_uinput

if TYPE_CHECKING:
    from pathlib import Path

    from .profile import Profile

try:
    import evdev
except ImportError as exc:  # pragma: no cover - evdev is a dependency
    raise GamepadlyError("python3-evdev missing.") from exc

_logger = logging.getLogger(__name__)

OWN_DEVICE_PREFIX: Final = "gamepad-mapper-"
"""Names of gamepadly's virtual devices (see uinput_backend), never read."""

RESCAN_SECONDS: Final = 2.0

_SAME_KEY: Final = {
    ec.KEY_RIGHTSHIFT: ec.KEY_LEFTSHIFT,
    ec.KEY_RIGHTCTRL: ec.KEY_LEFTCTRL,
    ec.KEY_RIGHTALT: ec.KEY_LEFTALT,
    ec.KEY_RIGHTMETA: ec.KEY_LEFTMETA,
}

_KEY_DOWN: Final = 1
_KEY_UP: Final = 0


def normalize_key(code: int) -> int:
    """Right-hand modifiers count as the left-hand ones."""
    return _SAME_KEY.get(code, code)


def _key_codes(names: tuple[str, ...]) -> frozenset[int] | None:
    try:
        return frozenset(normalize_key(resolve_ecode(name)) for name in names)
    except ValueError as exc:
        _logger.warning("Keyboard mapping %r: %s — ignored.", names, exc)
        return None


def resolve_keyboard_profile(profile: Profile) -> ResolvedProfile:
    """Bind the key names of the keyboard section to key codes."""
    hotkeys: list[ResolvedHotkey] = []
    for hotkey in profile.hotkeys:
        codes = _key_codes(hotkey.trigger)
        if codes is None:
            continue
        if len(codes) < len(hotkey.trigger):
            _logger.warning("Keyboard mapping %r: the same key twice — ignored.", hotkey.trigger)
            continue
        hotkeys.append(
            ResolvedHotkey(
                codes=codes,
                action=hotkey.action,
                cooldown=hotkey.cooldown,
                hold=hotkey.hold,
                tap=hotkey.tap,
            )
        )

    sequences = []
    for sequence in profile.sequences:
        if _key_codes(sequence.trigger) is None:
            continue
        sequences.append(
            ResolvedSequence(
                codes=tuple(normalize_key(resolve_ecode(name)) for name in sequence.trigger),
                action=sequence.action,
                cooldown=sequence.cooldown,
            )
        )

    if profile.mouse or profile.scroll:
        _logger.warning("Mouse and scroll mappings are ignored in '%s'.", KEYBOARD_SECTION)
    return ResolvedProfile(
        hotkeys=tuple(hotkeys), mouse=(), scroll=(), sequences=tuple(sequences)
    )


def is_keyboard(device: evdev.InputDevice) -> bool:
    """A real keyboard: letter and Escape keys, and not one of gamepadly's devices."""
    if device.name.startswith(OWN_DEVICE_PREFIX):
        return False
    keys = device.capabilities().get(ec.EV_KEY, [])
    return ec.KEY_A in keys and ec.KEY_ESC in keys


@dataclass
class _Keyboards:
    """The keyboards being watched, found again every few seconds."""

    devices: dict[str, evdev.InputDevice] = field(default_factory=dict)
    last_scan: float = float("-inf")

    def rescan(self, now: float) -> None:
        """Open the keyboards that appeared since the last scan."""
        if now - self.last_scan < RESCAN_SECONDS:
            return
        self.last_scan = now
        for path in evdev.list_devices():
            if path in self.devices:
                continue
            try:
                device = evdev.InputDevice(path)
            except OSError:
                continue
            if is_keyboard(device):
                _logger.info("Watching keyboard '%s' (%s)", device.name, path)
                self.devices[path] = device
            else:
                device.close()

    def drop(self, device: evdev.InputDevice) -> None:
        """Forget a keyboard that went away."""
        _logger.info("Keyboard '%s' gone", device.name)
        self.devices.pop(device.path, None)
        try:
            device.close()
        except OSError:
            pass

    def close(self) -> None:
        """Close every keyboard."""
        for device in list(self.devices.values()):
            device.close()
        self.devices.clear()


def _forward(engine: MapperEngine, device: evdev.InputDevice, now: float, ui) -> None:
    """Feed the pending events of one keyboard to the engine."""
    for event in device.read():
        if event.type != ec.EV_KEY:
            continue
        code = normalize_key(event.code)
        if event.value == _KEY_DOWN:
            engine.press(code, now, ui)
        elif event.value == _KEY_UP:
            engine.release(code, now, ui)
        # 2 is autorepeat: a held key is already pressed


def run_keyboard_mapper(profile_path: str | Path) -> None:
    """Fire the profile's keyboard mappings until stopped."""
    resolved = resolve_keyboard_profile(load_profile(profile_path, section=KEYBOARD_SECTION))
    if resolved.empty:
        raise ProfileError(f"No '{KEYBOARD_SECTION}' mappings in {profile_path}.")

    engine = MapperEngine(joystick=None, resolved=resolved, player=0)
    ui = build_uinput(resolved, "keyboard")
    keyboards = _Keyboards()
    iterations = 0
    try:
        while True:
            now = time.monotonic()
            keyboards.rescan(now)
            readable = []
            if keyboards.devices:
                readable, _, _ = select.select(list(keyboards.devices.values()), [], [], LOOP_DT)
            else:
                time.sleep(LOOP_DT)
            now = time.monotonic()
            for device in readable:
                try:
                    _forward(engine, device, now, ui)
                except OSError:
                    keyboards.drop(device)
                    # its keys will never be released: let go of everything
                    for code in list(engine.state.pressed):
                        engine.release(code, now, ui)
            engine.tick(now, ui)
            iterations += 1
            if iterations % REAP_EVERY == 0:
                reap_children()
    finally:
        keyboards.close()
        ui.close()
