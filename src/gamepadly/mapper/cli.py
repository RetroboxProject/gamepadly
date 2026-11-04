"""Command line of the mapper (``gamepadly-mapper``, ``python3 -m gamepadly.mapper``)."""

from __future__ import annotations

import argparse
import logging

from .exceptions import GamepadlyError

_logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """The argument parser of the mapper."""
    parser = argparse.ArgumentParser(
        prog="gamepadly-mapper",
        description="Gamepad hotkey mapper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  %(prog)s --list
  %(prog)s --guid 050000007e0500000920000001800000 --sdl_id 0 \\
           --es-input ~/.emulationstation/es_input.cfg
  %(prog)s --guid 050000007e0500000920000001800000 --sdl_id 0 \\
           --es-input ~/.emulationstation/es_input.cfg --profile hotkeys.json
  %(prog)s --keyboard --profile hotkeys.json
""",
    )

    parser.add_argument("--list", action="store_true", help="List the connected gamepads.")
    parser.add_argument(
        "--keyboard",
        action="store_true",
        help="Watch every keyboard and fire the profile's actions_keyboard mappings "
        "(needs --profile; --guid and --es-input are not used).",
    )
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
    parser.add_argument("--es-input", metavar="FILE")
    parser.add_argument(
        "--profile",
        metavar="FILE",
        help="JSON profile for hotkeys. evmapy profiles can be used.",
    )
    parser.add_argument("--debug", action="store_true")

    return parser


def setup_logging(debug: bool) -> None:
    """Log to stderr, with DEBUG messages when asked."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the exit status."""
    parser = build_parser()
    args = parser.parse_args(argv)

    setup_logging(args.debug)

    # pygame and evdev are only imported for the mode that needs them
    # pylint: disable=import-outside-toplevel
    try:
        if args.list:
            from .joystick import list_gamepads

            list_gamepads()
            return 0

        if args.keyboard:
            if not args.profile:
                parser.error("--keyboard needs --profile")
            from .runner import run_keyboard

            run_keyboard(args.profile)
            return 0

        if not args.guid:
            parser.error("--guid is required")

        if not args.es_input:
            parser.error("--es-input is required")

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
