from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .actions import Action, ClickAction, KeyAction
from .ecodes import resolve_ecode
from .exceptions import ProfileError

_logger = logging.getLogger(__name__)

_STICK_AXES = {
    "joystick1": ("joystick1left", "joystick1up"),
    "joystick2": ("joystick2left", "joystick2up"),
}


@dataclass(frozen=True)
class Hotkey:
    trigger: tuple[str, ...]
    action: Action
    cooldown: float


@dataclass(frozen=True)
class MouseAxisConfig:
    axis_x: str
    axis_y: str
    speed: float = 800.0
    deadzone: float = 0.15
    acceleration: float = 1.5
    condition: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ScrollAxisConfig:
    axis_y: str
    axis_x: str | None = None
    speed: float = 8.0
    deadzone: float = 0.15
    acceleration: float = 1.2
    condition: tuple[str, ...] | None = None


@dataclass(frozen=True)
class Profile:
    hotkeys: tuple[Hotkey, ...]
    mouse: tuple[MouseAxisConfig, ...]
    scroll: tuple[ScrollAxisConfig, ...]
    global_cooldown: float


def _as_name_list(value: Any) -> list[str]:
    """
    Normaliza un valor JSON a una lista de strings.

    - None → []
    - "" / False / 0 → []
    - "a" → ["a"]
    - ["a", "b"] → ["a", "b"]
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


def load_profile(path: Path | str, player: int = 1) -> Profile:
    """
    Carga un perfil compatible con evmapy.
    """
    path = Path(path)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"Error reading pad2key profile: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Error reading pad2key profile: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError("El perfil JSON debe ser un objeto.")

    try:
        global_cooldown = float(data.get("cooldown", 0.5))

        player_key = f"actions_player{player}"
        entries = data.get(player_key) or data.get("mappings") or []

        if not isinstance(entries, list):
            entries = []

        if not entries:
            available = [key for key in data if key.startswith("actions_")]
            _logger.warning(
                "No se encontró '%s' en el perfil. Secciones disponibles: %s",
                player_key,
                available or ["(ninguna)"],
            )

        hotkeys: dict[tuple[str, ...], Hotkey] = {}
        mouse: list[MouseAxisConfig] = []
        scroll: list[ScrollAxisConfig] = []

        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                _logger.warning("Mapping #%d: entrada no válida → ignorada.", index)
                continue

            if entry.get("_disabled"):
                continue

            atype = entry.get("type", "")
            if not atype:
                _logger.warning("Mapping #%d: not found 'type' → ignored.", index)
                continue

            raw_trigger = entry.get("trigger")
            if raw_trigger is None:
                _logger.warning("Mapping #%d: not found 'trigger' → ignored.", index)
                continue

            triggers = _as_name_list(raw_trigger)
            if not triggers:
                _logger.warning("Mapping #%d: 'trigger' empty → ignored.", index)
                continue

            condition = _as_name_list(entry.get("condition"))

            # ── key ────────────────────────────────────────────────
            if atype == "key":
                raw_target = entry.get("target")
                if raw_target is None:
                    _logger.warning(
                        "Mapping #%d: type 'key' sin 'target' → ignored.",
                        index,
                    )
                    continue

                targets = _as_name_list(raw_target)
                if not targets:
                    _logger.warning(
                        "Mapping #%d: 'target' vacío → ignored.",
                        index,
                    )
                    continue

                try:
                    codes = [resolve_ecode(target) for target in targets]
                except ValueError as exc:
                    _logger.warning("Mapping #%d: %s → ignored.", index, exc)
                    continue

                if len(codes) == 1 and targets[0].startswith("BTN_"):
                    action: Action = ClickAction(codes[0])
                else:
                    action = KeyAction(codes)

                combo = tuple(triggers + condition)

                if "cooldown" in entry:
                    cooldown = float(entry["cooldown"])
                elif len(combo) == 1:
                    cooldown = 0.0
                else:
                    cooldown = global_cooldown

                if combo in hotkeys:
                    _logger.warning(
                        "Mapping #%d: combo %r duplicate → replaced.",
                        index,
                        combo,
                    )

                hotkeys[combo] = Hotkey(
                    trigger=combo,
                    action=action,
                    cooldown=cooldown,
                )

                _logger.debug(
                    "  Mapping #%d: %s → %s (cd=%.2fs)",
                    index,
                    " + ".join(combo),
                    action,
                    cooldown,
                )

            # ── mouse ──────────────────────────────────────────────
            elif atype == "mouse":
                if len(triggers) == 1 and triggers[0] in _STICK_AXES:
                    axis_x, axis_y = _STICK_AXES[triggers[0]]
                elif len(triggers) == 2:
                    axis_x, axis_y = triggers[0], triggers[1]
                else:
                    _logger.warning(
                        "Mapping #%d: type 'mouse' needs complete stick "
                        "('joystick1'/'joystick2') or two axis → ignored.",
                        index,
                    )
                    continue

                cfg = MouseAxisConfig(
                    axis_x=axis_x,
                    axis_y=axis_y,
                    speed=float(entry.get("speed", 800.0)),
                    deadzone=float(entry.get("deadzone", 0.15)),
                    acceleration=float(entry.get("acceleration", 1.5)),
                    condition=tuple(condition) if condition else None,
                )
                mouse.append(cfg)

                cond_str = " + ".join(condition) if condition else "siempre"
                _logger.debug(
                    "  Mapping #%d: mouse (%s, %s) speed=%.1f dz=%.2f accel=%.2f condition=%s",
                    index,
                    axis_x,
                    axis_y,
                    cfg.speed,
                    cfg.deadzone,
                    cfg.acceleration,
                    cond_str,
                )

            # ── scroll ─────────────────────────────────────────────
            elif atype == "scroll":
                axis_y_name: str | None = None
                axis_x_name: str | None = None

                if len(triggers) == 1:
                    trigger_name = triggers[0]
                    if trigger_name in _STICK_AXES:
                        _, axis_y_name = _STICK_AXES[trigger_name]
                    else:
                        axis_y_name = trigger_name

                elif len(triggers) == 2:
                    axis_y_name, axis_x_name = triggers[0], triggers[1]

                else:
                    _logger.warning(
                        "Mapping #%d: type 'scroll' accepts 1 or 2 axis → ignored.",
                        index,
                    )
                    continue

                if axis_y_name is None:
                    _logger.warning(
                        "Mapping #%d: type 'scroll' with no valid Y axis → ignored.",
                        index,
                    )
                    continue

                scroll.append(
                    ScrollAxisConfig(
                        axis_y=axis_y_name,
                        axis_x=axis_x_name,
                        speed=float(entry.get("speed", 8.0)),
                        deadzone=float(entry.get("deadzone", 0.15)),
                        acceleration=float(entry.get("acceleration", 1.2)),
                        condition=tuple(condition) if condition else None,
                    )
                )

            else:
                _logger.warning(
                    "Mapping #%d: type '%s' unknown → ignored.",
                    index,
                    atype,
                )

        _logger.info(
            "Profile '%s' loaded: %d hotkey(s), %d mouse axis, %d scroll axis, global cooldown=%.2fs",  # noqa: E501
            path,
            len(hotkeys),
            len(mouse),
            len(scroll),
            global_cooldown,
        )

        return Profile(
            hotkeys=tuple(hotkeys.values()),
            mouse=tuple(mouse),
            scroll=tuple(scroll),
            global_cooldown=global_cooldown,
        )

    except (TypeError, ValueError) as exc:
        raise ProfileError(f"Error reading pad2key profile: {exc}") from exc
