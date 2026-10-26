from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .uinput_backend import UInputPair


@dataclass(frozen=True)
class KeyAction:
    """Pulsa y suelta una secuencia de teclas."""

    keys: list[int]

    def press_down(self, ui: "UInputPair") -> None:
        for key in self.keys:
            ui.write_key(key, 1)
        ui.syn(has_kbd=True)

    def press_up(self, ui: "UInputPair") -> None:
        for key in reversed(self.keys):
            ui.write_key(key, 0)
        ui.syn(has_kbd=True)

    def uinput_keys(self) -> set[int]:
        return set(self.keys)

    def uinput_rel(self) -> set[int]:
        return set()


@dataclass(frozen=True)
class ClickAction:
    """Botón de ratón mantenido mientras el botón del mando esté pulsado."""

    button: int

    def press_down(self, ui: "UInputPair") -> None:
        ui.write_key(self.button, 1)
        ui.syn(has_mouse=True)

    def press_up(self, ui: "UInputPair") -> None:
        ui.write_key(self.button, 0)
        ui.syn(has_mouse=True)

    def uinput_keys(self) -> set[int]:
        return {self.button}

    def uinput_rel(self) -> set[int]:
        return set()


@dataclass(frozen=True)
class CallbackAction:
    """Acción arbitraria en Python. Solo uso interno, no JSON."""

    fn: Callable[[], None]

    def press_down(self, ui: "UInputPair") -> None:
        self.fn()

    def press_up(self, ui: "UInputPair") -> None:
        pass

    def uinput_keys(self) -> set[int]:
        return set()

    def uinput_rel(self) -> set[int]:
        return set()


Action = KeyAction | ClickAction | CallbackAction
