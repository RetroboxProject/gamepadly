from __future__ import annotations

import logging
from dataclasses import dataclass

from .ecodes import ec, is_button
from .exceptions import GamepadlyError
from .resolver import ResolvedProfile

try:
    from evdev import UInput
except ImportError as exc:
    raise GamepadlyError(
        "python3-evdev missing.\n"
        "Install through pip or your OS package manager (apt, dnf...)"
    ) from exc

_logger = logging.getLogger(__name__)


@dataclass
class UInputPair:
    """
    Dos dispositivos UInput separados:

      kbd   → EV_KEY con KEY_*
      mouse → EV_KEY con BTN_* + EV_REL

    Separarlos evita que el compositor/clasificador del kernel trate
    eventos BTN_* como teclas de teclado.
    """

    kbd: UInput | None
    mouse: UInput | None

    def write_key(self, code: int, value: int) -> None:
        if is_button(code):
            if self.mouse:
                self.mouse.write(ec.EV_KEY, code, value)
        else:
            if self.kbd:
                self.kbd.write(ec.EV_KEY, code, value)

    def write_rel(self, rel: int, value: int) -> None:
        if self.mouse:
            self.mouse.write(ec.EV_REL, rel, value)

    def syn(self, has_kbd: bool = False, has_mouse: bool = False) -> None:
        if has_kbd and self.kbd:
            self.kbd.syn()

        if has_mouse and self.mouse:
            self.mouse.syn()

    def close(self) -> None:
        if self.kbd:
            self.kbd.close()

        if self.mouse:
            self.mouse.close()


def build_uinput(resolved: ResolvedProfile, player: int) -> UInputPair:
    kbd_keys: set[int] = set()
    mouse_buttons: set[int] = set()

    has_rel = bool(resolved.mouse)
    has_scroll = bool(resolved.scroll)

    for action in resolved.hotkeys.values():
        for code in action.uinput_keys():
            if is_button(code):
                mouse_buttons.add(code)
            else:
                kbd_keys.add(code)

    # Si hay movimiento de ratón también necesitamos BTN_LEFT declarado
    # para que el compositor reconozca el dispositivo como puntero.
    if has_rel:
        mouse_buttons.add(ec.BTN_LEFT)

    kbd_uinput = None
    mouse_uinput = None

    if kbd_keys:
        kbd_uinput = UInput(
            {ec.EV_KEY: sorted(kbd_keys)},
            name=f"gamepad-mapper-kbd-{player}",
        )
        _logger.debug("UInput teclado: %s", sorted(kbd_keys))

    if mouse_buttons or has_rel or has_scroll:
        caps: dict[int, list[int]] = {}

        if mouse_buttons:
            caps[ec.EV_KEY] = sorted(mouse_buttons)

        rel_axes = [ec.REL_X, ec.REL_Y]

        if has_scroll:
            rel_axes.extend([ec.REL_WHEEL, ec.REL_HWHEEL])

        caps[ec.EV_REL] = rel_axes

        mouse_uinput = UInput(
            caps,
            name=f"gamepad-mapper-mouse-{player}",
        )
        _logger.debug("UInput ratón: BTNs=%s", sorted(mouse_buttons))

    return UInputPair(kbd=kbd_uinput, mouse=mouse_uinput)