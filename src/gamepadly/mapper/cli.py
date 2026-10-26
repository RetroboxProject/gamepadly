from __future__ import annotations

import argparse
import logging

from .exceptions import GamepadlyError

_logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gamepadly-mapper",
        description="Gamepad hotkey mapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ejemplos:
  %(prog)s --list
  %(prog)s --guid 050000007e0500000920000001800000 --sdl_id 0 \\
           --es-input ~/.emulationstation/es_input.cfg
  %(prog)s --guid 050000007e0500000920000001800000 --sdl_id 0 \\
           --es-input ~/.emulationstation/es_input.cfg --profile hotkeys.json
""",
    )

    parser.add_argument("--list", action="store_true")
    parser.add_argument("--guid", metavar="GUID")
    parser.add_argument(
        "--sdl_id",
        metavar="N",
        type=int,
        default=0,
        help="SDL index - needed when there are two or more gamepads with same GUID (0-based).",
    )
    parser.add_argument(
        "--player",
        metavar="N",
        type=int,
        default=1,
        help="EmulationStation player number (1, 2, 3...): selects actions_playerN in profile.",
    )
    parser.add_argument("--es-input", metavar="ARCHIVO")
    parser.add_argument(
        "--profile",
        metavar="ARCHIVO",
        help="JSON profile for hotkeys. evmapy profiles can be used."
    )
    parser.add_argument("--debug", action="store_true")

    return parser


def setup_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.debug)

    try:
        if args.list:
            from .joystick import list_gamepads

            list_gamepads()
            return 0

        if not args.guid:
            parser.error("Se requiere --guid")

        if not args.es_input:
            parser.error("Se requiere --es-input")

        from .runner import run_mapper

        run_mapper(
            guid=args.guid,
            sdl_id=args.sdl_id,
            player=args.player,
            es_input=args.es_input,
            profile_path=args.profile,
        )

        return 0

    except GamepadlyError as exc:
        _logger.error("%s", exc)
        return 1

    except KeyboardInterrupt:
        _logger.info("Stopped by user.")
        return 0
