import json
from pathlib import Path

import pytest

import gamepadly
from gamepadly.manager import GamepadManager, find_profile
from gamepadly.mapper.cli import build_parser, main
from gamepadly.mapper.guid import guid_matches
from gamepadly.mapper.profile import load_profile


def test_version_is_exposed():
    assert gamepadly.__version__


def test_cli_help_exits_cleanly(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--guid" in capsys.readouterr().out


def test_cli_requires_guid():
    with pytest.raises(SystemExit) as exc:
        main(["--es-input", "x"])
    assert exc.value.code == 2


def test_parser_defaults():
    args = build_parser().parse_args(["--list"])
    assert args.list and args.player == 1 and args.sdl_id == 0


def test_guid_matching_is_case_insensitive():
    guid = "050000007e0500000920000001800000"
    assert guid_matches(guid, guid.upper())


def test_load_profile(tmp_path: Path):
    profile = tmp_path / "p.keys"
    profile.write_text(json.dumps({
        "cooldown": 0.5,
        "actions_player1": [
            {"trigger": ["hotkey", "start"], "type": "key", "target": ["KEY_ESC"]},
        ],
    }))
    loaded = load_profile(profile, player=1)
    assert len(loaded.hotkeys) == 1
    assert loaded.hotkeys[0].trigger == ("hotkey", "start")
    assert loaded.global_cooldown == 0.5


def test_profile_lookup_prefers_user_then_most_specific(tmp_path: Path):
    system_dir, user_dir = tmp_path / "sys", tmp_path / "user"
    system_dir.mkdir()
    user_dir.mkdir()
    rom = tmp_path / "game.rom"
    (system_dir / "snes.keys").write_text("{}")
    (system_dir / "snes.retroarch.keys").write_text("{}")
    (user_dir / "snes.keys").write_text("{}")

    found = find_profile(rom, "snes", "retroarch", "bsnes", system_dir, user_dir)
    assert found == user_dir / "snes.keys"
    (user_dir / "snes.keys").unlink()
    found = find_profile(rom, "snes", "retroarch", "bsnes", system_dir, user_dir)
    assert found == system_dir / "snes.retroarch.keys"
    assert find_profile(rom, "gba", "mgba", "mgba", system_dir, user_dir) is None


class _Pad:
    guid = "050000007e0500000920000001800000"
    index = 0
    player_number = 1
    type = "joystick"


def test_manager_launches_mapper_module(tmp_path: Path, monkeypatch):
    profiles, user = tmp_path / "p", tmp_path / "u"
    profiles.mkdir()
    user.mkdir()
    (profiles / "any.keys").write_text("{}")
    es_input = tmp_path / "es_input.cfg"
    es_input.write_text("<inputList/>")

    launched = []

    class FakeProc:
        pid = 1234

        def poll(self):
            return 0

    monkeypatch.setattr("gamepadly.manager.subprocess.Popen",
                        lambda cmd, **kw: launched.append(cmd) or FakeProc())
    with GamepadManager(system="snes", emulator="x", core="y", rom=tmp_path / "r",
                        controllers=[_Pad()], profiles_dir=profiles, user_profiles_dir=user,
                        es_input=es_input):
        pass
    assert len(launched) == 1
    assert launched[0][1:3] == ["-m", "gamepadly.mapper"]
    assert "--guid" in launched[0] and str(profiles / "any.keys") in launched[0]
