"""Main loop of a mapper: read one controller, fire its mappings."""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .actions import reap_children
from .ecodes import ec
from .guid import normalize_guid
from .inputs import AXIS_THRESHOLD, axis_code, button_code, hat_code
from .profile import TAP_MAX_SECONDS
from .pygame_backend import pygame
from .uinput_backend import build_uinput

if TYPE_CHECKING:
    from .resolver import ResolvedHotkey, ResolvedProfile
    from .uinput_backend import UInputPair

_logger = logging.getLogger(__name__)

LOOP_HZ = 200
LOOP_DT = 1.0 / LOOP_HZ
REAP_EVERY = LOOP_HZ
"""Loop iterations between two checks for finished ``exec`` commands."""


def apply_curve(value: float, deadzone: float, acceleration: float) -> float:
    """Map a stick value to [-1, 1] past the deadzone, with an acceleration curve."""
    if abs(value) <= deadzone or deadzone >= 1.0:
        return 0.0
    normalized = (abs(value) - deadzone) / (1.0 - deadzone)
    normalized = max(0.0, min(1.0, normalized))
    return math.copysign(normalized**acceleration, value)


@dataclass
class _HotkeyState:
    """What the inputs held so far have started."""

    pressed: set[int] = field(default_factory=set)
    # combos fired whose action is held down until one of their inputs is released
    active: dict[frozenset[int], ResolvedHotkey] = field(default_factory=dict)
    # combos waiting for their hold time, with the moment they became complete
    pending: dict[frozenset[int], tuple[ResolvedHotkey, float]] = field(default_factory=dict)
    # tap inputs pressed alone so far, with the moment they were pressed
    armed_taps: dict[int, float] = field(default_factory=dict)
    last_fired: dict[object, float] = field(default_factory=dict)
    sequence_progress: list[int] = field(default_factory=list)


@dataclass
class _StickState:
    """Analog and hat state, plus the sub-unit motion carried between ticks."""

    hat_active: dict[tuple[int, int], int] = field(default_factory=dict)
    axis_active: dict[tuple[int, int], int] = field(default_factory=dict)
    axis_values: dict[int, float] = field(default_factory=dict)
    mouse_accum: list[float] = field(default_factory=lambda: [0.0, 0.0])
    scroll_accum: list[float] = field(default_factory=lambda: [0.0, 0.0])


