"""
GamepadManager — context manager que lanza/mata instancias del mapper
por cada controller activo, usando el mismo sistema de búsqueda de perfiles
que evmapy de Batocera.

Jerarquía de búsqueda de perfiles (primer match gana):

    {rom}.keys                              ← override por juego
    profiles/{system}.{emulator}.{core}.keys
    profiles/{system}.{emulator}.keys
    profiles/{system}.keys
    profiles/{emulator}.keys
    profiles/any.keys                       ← fallback global

Este módulo no depende de ningún proyecto concreto: los directorios de
perfiles y el es_input.cfg los recibe por parámetro, y el mapper se lanza
como `python -m gamepadly.mapper` (o con el comando que se indique en
`mapper_command`). Los controllers son cualquier objeto con los atributos de
`Controller`.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Iterator, Protocol

if TYPE_CHECKING:
    from types import TracebackType

_logger = logging.getLogger(__name__)

KEYBOARD_SECTION = "actions_keyboard"
"""Profile section of the keyboard hotkeys (see ``mapper.keyboard``)."""

DEFAULT_MAPPER_COMMAND: tuple[str, ...] = (sys.executable, "-m", "gamepadly.mapper")


def mapper_log(what: str) -> Path:
    """Where a mapper process logs (``keyboards``, ``player 1``...), started
    afresh with it: ``$XDG_STATE_HOME/gamepadly/``."""
    state = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return state / "gamepadly" / f"{what.replace(' ', '-')}.log"


class Controller(Protocol):  # pylint: disable=too-few-public-methods
    """What the manager needs to know about a controller."""

    guid: str
    index: int
    player_number: int


Controllers = Iterable[Controller]


def _profile_names(system: str, emulator: str, core: str) -> tuple[str, ...]:
    return (
        f"{system}.{emulator}.{core}.keys",
        f"{system}.{emulator}.keys",
        f"{system}.keys",
        f"{emulator}.keys",
        "any.keys",
    )


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def _profile_candidates(
    rom: Path,
    system: str,
    emulator: str,
    core: str,
    profiles_dir: Path,
    user_profiles_dir: Path,
) -> Iterator[Path]:
    # Override por juego.
    #
    # Si el ROM es un directorio, mantengo compatibilidad con el nombre
    # legado "pad2.keys", pero también intento buscar "{rom.name}.keys".
    if rom.is_dir():
        yield rom / f"{rom.name}.keys"
        yield rom / "pad2.keys"
    else:
        yield rom.parent / f"{rom.name}.keys"

    # Perfiles de usuario primero, luego perfiles del sistema.
    for base in (user_profiles_dir, profiles_dir):
        for name in _profile_names(system, emulator, core):
            yield base / name


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def find_profile(
    rom: Path,
    system: str,
    emulator: str,
    core: str,
    profiles_dir: Path,
    user_profiles_dir: Path,
) -> Path | None:
    """Return the first existing profile of the lookup order, or None."""
    for path in _profile_candidates(
        rom, system, emulator, core, profiles_dir, user_profiles_dir
    ):
        _logger.debug("gamepadly: comprobando perfil de mando en %s", path)
        if path.exists():
            _logger.debug("gamepadly: perfil → %s", path)
            return path

    _logger.debug(
        "gamepadly: sin perfil para system=%s emulator=%s core=%s",
        system,
        emulator,
        core,
    )
    return None


def _has_keyboard_mappings(profile: Path) -> bool:
    """Tell whether the profile has a non-empty ``actions_keyboard`` section."""
    try:
        data = json.loads(profile.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and bool(data.get(KEYBOARD_SECTION))


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return

    # El mapper se lanza con start_new_session=True, por lo que podemos
    # matar el grupo de procesos si hiciera falta.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except OSError:
            try:
                proc.send_signal(sig)
            except OSError:
                pass

        try:
            proc.wait(timeout=3 if sig == signal.SIGTERM else 1)
            return
        except subprocess.TimeoutExpired:
            continue


@dataclass
class GamepadManager(AbstractContextManager):
    """Run one mapper per active controller while the context is open.

    Nothing is started when no ``.keys`` profile is found. ``profiles_dir``,
    ``user_profiles_dir`` and ``es_input`` are resolved by the caller: the
    manager knows nothing about where the applications using it live.
    ``mapper_command`` is the command that starts a mapper (this package's
    by default).

    ``profile`` skips the lookup: the caller hands over the profile to use
    (e.g. one it has composed for this session), and the lookup directories
    are not used.
    """

    system: str
    emulator: str
    core: str
    rom: Path
    controllers: Controllers
    profiles_dir: Path
    user_profiles_dir: Path
    es_input: Path
    mapper_command: tuple[str, ...] = DEFAULT_MAPPER_COMMAND
    profile: Path | None = None

    _processes: list[subprocess.Popen] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __enter__(self) -> "GamepadManager":
        self._stop_all()

        profile = self.profile
        if profile is not None and not profile.exists():
            _logger.warning("gamepadly: profile not found: %s", profile)
            return self
        if profile is None:
            profile = find_profile(
                rom=self.rom,
                system=self.system,
                emulator=self.emulator,
                core=self.core,
                profiles_dir=self.profiles_dir,
                user_profiles_dir=self.user_profiles_dir,
            )
        if profile is None:
            return self

        if _has_keyboard_mappings(profile):
            self._start(["--keyboard", "--profile", str(profile)], "keyboards")

        if not self.es_input.exists():
            _logger.warning("gamepadly: es_input not found en %s", self.es_input)
            return self

        for controller in self.controllers:
            # joysticks only: keyboards are all watched by the keyboard mapper
            if getattr(controller, "type", "joystick") == "keyboard":
                continue

            self._launch(controller, profile, self.es_input)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._stop_all()

    def _launch(
        self,
        controller: Controller,
        profile: Path,
        es_input: Path,
    ) -> None:
        guid = controller.guid
        index = controller.index
        player = controller.player_number

        if not guid:
            _logger.warning(
                "gamepadly: controller without GUID (player=%d), skipping",
                player,
            )
            return

        _logger.info(
            "gamepadly: player=%d guid=%s sdl_id=%d perfil=%s",
            player,
            guid,
            index,
            profile.name,
        )
        self._start(
            [
                "--guid", guid,
                "--sdl_id", str(index),
                "--player", str(player),
                "--es-input", str(es_input),
                "--profile", str(profile),
            ],
            f"player {player}",
        )

    def _start(self, args: list[str], what: str) -> None:
        """Start one mapper process with these arguments."""
        cmd = [*self.mapper_command, *args]
        _logger.debug("gamepadly: %s: cmd=%s", what, " ".join(cmd))

        log = mapper_log(what)
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            # the child keeps its own copy of the descriptor
            with log.open("wb") as output:
                # pylint: disable-next=consider-using-with  # owned by _stop_all()
                proc = subprocess.Popen(
                    cmd,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
        except OSError as exc:
            _logger.error("gamepadly: error launching mapper: %s", exc)
            return

        self._processes.append(proc)
        _logger.debug("gamepadly: PID %d launched", proc.pid)

    def _stop_all(self) -> None:
        for proc in self._processes:
            _logger.debug("gamepadly: ended PID %d", proc.pid)
            _terminate_process(proc)

        self._processes.clear()
