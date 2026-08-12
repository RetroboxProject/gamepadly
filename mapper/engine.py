from __future__ import annotations

import logging
import math
import time

from .ecodes import ec
from .guid import normalize_guid
from .inputs import AXIS_THRESHOLD, axis_code, button_code, hat_code
from .pygame_backend import pygame
from .resolver import ResolvedProfile
from .uinput_backend import build_uinput

_logger = logging.getLogger(__name__)

LOOP_HZ = 200
LOOP_DT = 1.0 / LOOP_HZ


def apply_curve(value: float, deadzone: float, acceleration: float) -> float:
    if abs(value) <= deadzone:
        return 0.0

    if deadzone >= 1.0:
        return 0.0

    normalized = (abs(value) - deadzone) / (1.0 - deadzone)
    normalized = max(0.0, min(1.0, normalized))

    return math.copysign(normalized**acceleration, value)


class MapperEngine:
    def __init__(
        self,
        joystick: pygame.joystick.Joystick,
        resolved: ResolvedProfile,
        player: int,
    ) -> None:
        self.joystick = joystick
        self.resolved = resolved
        self.player = player

        self.pressed: set[int] = set()
        self.active_combos: set[frozenset[int]] = set()
        self.active_holds: dict[frozenset[int], object] = {}
        self.last_fired: dict[frozenset[int], float] = {}

        self.hat_active: dict[tuple[int, int], int] = {}
        self.axis_active: dict[tuple[int, int], int] = {}
        self.axis_values: dict[int, float] = {}

        self.mouse_accum_x = 0.0
        self.mouse_accum_y = 0.0

        self.scroll_accum_x = 0.0
        self.scroll_accum_y = 0.0

        # Combos más largos primero.
        self.hotkeys_by_priority = sorted(
            resolved.hotkeys,
            key=len,
            reverse=True,
        )

    def run(self) -> None:
        ui = build_uinput(self.resolved, self.player)

        _logger.info(
            "Escuchando '%s'  GUID=%s",
            self.joystick.get_name(),
            normalize_guid(self.joystick.get_guid()),
        )
        _logger.info(
            "%d hotkey(s)  %d eje(s) de ratón  %d eje(s) de scroll",
            len(self.resolved.hotkeys),
            len(self.resolved.mouse),
            len(self.resolved.scroll),
        )

        last_tick = time.monotonic()

        try:
            while True:
                now = time.monotonic()
                dt = now - last_tick
                last_tick = now

                removed = False

                for event in pygame.event.get():
                    if self._handle_event(event, ui):
                        removed = True
                        break

                if removed:
                    return

                if self.resolved.mouse:
                    self._tick_mouse(dt, ui)

                if self.resolved.scroll:
                    self._tick_scroll(dt, ui)

                elapsed = time.monotonic() - now
                sleep_time = LOOP_DT - elapsed

                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            pass

        finally:
            ui.close()

    def _handle_event(self, event, ui) -> bool:
        if event.type == pygame.JOYBUTTONDOWN:
            self.pressed.add(button_code(event.button))
            self._check_and_press(ui)
            return False

        if event.type == pygame.JOYBUTTONUP:
            self._release(button_code(event.button), ui)
            return False

        if event.type == pygame.JOYHATMOTION:
            self._handle_hat(event, ui)
            return False

        if event.type == pygame.JOYAXISMOTION:
            self._handle_axis(event, ui)
            return False

        if event.type == pygame.JOYDEVICEREMOVED:
            if event.instance_id == self.joystick.get_instance_id():
                _logger.warning(
                    "JOYDEVICEREMOVED — mando activo desconectado, saliendo del loop."
                )
                return True

            _logger.debug(
                "JOYDEVICEREMOVED — mando ajeno (instance_id=%s), ignorado.",
                event.instance_id,
            )
            return False

        return False

    def _check_and_press(self, ui) -> None:
        now = time.monotonic()

        best = next(
            (
                combo
                for combo in self.hotkeys_by_priority
                if combo.issubset(self.pressed)
                and combo not in self.active_combos
            ),
            None,
        )

        if best is None:
            return

        cooldown = self.resolved.cooldowns.get(best, 0.0)
        if now - self.last_fired.get(best, 0.0) < cooldown:
            return

        self.last_fired[best] = now
        self.active_combos.add(best)

        action = self.resolved.hotkeys[best]
        _logger.debug("▼ %s", " + ".join(hex(code) for code in sorted(best)))

        action.press_down(ui)
        self.active_holds[best] = action

    def _release(self, code: int, ui) -> None:
        self.pressed.discard(code)

        to_release = {
            combo
            for combo in self.active_combos
            if code in combo
        }

        for combo in to_release:
            action = self.active_holds.pop(combo, None)
            if action is not None:
                _logger.debug("▲ %s", " + ".join(hex(c) for c in sorted(combo)))
                action.press_up(ui)

        self.active_combos.difference_update(to_release)

    def _handle_hat(self, event, ui) -> None:
        key_hat = (event.joy, event.hat)

        previous = self.hat_active.pop(key_hat, None)
        if previous is not None:
            self._release(previous, ui)

        hx, hy = event.value

        if hx == 1:
            new = hat_code(event.hat, 2)
        elif hx == -1:
            new = hat_code(event.hat, 8)
        elif hy == 1:
            new = hat_code(event.hat, 1)
        elif hy == -1:
            new = hat_code(event.hat, 4)
        else:
            new = None

        if new is not None:
            self.hat_active[key_hat] = new
            self.pressed.add(new)
            self._check_and_press(ui)

    def _handle_axis(self, event, ui) -> None:
        self.axis_values[event.axis] = event.value

        key_axis = (event.joy, event.axis)

        previous = self.axis_active.pop(key_axis, None)
        if previous is not None:
            self._release(previous, ui)

        value = event.value

        if value > AXIS_THRESHOLD:
            new = axis_code(event.axis, positive=True)
        elif value < -AXIS_THRESHOLD:
            new = axis_code(event.axis, positive=False)
        else:
            new = None

        if new is not None:
            self.axis_active[key_axis] = new
            self.pressed.add(new)
            self._check_and_press(ui)

    def _tick_mouse(self, dt: float, ui) -> None:
        total_dx = 0.0
        total_dy = 0.0

        for cfg in self.resolved.mouse:
            if cfg.condition is not None and not cfg.condition.issubset(self.pressed):
                continue

            raw_x = self.axis_values.get(cfg.axis_id_x, 0.0) * cfg.scale_x
            raw_y = self.axis_values.get(cfg.axis_id_y, 0.0) * cfg.scale_y

            total_dx += apply_curve(raw_x, cfg.deadzone, cfg.acceleration) * cfg.speed * dt
            total_dy += apply_curve(raw_y, cfg.deadzone, cfg.acceleration) * cfg.speed * dt

        self.mouse_accum_x += total_dx
        self.mouse_accum_y += total_dy

        ix = int(self.mouse_accum_x)
        iy = int(self.mouse_accum_y)

        if ix or iy:
            self.mouse_accum_x -= ix
            self.mouse_accum_y -= iy

            if ix:
                ui.write_rel(ec.REL_X, ix)

            if iy:
                ui.write_rel(ec.REL_Y, iy)

            ui.syn(has_mouse=True)

    def _tick_scroll(self, dt: float, ui) -> None:
        for cfg in self.resolved.scroll:
            if cfg.condition is not None and not cfg.condition.issubset(self.pressed):
                continue

            raw_y = self.axis_values.get(cfg.axis_id_y, 0.0) * cfg.scale_y

            raw_x = 0.0
            if cfg.axis_id_x is not None and cfg.scale_x is not None:
                raw_x = self.axis_values.get(cfg.axis_id_x, 0.0) * cfg.scale_x

            self.scroll_accum_y += (
                apply_curve(raw_y, cfg.deadzone, cfg.acceleration)
                * cfg.speed
                * dt
            )
            self.scroll_accum_x += (
                apply_curve(raw_x, cfg.deadzone, cfg.acceleration)
                * cfg.speed
                * dt
            )

        iy = int(self.scroll_accum_y)
        ix = int(self.scroll_accum_x)

        if iy or ix:
            self.scroll_accum_y -= iy
            self.scroll_accum_x -= ix

            if iy:
                ui.write_rel(ec.REL_WHEEL, iy)

            if ix:
                ui.write_rel(ec.REL_HWHEEL, ix)

            ui.syn(has_mouse=True)