class MapperEngine:
    """Turn the events of one controller into the actions of its profile."""

    def __init__(
        self,
        joystick: pygame.joystick.Joystick,
        resolved: ResolvedProfile,
        player: int,
    ) -> None:
        self.joystick = joystick
        self.resolved = resolved
        self.player = player

        self.state = _HotkeyState(sequence_progress=[0] * len(resolved.sequences))
        self.sticks = _StickState()

        # longest combinations first: Hotkey+Start wins over Start alone
        self.combos = sorted(
            (hotkey for hotkey in resolved.hotkeys if not hotkey.tap),
            key=lambda hotkey: len(hotkey.codes),
            reverse=True,
        )
        self.taps = {
            next(iter(hotkey.codes)): hotkey for hotkey in resolved.hotkeys if hotkey.tap
        }

    def run(self) -> None:
        """Process events until the controller is unplugged."""
        ui = build_uinput(self.resolved, self.player)

        _logger.info(
            "Listening to '%s'  GUID=%s",
            self.joystick.get_name(),
            normalize_guid(self.joystick.get_guid()),
        )
        _logger.info(
            "%d hotkey(s)  %d sequence(s)  %d mouse axis  %d scroll axis",
            len(self.resolved.hotkeys),
            len(self.resolved.sequences),
            len(self.resolved.mouse),
            len(self.resolved.scroll),
        )

        last_tick = time.monotonic()
        iterations = 0
        try:
            while True:
                now = time.monotonic()
                dt = now - last_tick
                last_tick = now

                if any(self._handle_event(event, ui) for event in pygame.event.get()):
                    return

                self.tick(now, ui)
                if self.resolved.mouse:
                    self._tick_mouse(dt, ui)
                if self.resolved.scroll:
                    self._tick_scroll(dt, ui)

                iterations += 1
                if iterations % REAP_EVERY == 0:
                    reap_children()

                sleep_time = LOOP_DT - (time.monotonic() - now)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            pass

        finally:
            ui.close()

    # ── input events ──────────────────────────────────────────────────

    def _handle_event(self, event, ui: UInputPair) -> bool:
        """Process one pygame event; return True when the controller is gone."""
        now = time.monotonic()

        if event.type == pygame.JOYBUTTONDOWN:
            self.press(button_code(event.button), now, ui)
        elif event.type == pygame.JOYBUTTONUP:
            self.release(button_code(event.button), now, ui)
        elif event.type == pygame.JOYHATMOTION:
            self._handle_hat(event, now, ui)
        elif event.type == pygame.JOYAXISMOTION:
            self._handle_axis(event, now, ui)
        elif event.type == pygame.JOYDEVICEREMOVED:
            if event.instance_id == self.joystick.get_instance_id():
                _logger.warning("JOYDEVICEREMOVED — active controller unplugged.")
                return True
            _logger.debug(
                "JOYDEVICEREMOVED — another controller (instance_id=%s), ignored.",
                event.instance_id,
            )
        return False

    def _handle_hat(self, event, now: float, ui: UInputPair) -> None:
        key_hat = (event.joy, event.hat)
        previous = self.sticks.hat_active.pop(key_hat, None)
        if previous is not None:
            self.release(previous, now, ui)

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
            self.sticks.hat_active[key_hat] = new
            self.press(new, now, ui)

    def _handle_axis(self, event, now: float, ui: UInputPair) -> None:
        self.sticks.axis_values[event.axis] = event.value

        key_axis = (event.joy, event.axis)
        previous = self.sticks.axis_active.pop(key_axis, None)

        if event.value > AXIS_THRESHOLD:
            new = axis_code(event.axis, positive=True)
        elif event.value < -AXIS_THRESHOLD:
            new = axis_code(event.axis, positive=False)
        else:
            new = None

        if previous is not None and previous != new:
            self.release(previous, now, ui)
        if new is not None:
            self.sticks.axis_active[key_axis] = new
            if new != previous:
                self.press(new, now, ui)

    # ── hotkeys ───────────────────────────────────────────────────────

    def press(self, code: int, now: float, ui: UInputPair) -> None:
        """An input became active."""
        state = self.state
        state.pressed.add(code)

        # a tap is only a tap if nothing else is pressed while it is held
        for armed in [armed for armed in state.armed_taps if armed != code]:
            del state.armed_taps[armed]
        if code in self.taps:
            state.armed_taps[code] = now

        self._advance_sequences(code, now, ui)

        best = next(
            (
                hotkey
                for hotkey in self.combos
                if code in hotkey.codes
                and hotkey.codes <= state.pressed
                and hotkey.codes not in state.active
                and hotkey.codes not in state.pending
            ),
            None,
        )
        if best is None:
            return
        if best.hold > 0:
            state.pending[best.codes] = (best, now)
        else:
            self._fire(best, now, ui)

    def release(self, code: int, now: float, ui: UInputPair) -> None:
        """An input stopped being active."""
        state = self.state
        state.pressed.discard(code)

        armed_at = state.armed_taps.pop(code, None)
        if armed_at is not None and now - armed_at <= TAP_MAX_SECONDS:
            tap = self.taps[code]
            if self._cooled_down(tap.codes, tap.cooldown, now):
                _logger.debug("● tap %s", hex(code))
                tap.action.press_down(ui)
                tap.action.press_up(ui)

        for codes in [codes for codes in state.active if code in codes]:
            _logger.debug("▲ %s", " + ".join(hex(c) for c in sorted(codes)))
            state.active.pop(codes).action.press_up(ui)

        for codes in [codes for codes in state.pending if code in codes]:
            del state.pending[codes]

    def tick(self, now: float, ui: UInputPair) -> None:
        """Fire the combinations that have been held long enough."""
        for codes, (hotkey, since) in list(self.state.pending.items()):
            if not codes <= self.state.pressed:
                del self.state.pending[codes]
            elif now - since >= hotkey.hold:
                del self.state.pending[codes]
                self._fire(hotkey, now, ui)

    def _cooled_down(self, key: object, cooldown: float, now: float) -> bool:
        """Tell whether a mapping may fire, and record that it does."""
        last = self.state.last_fired.get(key)
        if last is not None and now - last < cooldown:
            return False
        self.state.last_fired[key] = now
        return True

    def _fire(self, hotkey: ResolvedHotkey, now: float, ui: UInputPair) -> None:
        if not self._cooled_down(hotkey.codes, hotkey.cooldown, now):
            return
        # the inputs of a combination are not taps any more
        for code in hotkey.codes:
            self.state.armed_taps.pop(code, None)

        _logger.debug("▼ %s", " + ".join(hex(code) for code in sorted(hotkey.codes)))
        self.state.active[hotkey.codes] = hotkey
        hotkey.action.press_down(ui)

    def _advance_sequences(self, code: int, now: float, ui: UInputPair) -> None:
        """Follow every sequence with the input just pressed (evmapy semantics)."""
        progress = self.state.sequence_progress
        for index, sequence in enumerate(self.resolved.sequences):
            if code == sequence.codes[progress[index]]:
                progress[index] += 1
            else:
                progress[index] = 1 if code == sequence.codes[0] else 0

            if progress[index] == len(sequence.codes):
                progress[index] = 0
                if self._cooled_down(("sequence", index), sequence.cooldown, now):
                    _logger.debug("▶ sequence #%d", index)
                    sequence.action.press_down(ui)
                    sequence.action.press_up(ui)

    # ── analog sticks ─────────────────────────────────────────────────

    def _condition_held(self, condition: frozenset[int] | None) -> bool:
        return condition is None or condition <= self.state.pressed

    def _tick_mouse(self, dt: float, ui: UInputPair) -> None:
        values = self.sticks.axis_values
        accum = self.sticks.mouse_accum

        for cfg in self.resolved.mouse:
            if not self._condition_held(cfg.condition):
                continue
            raw_x = values.get(cfg.axis_id_x, 0.0) * cfg.scale_x
            raw_y = values.get(cfg.axis_id_y, 0.0) * cfg.scale_y
            accum[0] += apply_curve(raw_x, cfg.deadzone, cfg.acceleration) * cfg.speed * dt
            accum[1] += apply_curve(raw_y, cfg.deadzone, cfg.acceleration) * cfg.speed * dt

        ix, iy = int(accum[0]), int(accum[1])
        if ix or iy:
            accum[0] -= ix
            accum[1] -= iy
            if ix:
                ui.write_rel(ec.REL_X, ix)
            if iy:
                ui.write_rel(ec.REL_Y, iy)
            ui.syn(has_mouse=True)

    def _tick_scroll(self, dt: float, ui: UInputPair) -> None:
        values = self.sticks.axis_values
        accum = self.sticks.scroll_accum

        for cfg in self.resolved.scroll:
            if not self._condition_held(cfg.condition):
                continue
            raw_y = values.get(cfg.axis_id_y, 0.0) * cfg.scale_y
            raw_x = 0.0
            if cfg.axis_id_x is not None and cfg.scale_x is not None:
                raw_x = values.get(cfg.axis_id_x, 0.0) * cfg.scale_x
            accum[0] += apply_curve(raw_x, cfg.deadzone, cfg.acceleration) * cfg.speed * dt
            accum[1] += apply_curve(raw_y, cfg.deadzone, cfg.acceleration) * cfg.speed * dt

        ix, iy = int(accum[0]), int(accum[1])
        if ix or iy:
            accum[0] -= ix
            accum[1] -= iy
            if iy:
                ui.write_rel(ec.REL_WHEEL, iy)
            if ix:
                ui.write_rel(ec.REL_HWHEEL, ix)
            ui.syn(has_mouse=True)
