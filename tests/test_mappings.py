"""evmapy compatibility (modes, hold, exec) and the tap extension."""

# pylint: disable=missing-function-docstring,missing-class-docstring,too-few-public-methods

import json
from pathlib import Path

import pytest

from gamepadly.manager import GamepadManager
from gamepadly.mapper import actions as actions_module
from gamepadly.mapper.actions import ExecAction, KeyAction
from gamepadly.mapper.ecodes import ec
from gamepadly.mapper.engine import MapperEngine
from gamepadly.mapper.es_input import parse_es_input
from gamepadly.mapper.inputs import AxisInput, ButtonInput, axis_code, button_code
from gamepadly.mapper.profile import TAP_MAX_SECONDS, load_profile
from gamepadly.mapper.resolver import resolve_profile

HOTKEY, START, SELECT, A, B = 10, 7, 6, 0, 1
ES_MAP = {
    "hotkey": ButtonInput(HOTKEY),
    "start": ButtonInput(START),
    "select": ButtonInput(SELECT),
    "a": ButtonInput(A),
    "b": ButtonInput(B),
}


class FakeUI:
    """Records the keys written to the virtual keyboard."""

    def __init__(self):
        self.events = []

    def write_key(self, code, value):
        self.events.append((code, value))

    def syn(self, has_kbd=False, has_mouse=False):
        pass


def _engine(tmp_path: Path, mappings: list, es_map=None) -> MapperEngine:
    path = tmp_path / "p.keys"
    path.write_text(json.dumps({"actions_player1": mappings}))
    resolved = resolve_profile(load_profile(path), es_map or ES_MAP)
    return MapperEngine(joystick=None, resolved=resolved, player=1)


def _key(trigger, target, **extra):
    return {"trigger": trigger, "type": "key", "target": target, **extra}


def test_combo_presses_and_releases_chord(tmp_path):
    engine, ui = _engine(tmp_path, [_key(["hotkey", "start"], ["KEY_LEFTALT", "KEY_F4"])]), FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(START), 0.1, ui)
    engine.release(button_code(START), 0.2, ui)
    assert ui.events == [
        (ec.KEY_LEFTALT, 1), (ec.KEY_F4, 1), (ec.KEY_F4, 0), (ec.KEY_LEFTALT, 0),
    ]


def test_mode_any_fires_on_each_input(tmp_path):
    engine, ui = _engine(tmp_path, [_key(["a", "b"], "KEY_X", mode="any")]), FakeUI()
    engine.press(button_code(B), 0.0, ui)
    assert ui.events == [(ec.KEY_X, 1)]


def test_hold_waits_before_firing(tmp_path):
    engine, ui = _engine(tmp_path, [_key(["hotkey", "start"], "KEY_ESC", hold=1.0)]), FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(START), 0.0, ui)
    engine.tick(0.5, ui)
    assert not ui.events
    engine.tick(1.0, ui)
    assert ui.events == [(ec.KEY_ESC, 1)]


def test_hold_cancelled_by_early_release(tmp_path):
    engine, ui = _engine(tmp_path, [_key(["hotkey", "start"], "KEY_ESC", hold=1.0)]), FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(START), 0.0, ui)
    engine.release(button_code(START), 0.5, ui)
    engine.tick(1.5, ui)
    assert not ui.events


def test_hold_cancelled_by_another_press(tmp_path):
    """A held hotkey waiting to fire alone gives way to Hotkey+Start."""
    engine = _engine(tmp_path, [
        _key(["hotkey"], "KEY_F7", hold=0.75),
        _key(["hotkey", "start"], "KEY_ESC"),
    ])
    ui = FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(START), 0.2, ui)
    engine.release(button_code(START), 0.3, ui)
    engine.tick(1.0, ui)
    assert ui.events == [(ec.KEY_ESC, 1), (ec.KEY_ESC, 0)]


def test_hold_cancelled_by_unrelated_press(tmp_path):
    engine = _engine(tmp_path, [_key(["hotkey"], "KEY_F7", hold=0.75)])
    ui = FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(A), 0.2, ui)
    engine.release(button_code(A), 0.3, ui)
    engine.tick(1.0, ui)
    assert not ui.events


def test_sequence(tmp_path):
    engine, ui = _engine(tmp_path, [_key(["a", "b", "a"], "KEY_Z", mode="sequence")]), FakeUI()
    for code in (A, B, B, A, B, A):
        engine.press(button_code(code), 0.0, ui)
        engine.release(button_code(code), 0.0, ui)
    assert ui.events == [(ec.KEY_Z, 1), (ec.KEY_Z, 0)]


@pytest.mark.parametrize(
    "mapping",
    [
        _key(["a", "b"], "KEY_Z", mode="sequence", hold=1),
        _key(["a"], "KEY_Z", mode="sequence"),
        _key(["a"], "KEY_Z", mode="bogus"),
        _key(["a"], "KEY_Z", hold=-1),
        _key(["a", "a"], "KEY_Z"),
        _key(["a"], ["KEY_Z", "KEY_Z"]),
        _key(["hotkey", "a"], "KEY_Z", tap=True),
    ],
)
def test_invalid_mappings_are_ignored(tmp_path, mapping):
    path = tmp_path / "p.keys"
    path.write_text(json.dumps({"actions_player1": [mapping]}))
    profile = load_profile(path)
    assert not profile.hotkeys and not profile.sequences


