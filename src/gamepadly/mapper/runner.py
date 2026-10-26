from __future__ import annotations

import logging
import signal
import time

from .defaults import default_profile
from .engine import MapperEngine
from .es_input import parse_es_input
from .exceptions import GamepadlyError
from .joystick import find_joystick, init_pygame, quit_pygame
from .profile import load_profile
from .pygame_backend import pygame
from .resolver import resolve_profile

_logger = logging.getLogger(__name__)

RECONNECT_INTERVAL = 2.0


def _install_signal_handlers() -> None:
    def _signal_handler(signum, frame):
        raise SystemExit(0)

    try:
        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
    except ValueError:
        # No estamos en el hilo principal.
        pass


def run_mapper(
    guid: str,
    sdl_id: int,
    player: int,
    es_input: str,
    profile_path: str | None = None,
) -> None:
    _install_signal_handlers()
    init_pygame()

    try:
        if profile_path:
            profile = load_profile(profile_path, player=player)
        else:
            _logger.info("--profile not specified, using default profile.")
            profile = default_profile()

        es_map = parse_es_input(es_input, guid)
        resolved = resolve_profile(profile, es_map)

        if resolved.empty:
            raise GamepadlyError("No actions resolved.")

        first_attempt = True

        while True:
            joystick = find_joystick(guid, sdl_id)

            if joystick is None:
                if first_attempt:
                    _logger.warning(
                        "Mando GUID=%s not found. Waiting for connection...",
                        guid,
                    )
                    first_attempt = False

                pygame.event.pump()
                time.sleep(RECONNECT_INTERVAL)
                continue

            first_attempt = True

            _logger.info(
                "Mando conectado: '%s' (player=%d, sdl_id=%d)",
                joystick.get_name(),
                player,
                sdl_id,
            )

            try:
                engine = MapperEngine(
                    joystick=joystick,
                    resolved=resolved,
                    player=player,
                )
                engine.run()
            except GamepadlyError:
                raise
            except Exception:
                _logger.exception("Unexpected error.")
            finally:
                try:
                    joystick.quit()
                except Exception:
                    pass

            _logger.warning("Gamepad was unplugged, waiting reconnection...")
            pygame.event.pump()
            time.sleep(RECONNECT_INTERVAL)

    except SystemExit:
        _logger.info("Stopped by EXIT signal")

    finally:
        quit_pygame()
