"""What a mapping does when its trigger fires."""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .uinput_backend import UInputPair

_logger = logging.getLogger(__name__)

# Commands started by ExecAction, polled by reap_children() so that they do
# not linger as zombies while the mapper keeps running.
_children: list[subprocess.Popen] = []


def reap_children() -> None:
    """Forget the commands that have already finished."""
    _children[:] = [child for child in _children if child.poll() is None]


@dataclass(frozen=True)
class KeyAction:
    """Press a key chord while the trigger is held, release it afterwards."""

    keys: list[int]

    def press_down(self, ui: UInputPair) -> None:
        """Press every key of the chord, in order."""
        for key in self.keys:
            ui.write_key(key, 1)
        ui.syn(has_kbd=True)

    def press_up(self, ui: UInputPair) -> None:
        """Release the chord, in reverse order."""
        for key in reversed(self.keys):
            ui.write_key(key, 0)
        ui.syn(has_kbd=True)

    def uinput_keys(self) -> set[int]:
        """Key codes the virtual keyboard has to declare."""
        return set(self.keys)

    def uinput_rel(self) -> set[int]:
        """Relative axes the virtual mouse has to declare."""
        return set()


@dataclass(frozen=True)
class ClickAction:
    """Hold a mouse button while the trigger is held."""

    button: int

    def press_down(self, ui: UInputPair) -> None:
        """Press the mouse button."""
        ui.write_key(self.button, 1)
        ui.syn(has_mouse=True)

    def press_up(self, ui: UInputPair) -> None:
        """Release the mouse button."""
        ui.write_key(self.button, 0)
        ui.syn(has_mouse=True)

    def uinput_keys(self) -> set[int]:
        """Button codes the virtual mouse has to declare."""
        return {self.button}

    def uinput_rel(self) -> set[int]:
        """Relative axes the virtual mouse has to declare."""
        return set()


@dataclass(frozen=True)
class ExecAction:
    """Run external commands when the trigger fires (evmapy's ``exec`` type).

    Like evmapy, each command is a shell command line. Unlike evmapy, which
    calls ``os.system`` and blocks until the command ends, the commands run in
    the background, in a session of their own: they never stall the mapper,
    and they survive it when the mapper is stopped (e.g. a command that ends
    the game, and with it the mapper).
    """

    commands: tuple[str, ...]

    def press_down(self, ui: UInputPair) -> None:  # pylint: disable=unused-argument
        """Start every command."""
        for command in self.commands:
            _logger.debug("exec: %s", command)
            try:
                # pylint: disable-next=consider-using-with  # reaped by reap_children()
                child = subprocess.Popen(
                    command,
                    shell=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError as exc:
                _logger.error("exec: cannot run %r: %s", command, exc)
                continue
            _children.append(child)

    def press_up(self, ui: UInputPair) -> None:
        """Nothing to release."""

    def uinput_keys(self) -> set[int]:
        """Commands need no virtual device."""
        return set()

    def uinput_rel(self) -> set[int]:
        """Commands need no virtual device."""
        return set()


@dataclass(frozen=True)
class CallbackAction:
    """Arbitrary Python action. Internal use only, not available in JSON."""

    fn: Callable[[], None]

    def press_down(self, ui: UInputPair) -> None:  # pylint: disable=unused-argument
        """Call the function."""
        self.fn()

    def press_up(self, ui: UInputPair) -> None:
        """Nothing to release."""

    def uinput_keys(self) -> set[int]:
        """Callbacks need no virtual device."""
        return set()

    def uinput_rel(self) -> set[int]:
        """Callbacks need no virtual device."""
        return set()


Action = KeyAction | ClickAction | ExecAction | CallbackAction
