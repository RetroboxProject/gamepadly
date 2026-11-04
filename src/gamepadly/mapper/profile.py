"""Load evmapy-compatible pad2key profiles.

A profile is a JSON object whose ``actions_player<N>`` list (or ``mappings``)
holds the mappings of player N. Every mapping has a ``trigger`` (one or more
EmulationStation input names), a ``type`` and the type's own fields:

* ``key``: ``target`` is a key chord (``KEY_*``) or a mouse button (``BTN_*``)
  held while the trigger is held;
* ``exec``: ``target`` is a shell command line, or a list of them, run when
  the trigger fires;
* ``mouse`` / ``scroll`` (gamepadly): an analog stick moves the pointer or
  the wheel.

Like evmapy, ``key`` and ``exec`` mappings accept:

* ``mode``: ``all`` (default, the trigger is a combination), ``any`` (each
  input of the trigger fires the mapping on its own) or ``sequence`` (the
  inputs have to be pressed one after the other);
* ``hold``: seconds the trigger has to stay active before the mapping fires
  (not allowed with ``sequence``).

Gamepadly adds:

* ``condition``: inputs that also have to be held (as in Batocera);
* ``cooldown``: seconds before the mapping can fire again (the profile's
  top-level ``cooldown`` is the default for combinations);
* ``tap``: ``true`` makes a single-input mapping fire when the input is
  released, and only if nothing else was pressed meanwhile and it was not
  held longer than ``TAP_MAX_SECONDS``. It lets a button that is also the
  modifier of combinations (the hotkey) do something of its own;
* ``_disabled``: ``true`` skips the mapping.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .actions import Action, ClickAction, ExecAction, KeyAction
from .ecodes import resolve_ecode
from .exceptions import ProfileError

_logger = logging.getLogger(__name__)

_STICK_AXES = {
    "joystick1": ("joystick1left", "joystick1up"),
    "joystick2": ("joystick2left", "joystick2up"),
}

_MODES = ("all", "any", "sequence")

DEFAULT_COOLDOWN = 0.5
TAP_MAX_SECONDS = 0.5
"""A tap held longer than this is not a tap any more."""


@dataclass(frozen=True)
class Hotkey:
    """A combination of inputs (one or more) and what it does."""

    trigger: tuple[str, ...]
    action: Action
    cooldown: float
    hold: float = 0.0
    tap: bool = False


@dataclass(frozen=True)
class Sequence:
    """Inputs pressed one after the other (evmapy's ``sequence`` mode)."""

    trigger: tuple[str, ...]
    action: Action
    cooldown: float


@dataclass(frozen=True)
class MouseAxisConfig:
    """Pointer motion from an analog stick."""

    axis_x: str
    axis_y: str
    speed: float = 800.0
    deadzone: float = 0.15
    acceleration: float = 1.5
    condition: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ScrollAxisConfig:
    """Wheel motion from an analog stick."""

    axis_y: str
    axis_x: str | None = None
    speed: float = 8.0
    deadzone: float = 0.15
    acceleration: float = 1.2
    condition: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Profile:
    """The mappings of one player."""

    hotkeys: tuple[Hotkey, ...]
    mouse: tuple[MouseAxisConfig, ...]
    scroll: tuple[ScrollAxisConfig, ...]
    global_cooldown: float
    sequences: tuple[Sequence, ...] = ()


@dataclass
class _Collected:
    """Mappings gathered while reading a profile, deduplicated by trigger."""

    hotkeys: dict[tuple[tuple[str, ...], bool], Hotkey]
    sequences: dict[tuple[str, ...], Sequence]
    mouse: list[MouseAxisConfig]
    scroll: list[ScrollAxisConfig]


def _as_name_list(value: Any) -> list[str]:
    """Normalize a JSON value to a list of strings.

    ``None`` and falsy scalars give ``[]``, a string gives ``[string]`` and a
    list gives its items as strings.
    """
    if value is None:
        return []
    if not value and not isinstance(value, list):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _parse_action(entry: dict[str, Any], index: int) -> Action | None:
    """Build the action of a ``key`` or ``exec`` mapping."""
    atype = entry["type"]
    targets = _as_name_list(entry.get("target"))
    if not targets:
        _logger.warning("Mapping #%d: type '%s' without 'target' → ignored.", index, atype)
        return None

    if atype == "exec":
        return ExecAction(tuple(targets))

    if len(set(targets)) != len(targets):
        _logger.warning("Mapping #%d: duplicate key in 'target' → ignored.", index)
        return None
    try:
        codes = [resolve_ecode(target) for target in targets]
    except ValueError as exc:
        _logger.warning("Mapping #%d: %s → ignored.", index, exc)
        return None

    if len(codes) == 1 and targets[0].startswith("BTN_"):
        return ClickAction(codes[0])
    return KeyAction(codes)


def _timing(entry: dict[str, Any], index: int) -> tuple[str, float, bool] | None:
    """Read and check ``mode``, ``hold`` and ``tap`` the way evmapy does."""
    mode = str(entry.get("mode", "all"))
    hold = float(entry.get("hold", 0.0))
    tap = bool(entry.get("tap", False))

    error = None
    if mode not in _MODES:
        error = f"invalid mode '{mode}'"
    elif hold < 0:
        error = "hold time cannot be negative"
    elif mode == "sequence" and hold > 0:
        error = "hold time cannot be positive for sequences"
    elif tap and (hold > 0 or mode == "sequence"):
        error = "'tap' cannot be combined with 'hold' or a sequence"

    if error is not None:
        _logger.warning("Mapping #%d: %s → ignored.", index, error)
        return None
    return mode, hold, tap


def _cooldown(entry: dict[str, Any], combo_size: int, global_cooldown: float) -> float:
    """Explicit cooldown, else none for single inputs and the global one for combos."""
    if "cooldown" in entry:
        return float(entry["cooldown"])
    return 0.0 if combo_size == 1 else global_cooldown


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _add_triggered(
    entry: dict[str, Any],
    index: int,
    triggers: list[str],
    condition: list[str],
    global_cooldown: float,
    collected: _Collected,
) -> None:
    """Add a ``key`` or ``exec`` mapping."""
    timing = _timing(entry, index)
    action = _parse_action(entry, index)
    if timing is None or action is None:
        return
    mode, hold, tap = timing

    if mode == "sequence":
        if len(triggers) < 2:
            _logger.warning("Mapping #%d: a sequence needs 2 inputs or more → ignored.", index)
            return
        sequence = tuple(triggers)
        collected.sequences[sequence] = Sequence(
            trigger=sequence,
            action=action,
            cooldown=_cooldown(entry, len(sequence), global_cooldown),
        )
        return

    if len(set(triggers)) != len(triggers):
        _logger.warning("Mapping #%d: duplicate input in 'trigger' → ignored.", index)
        return

    # "any": every input of the trigger is a combination of its own
    combos = [[name] for name in triggers] if mode == "any" else [triggers]
    for names in combos:
        combo = tuple(names + condition)
        if tap and len(combo) != 1:
            _logger.warning("Mapping #%d: 'tap' needs a single input → ignored.", index)
            return
        if (combo, tap) in collected.hotkeys:
            _logger.warning("Mapping #%d: combo %r duplicate → replaced.", index, combo)
        collected.hotkeys[(combo, tap)] = Hotkey(
            trigger=combo,
            action=action,
            cooldown=_cooldown(entry, len(combo), global_cooldown),
            hold=hold,
            tap=tap,
        )
        _logger.debug("  Mapping #%d: %s → %s", index, " + ".join(combo), action)


def _add_mouse(
    entry: dict[str, Any], index: int, triggers: list[str], condition: list[str],
    collected: _Collected,
) -> None:
    """Add a ``mouse`` mapping: a whole stick or two axes."""
    if len(triggers) == 1 and triggers[0] in _STICK_AXES:
        axis_x, axis_y = _STICK_AXES[triggers[0]]
    elif len(triggers) == 2:
        axis_x, axis_y = triggers[0], triggers[1]
    else:
        _logger.warning(
            "Mapping #%d: type 'mouse' needs a whole stick ('joystick1'/'joystick2') "
            "or two axes → ignored.",
            index,
        )
        return

    collected.mouse.append(
        MouseAxisConfig(
            axis_x=axis_x,
            axis_y=axis_y,
            speed=float(entry.get("speed", 800.0)),
            deadzone=float(entry.get("deadzone", 0.15)),
            acceleration=float(entry.get("acceleration", 1.5)),
            condition=tuple(condition) if condition else None,
        )
    )


def _add_scroll(
    entry: dict[str, Any], index: int, triggers: list[str], condition: list[str],
    collected: _Collected,
) -> None:
    """Add a ``scroll`` mapping: a vertical axis, optionally a horizontal one."""
    axis_x: str | None = None
    if len(triggers) == 1:
        axis_y = _STICK_AXES[triggers[0]][1] if triggers[0] in _STICK_AXES else triggers[0]
    elif len(triggers) == 2:
        axis_y, axis_x = triggers
    else:
        _logger.warning("Mapping #%d: type 'scroll' accepts 1 or 2 axes → ignored.", index)
        return

    collected.scroll.append(
        ScrollAxisConfig(
            axis_y=axis_y,
            axis_x=axis_x,
            speed=float(entry.get("speed", 8.0)),
            deadzone=float(entry.get("deadzone", 0.15)),
            acceleration=float(entry.get("acceleration", 1.2)),
            condition=tuple(condition) if condition else None,
        )
    )


def _add_entry(entry: Any, index: int, global_cooldown: float, collected: _Collected) -> None:
    """Dispatch one mapping of the profile to its parser."""
    if not isinstance(entry, dict):
        _logger.warning("Mapping #%d: not an object → ignored.", index)
        return
    if entry.get("_disabled"):
        return

    atype = entry.get("type", "")
    triggers = _as_name_list(entry.get("trigger"))
    if not atype or not triggers:
        _logger.warning("Mapping #%d: missing 'type' or 'trigger' → ignored.", index)
        return
    condition = _as_name_list(entry.get("condition"))

    if atype in ("key", "exec"):
        _add_triggered(entry, index, triggers, condition, global_cooldown, collected)
    elif atype == "mouse":
        _add_mouse(entry, index, triggers, condition, collected)
    elif atype == "scroll":
        _add_scroll(entry, index, triggers, condition, collected)
    else:
        _logger.warning("Mapping #%d: type '%s' unknown → ignored.", index, atype)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"Error reading pad2key profile: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError("The JSON profile must be an object.")
    return data


def load_profile(path: Path | str, player: int = 1) -> Profile:
    """Load the mappings of a player from an evmapy-compatible profile."""
    path = Path(path)
    data = _read_json(path)

    try:
        global_cooldown = float(data.get("cooldown", DEFAULT_COOLDOWN))

        player_key = f"actions_player{player}"
        entries = data.get(player_key) or data.get("mappings") or []
        if not isinstance(entries, list):
            entries = []
        if not entries:
            available = [key for key in data if key.startswith("actions_")]
            _logger.warning(
                "'%s' not found in the profile. Available sections: %s",
                player_key,
                available or ["(none)"],
            )

        collected = _Collected(hotkeys={}, sequences={}, mouse=[], scroll=[])
        for index, entry in enumerate(entries):
            _add_entry(entry, index, global_cooldown, collected)

    except (TypeError, ValueError) as exc:
        raise ProfileError(f"Error reading pad2key profile: {exc}") from exc

    _logger.info(
        "Profile '%s' loaded: %d hotkey(s), %d sequence(s), %d mouse axis, %d scroll axis, "
        "global cooldown=%.2fs",
        path,
        len(collected.hotkeys),
        len(collected.sequences),
        len(collected.mouse),
        len(collected.scroll),
        global_cooldown,
    )

    return Profile(
        hotkeys=tuple(collected.hotkeys.values()),
        mouse=tuple(collected.mouse),
        scroll=tuple(collected.scroll),
        global_cooldown=global_cooldown,
        sequences=tuple(collected.sequences.values()),
    )
