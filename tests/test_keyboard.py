"""Keyboard hotkeys (actions_keyboard)."""

# pylint: disable=missing-function-docstring,missing-class-docstring,too-few-public-methods

import json
from pathlib import Path

from gamepadly.manager import GamepadManager
from gamepadly.mapper import actions as actions_module
from gamepadly.mapper.ecodes import ec
from gamepadly.mapper.engine import MapperEngine
from gamepadly.mapper.keyboard import (
    KEYBOARD_SECTION,
    is_keyboard,
    normalize_key,
    resolve_keyboard_profile,
)
from gamepadly.mapper.profile import load_profile


class FakeUI:
    def __init__(self):
        self.events = []

    def write_key(self, code, value):
        self.events.append((code, value))

    def syn(self, has_kbd=False, has_mouse=False):
        pass


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "p.keys"
    path.write_text(json.dumps(data))
    return path


def _engine(tmp_path, mappings):
    path = _write(tmp_path, {KEYBOARD_SECTION: mappings, "actions_player1": []})
    resolved = resolve_keyboard_profile(load_profile(path, section=KEYBOARD_SECTION))
    return MapperEngine(joystick=None, resolved=resolved, player=0)


def test_section_has_no_mappings_fallback(tmp_path):
    path = _write(tmp_path, {"mappings": [{"trigger": "a", "type": "key", "target": "KEY_A"}]})
    assert not load_profile(path, section=KEYBOARD_SECTION).hotkeys


def test_right_modifiers_count_as_left():
    assert normalize_key(ec.KEY_RIGHTSHIFT) == ec.KEY_LEFTSHIFT
    assert normalize_key(ec.KEY_ESC) == ec.KEY_ESC


def test_shift_escape_runs_command(tmp_path, monkeypatch):
    started = []

    class FakePopen:
        def __init__(self, command, **_kwargs):
            started.append(command)

        def poll(self):
            return 0

    monkeypatch.setattr(actions_module.subprocess, "Popen", FakePopen)
    engine = _engine(tmp_path, [
        {"trigger": ["KEY_LEFTSHIFT", "KEY_ESC"], "type": "exec", "target": "emukill"},
    ])
    ui = FakeUI()
    engine.press(normalize_key(ec.KEY_RIGHTSHIFT), 0.0, ui)
    engine.press(ec.KEY_ESC, 0.1, ui)
    assert started == ["emukill"]
    engine.release(ec.KEY_ESC, 0.2, ui)
    engine.press(ec.KEY_ESC, 0.3, ui)  # Escape alone: nothing
    assert started == ["emukill"]


def test_key_mapping_and_unknown_names(tmp_path):
    engine = _engine(tmp_path, [
        {"trigger": ["KEY_LEFTSHIFT", "KEY_F1"], "type": "key",
         "target": ["KEY_LEFTALT", "KEY_F4"]},
        {"trigger": ["KEY_NOPE"], "type": "key", "target": "KEY_A"},
    ])
    assert len(engine.resolved.hotkeys) == 1
    ui = FakeUI()
    engine.press(ec.KEY_LEFTSHIFT, 0.0, ui)
    engine.press(ec.KEY_F1, 0.0, ui)
    assert ui.events == [(ec.KEY_LEFTALT, 1), (ec.KEY_F4, 1)]


class FakeDevice:
    def __init__(self, name, keys):
        self.name = name
        self._keys = keys

    def capabilities(self):
        return {ec.EV_KEY: self._keys}


def test_keyboard_detection():
    assert is_keyboard(FakeDevice("AT keyboard", [ec.KEY_A, ec.KEY_ESC]))
    assert not is_keyboard(FakeDevice("gamepad-mapper-kbd-1", [ec.KEY_A, ec.KEY_ESC]))
    assert not is_keyboard(FakeDevice("Power Button", [ec.KEY_POWER]))


def test_manager_starts_keyboard_mapper(tmp_path, monkeypatch):
    profile = _write(tmp_path, {KEYBOARD_SECTION: [
        {"trigger": ["KEY_LEFTSHIFT", "KEY_ESC"], "type": "exec", "target": "x"},
    ]})
    launched = []

    class FakeProc:
        pid = 1

        def poll(self):
            return 0

    monkeypatch.setattr(
        "gamepadly.manager.subprocess.Popen", lambda cmd, **kw: launched.append(cmd) or FakeProc()
    )
    with GamepadManager(
        system="s", emulator="e", core="c", rom=tmp_path / "r", controllers=[],
        profiles_dir=tmp_path, user_profiles_dir=tmp_path,
        es_input=tmp_path / "missing.cfg", profile=profile,
    ):
        pass
    assert len(launched) == 1 and "--keyboard" in launched[0]