def test_exec_runs_shell_commands(tmp_path, monkeypatch):
    started = []

    class FakePopen:
        def __init__(self, command, **kwargs):
            started.append((command, kwargs))

        def poll(self):
            return 0

    monkeypatch.setattr(actions_module.subprocess, "Popen", FakePopen)
    engine = _engine(
        tmp_path,
        [{"trigger": ["hotkey", "start"], "type": "exec", "target": "retrobox-emukill"}],
    )
    ui = FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(START), 0.0, ui)
    assert started[0][0] == "retrobox-emukill"
    assert started[0][1]["shell"] and started[0][1]["start_new_session"]
    assert not ui.events
    actions_module.reap_children()
    assert not actions_module._children  # pylint: disable=protected-access


def test_exec_target_list_runs_every_command(tmp_path):
    path = tmp_path / "p.keys"
    path.write_text(json.dumps({"actions_player1": [
        {"trigger": "a", "type": "exec", "target": ["one", "two"]},
    ]}))
    assert load_profile(path).hotkeys[0].action == ExecAction(("one", "two"))


def _tap_engine(tmp_path, es_map=None):
    return _engine(
        tmp_path,
        [
            _key("hotkey", "KEY_HOMEPAGE", tap=True),
            _key(["hotkey", "start"], "KEY_ESC"),
        ],
        es_map,
    )


def test_tap_fires_on_release(tmp_path):
    engine, ui = _tap_engine(tmp_path), FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    assert not ui.events
    engine.release(button_code(HOTKEY), 0.1, ui)
    assert ui.events == [(ec.KEY_HOMEPAGE, 1), (ec.KEY_HOMEPAGE, 0)]


def test_tap_cancelled_by_combo(tmp_path):
    engine, ui = _tap_engine(tmp_path), FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(START), 0.1, ui)
    engine.release(button_code(START), 0.2, ui)
    engine.release(button_code(HOTKEY), 0.3, ui)
    assert ui.events == [(ec.KEY_ESC, 1), (ec.KEY_ESC, 0)]


def test_tap_cancelled_by_other_press_and_long_hold(tmp_path):
    engine, ui = _tap_engine(tmp_path), FakeUI()
    engine.press(button_code(HOTKEY), 0.0, ui)
    engine.press(button_code(A), 0.1, ui)
    engine.release(button_code(HOTKEY), 0.2, ui)
    engine.press(button_code(HOTKEY), 1.0, ui)
    engine.release(button_code(HOTKEY), 1.0 + TAP_MAX_SECONDS + 0.1, ui)
    assert not ui.events


def test_tap_ignored_when_hotkey_is_select(tmp_path):
    es_map = dict(ES_MAP, hotkey=ButtonInput(SELECT))
    engine, ui = _tap_engine(tmp_path, es_map), FakeUI()
    engine.press(button_code(SELECT), 0.0, ui)
    engine.release(button_code(SELECT), 0.1, ui)
    assert not ui.events
    assert isinstance(engine.combos[0].action, KeyAction)


def test_es_input_derives_opposite_stick_directions(tmp_path):
    guid = "050000007e0500000920000001800000"
    cfg = tmp_path / "es_input.cfg"
    cfg.write_text(
        f'<inputList><inputConfig type="joystick" deviceName="pad" deviceGUID="{guid}">'
        '<input name="joystick1up" type="axis" id="1" value="-1"/>'
        '<input name="joystick1left" type="axis" id="0" value="-1"/>'
        "</inputConfig></inputList>"
    )
    es_map = parse_es_input(cfg, guid)
    assert es_map["joystick1down"] == AxisInput(axis_id=1, value=1)
    assert es_map["joystick1right"] == AxisInput(axis_id=0, value=1)
    assert axis_code(1, positive=True) != axis_code(1, positive=False)


def test_manager_uses_given_profile(tmp_path, monkeypatch):
    profile = tmp_path / "session.keys"
    profile.write_text("{}")
    es_input = tmp_path / "es_input.cfg"
    es_input.write_text("<inputList/>")
    launched = []

    class FakeProc:
        pid = 1

        def poll(self):
            return 0

    class Pad:
        guid, index, player_number, type = "05000000", 0, 1, "joystick"

    monkeypatch.setattr(
        "gamepadly.manager.subprocess.Popen", lambda cmd, **kw: launched.append(cmd) or FakeProc()
    )
    with GamepadManager(
        system="snes", emulator="x", core="y", rom=tmp_path / "r", controllers=[Pad()],
        profiles_dir=tmp_path / "none", user_profiles_dir=tmp_path / "none",
        es_input=es_input, profile=profile,
    ):
        pass
    assert str(profile) in launched[0]
