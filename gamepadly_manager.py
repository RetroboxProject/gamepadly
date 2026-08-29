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

Este módulo no importa nada de runtime.paths: todos los paths
(mapper_script, profiles_dir, user_profiles_dir, es_input) los recibe por
parámetro. Es responsabilidad del caller (emulatorlauncher.py) resolverlos
y pasarlos. Así gamepadly queda igual de autocontenido que su propio motor
(runtime/gamepadly/mapper/*), que ya recibe todo por CLI y no depende de
retrobox_paths.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from types import TracebackType
    from runtime.launcher.configgen.controller import Controller, Controllers

_logger = logging.getLogger(__name__)


def _profile_names(system: str, emulator: str, core: str) -> tuple[str, ...]:
    return (
        f"{system}.{emulator}.{core}.keys",
        f"{system}.{emulator}.keys",
        f"{system}.keys",
        f"{emulator}.keys",
        "any.keys",
    )

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

def find_profile(
    rom: Path,
    system: str,
    emulator: str,
    core: str,
    profiles_dir: Path,
    user_profiles_dir: Path,
) -> Path | None:
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
    """
    Lanza una instancia del mapper por cada controller joystick activo
    y las termina al salir del contexto.

    Si no se encuentra ningún perfil .keys, no lanza nada.

    mapper_script, profiles_dir, user_profiles_dir y es_input son los
    únicos puntos de contacto con el resto de Retrobox: los resuelve el
    caller (típicamente desde runtime.paths) y se los pasa a
    este constructor. GamepadManager en sí no sabe nada de dónde vive
    Retrobox instalado.
    """

    system: str
    emulator: str
    core: str
    rom: Path
    controllers: "Controllers"
    mapper_script: Path
    profiles_dir: Path
    user_profiles_dir: Path
    es_input: Path

    _processes: list[subprocess.Popen] = field(
        default_factory=list,
        init=False,
        repr=False,
    )

    def __enter__(self) -> "GamepadManager":
        self._stop_all()

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

        if not self.es_input.exists():
            _logger.warning("gamepadly: es_input not found en %s", self.es_input)
            return self

        for controller in self.controllers:
            # Solo joysticks, no teclados.
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
        controller: "Controller",
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

        cmd = [
            sys.executable,
            str(self.mapper_script),
            "--guid", guid,
            "--sdl_id", str(index),
            "--player", str(player),
            "--es-input", str(es_input),
            "--profile", str(profile),
        ]

        _logger.info(
            "gamepadly: player=%d guid=%s sdl_id=%d perfil=%s",
            player,
            guid,
            index,
            profile.name,
        )
        _logger.debug("gamepadly: cmd=%s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
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