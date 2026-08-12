from __future__ import annotations

import logging
from dataclasses import dataclass

from .actions import Action
from .inputs import AxisInput, ESInputMap, input_to_virtual
from .profile import Profile

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedAxisMouse:
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
    axis_id_y: int
    scale_y: int
    axis_id_x: int | None
    scale_x: int | None
    speed: float
    deadzone: float
    acceleration: float
    condition: frozenset[int] | None


@dataclass
class ResolvedProfile:
    hotkeys: dict[frozenset[int], Action]
    cooldowns: dict[frozenset[int], float]
    mouse: tuple[ResolvedAxisMouse, ...]
    scroll: tuple[ResolvedAxisScroll, ...]

    @property
    def empty(self) -> bool:
        return not (self.hotkeys or self.mouse or self.scroll)


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


def resolve_profile(profile: Profile, es_map: ESInputMap) -> ResolvedProfile:
    hotkeys: dict[frozenset[int], Action] = {}
    cooldowns: dict[frozenset[int], float] = {}
    mouse: list[ResolvedAxisMouse] = []
    scroll: list[ResolvedAxisScroll] = []

    # ── Hotkeys ────────────────────────────────────────────────────
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

        # Evita combos que colapsan físicamente en el mismo input.
        if len(codes) < len(hotkey.trigger):
            _logger.debug(
                "Ignored combo %r: physical overlap.",
                hotkey.trigger,
            )
            continue

        hotkeys[codes] = hotkey.action
        cooldowns[codes] = hotkey.cooldown

        _logger.debug(
            "  %s → %s",
            " + ".join(hotkey.trigger),
            " + ".join(hex(code) for code in sorted(codes)),
        )

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
        hotkeys=hotkeys,
        cooldowns=cooldowns,
        mouse=tuple(mouse),
        scroll=tuple(scroll),
    )