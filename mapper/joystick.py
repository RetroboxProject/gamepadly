from __future__ import annotations

import logging

from .guid import guid_matches, normalize_guid
from .pygame_backend import pygame

_logger = logging.getLogger(__name__)


def init_pygame() -> None:
    pygame.init()
    pygame.joystick.init()


def quit_pygame() -> None:
    pygame.quit()


def _sdl_guid_str(js: pygame.joystick.Joystick) -> str:
    return normalize_guid(js.get_guid())


def find_joystick(guid: str, sdl_id: int) -> pygame.joystick.Joystick | None:
    matches: list[tuple[int, pygame.joystick.Joystick]] = []

    for i in range(pygame.joystick.get_count()):
        js = pygame.joystick.Joystick(i)
        js.init()

        js_guid = _sdl_guid_str(js)
        _logger.debug("  SDL joystick %d: %s  GUID=%s", i, js.get_name(), js_guid)

        if guid_matches(js_guid, guid):
            matches.append((i, js))
        else:
            js.quit()

    if not matches:
        return None

    selected = next(
        (js for device_index, js in matches if device_index == sdl_id),
        matches[0][1],
    )

    # Cierra los dispositivos coincidentes que no se van a usar.
    for _, js in matches:
        if js is not selected:
            js.quit()

    return selected


def list_gamepads() -> None:
    init_pygame()

    try:
        count = pygame.joystick.get_count()

        if count == 0:
            _logger.error("No gamepads found.")
            _logger.error(
                "Check if your user belongs to the input group: groups $USER | grep -w 'input'"
            )
            _logger.error(
                "If not, then run: sudo usermod -aG input $USER . After that, reboot your PC"
            )
            return

        guid_counters: dict[str, int] = {}

        for i in range(count):
            js = pygame.joystick.Joystick(i)
            js.init()

            guid = _sdl_guid_str(js)
            sdl_id = guid_counters.get(guid, 0)
            guid_counters[guid] = sdl_id + 1

            _logger.info("Nombre   : %s", js.get_name())
            _logger.info("GUID     : %s  ← usa este en --guid", guid)
            _logger.info("sdl_id   : %d", sdl_id)
            _logger.info(
                "Botones  : %d  Ejes: %d  Hats: %d",
                js.get_numbuttons(),
                js.get_numaxes(),
                js.get_numhats(),
            )
            _logger.info("")

            js.quit()

    finally:
        quit_pygame()