"""Bind a profile's input names to the physical inputs of a controller."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .actions import Action
from .inputs import AxisInput, ESInputMap, input_to_virtual
from .profile import Profile

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedAxisMouse:
    """Pointer motion bound to the axes of one controller."""

    axis_id_x: int
    scale_x: int
    axis_id_y: int
    scale_y: int
    speed: float
    deadzone: float
    acceleration: float
    condition: frozenset[int] | None


@dataclass(frozen=True)
class ResolvedAxisScroll:
    """Wheel motion bound to the axes of one controller."""

    axis_id_y: int
    scale_y: int
    axis_id_x: int | None
    scale_x: int | None
    speed: float
    deadzone: float
    acceleration: float
    condition: frozenset[int] | None


@dataclass(frozen=True)
class ResolvedHotkey:
    """A combination of physical inputs and what it does."""

    codes: frozenset[int]
    action: Action
    cooldown: float
    hold: float = 0.0
    tap: bool = False


@dataclass(frozen=True)
class ResolvedSequence:
    """Physical inputs to press one after the other."""

    codes: tuple[int, ...]
    action: Action
    cooldown: float


@dataclass
class ResolvedProfile:
    """A profile bound to the inputs of one controller."""

    hotkeys: tuple[ResolvedHotkey, ...]
    mouse: tuple[ResolvedAxisMouse, ...]
    scroll: tuple[ResolvedAxisScroll, ...]
    sequences: tuple[ResolvedSequence, ...] = ()

    @property
    def empty(self) -> bool:
        """Tell whether nothing at all is mapped."""
        return not (self.hotkeys or self.sequences or self.mouse or self.scroll)

    def actions(self) -> list[Action]:
        """Every action of the profile, for the virtual devices to declare."""
        return [hotkey.action for hotkey in self.hotkeys] + [
            sequence.action for sequence in self.sequences
        ]


def _resolve_condition(
    condition: tuple[str, ...] | None,
    es_map: ESInputMap,
) -> frozenset[int] | None:
    if not condition:
        return None

    missing = [name for name in condition if name not in es_map]
    if missing:
        raise KeyError(missing)

    return frozenset(input_to_virtual(es_map[name]) for name in condition)


def _shared_codes(es_map: ESInputMap) -> set[int]:
    """Physical inputs that EmulationStation maps to more than one name.

    Without a dedicated hotkey button, ``hotkey`` and ``select`` are the same
    button: a tap on it must not fire, it would hijack the game's input.
    """
    seen: set[int] = set()
    shared: set[int] = set()
    for inp in es_map.values():
        code = input_to_virtual(inp)
        if code in seen:
            shared.add(code)
        seen.add(code)
    return shared


def _resolve_hotkeys(profile: Profile, es_map: ESInputMap) -> list[ResolvedHotkey]:
    hotkeys: dict[tuple[frozenset[int], bool], ResolvedHotkey] = {}
    shared = _shared_codes(es_map)

    for hotkey in profile.hotkeys:
        missing = [name for name in hotkey.trigger if name not in es_map]
        if missing:
            _logger.warning(
                "Hotkey %r: %r not found in emulationstation gamepad settings — ignored.",
                hotkey.trigger,
                missing,
            )
            continue

        codes = frozenset(input_to_virtual(es_map[name]) for name in hotkey.trigger)

        # Combos whose inputs are physically the same one cannot be told apart.
        if len(codes) < len(hotkey.trigger):
            _logger.debug("Ignored combo %r: physical overlap.", hotkey.trigger)
            continue

        if hotkey.tap and codes & shared:
            _logger.info(
                "Tap on %r ignored: that button is also mapped to another input.",
                hotkey.trigger,
            )
            continue

        hotkeys[(codes, hotkey.tap)] = ResolvedHotkey(
            codes=codes,
            action=hotkey.action,
            cooldown=hotkey.cooldown,
            hold=hotkey.hold,
            tap=hotkey.tap,
        )
        _logger.debug(
            "  %s → %s%s",
            " + ".join(hotkey.trigger),
            " + ".join(hex(code) for code in sorted(codes)),
            " (tap)" if hotkey.tap else "",
        )

    return list(hotkeys.values())


def _resolve_sequences(profile: Profile, es_map: ESInputMap) -> list[ResolvedSequence]:
    sequences = []
    for sequence in profile.sequences:
        missing = [name for name in sequence.trigger if name not in es_map]
        if missing:
            _logger.warning(
                "Sequence %r: %r not found in emulationstation gamepad settings — ignored.",
                sequence.trigger,
                missing,
            )
            continue
        sequences.append(
            ResolvedSequence(
                codes=tuple(input_to_virtual(es_map[name]) for name in sequence.trigger),
                action=sequence.action,
                cooldown=sequence.cooldown,
            )
        )
    return sequences


def resolve_profile(profile: Profile, es_map: ESInputMap) -> ResolvedProfile:
    """Bind the input names of a profile to the inputs of one controller."""
    hotkeys = _resolve_hotkeys(profile, es_map)
    sequences = _resolve_sequences(profile, es_map)
    mouse: list[ResolvedAxisMouse] = []
    scroll: list[ResolvedAxisScroll] = []

    # ── Mouse ──────────────────────────────────────────────────────
    for cfg in profile.mouse:
        missing = [name for name in (cfg.axis_x, cfg.axis_y) if name not in es_map]
        if missing:
            _logger.warning(
                "AxisMouse: %r no está en el mapa ES — ignorado.",
                missing,
            )
            continue

        inp_x = es_map[cfg.axis_x]
        inp_y = es_map[cfg.axis_y]

        if not isinstance(inp_x, AxisInput) or not isinstance(inp_y, AxisInput):
            _logger.warning(
                "AxisMouse: '%s'/'%s' must be axis, not buttons.",
                cfg.axis_x,
                cfg.axis_y,
            )
            continue

        try:
            condition = _resolve_condition(cfg.condition, es_map)
        except KeyError as exc:
            _logger.warning("AxisMouse condition: %r no en mapa ES — ignorada.", exc)
            continue

        # Preservo el comportamiento del mapper original:
        # primero normalizaba por el signo ES y luego negaba el resultado.
        mouse.append(
            ResolvedAxisMouse(
                axis_id_x=inp_x.axis_id,
                scale_x=-int(inp_x.value),
                axis_id_y=inp_y.axis_id,
                scale_y=-int(inp_y.value),
                speed=cfg.speed,
                deadzone=cfg.deadzone,
                acceleration=cfg.acceleration,
                condition=condition,
            )
        )

        cond_str = " + ".join(cfg.condition) if cfg.condition else "siempre"
        _logger.debug(
            "  AxisMouse: (%s, %s) speed=%.1f deadzone=%.2f accel=%.2f condición=%s",
            cfg.axis_x,
            cfg.axis_y,
            cfg.speed,
            cfg.deadzone,
            cfg.acceleration,
            cond_str,
        )

    # ── Scroll ─────────────────────────────────────────────────────
    for cfg in profile.scroll:
        names_to_check = [cfg.axis_y] + ([cfg.axis_x] if cfg.axis_x else [])
        missing = [name for name in names_to_check if name not in es_map]
        if missing:
            _logger.warning(
                "AxisScroll: %r no está en el mapa ES — ignorado.",
                missing,
            )
            continue

        inp_y = es_map[cfg.axis_y]
        if not isinstance(inp_y, AxisInput):
            _logger.warning(
                "AxisScroll: '%s' must be an analog axis — ignored.",
                cfg.axis_y,
            )
            continue

        inp_x = None
        if cfg.axis_x:
            inp_x = es_map.get(cfg.axis_x)
            if not isinstance(inp_x, AxisInput):
                _logger.warning(
                    "AxisScroll: '%s' must be an analog axis. X axis ignored.",
                    cfg.axis_x,
                )
                inp_x = None

        try:
            condition = _resolve_condition(cfg.condition, es_map)
        except KeyError as exc:
            _logger.warning("AxisScroll condición: %r no en mapa ES — ignorada.", exc)
            continue

        scroll.append(
            ResolvedAxisScroll(
                axis_id_y=inp_y.axis_id,
                scale_y=int(inp_y.value),
                axis_id_x=inp_x.axis_id if inp_x else None,
                scale_x=int(inp_x.value) if inp_x else None,
                speed=cfg.speed,
                deadzone=cfg.deadzone,
                acceleration=cfg.acceleration,
                condition=condition,
            )
        )

    return ResolvedProfile(
        hotkeys=tuple(hotkeys),
        mouse=tuple(mouse),
        scroll=tuple(scroll),
        sequences=tuple(sequences),
    )
