# Gamepadly

Gamepadly is a Linux gamepad-to-keyboard/mouse mapper. It reads controller input through `pygame` / SDL2 and emits virtual keyboard and mouse events using `evdev` `UInput`.

As this project is intended to be used on a couch gaming/emulation setup, it's compatible with Batocera-style `evmapy` profiles, while adding extra features such as scroll wheel emulation, combo cooldowns, or an integration-oriented manager API.

This is based on a previous implementation that I did on my parallel project: [retrobox](https://github.com/manu-romero-411/retrobox-core.git)

---

## Features

- **Gamepad to keyboard/mouse mapping**
  - Emits virtual keyboard events.
  - Emits virtual mouse button events.
  - Emits relative mouse motion from analog sticks.
  - Emits scroll wheel events from analog sticks.

- **Evmapy-compatible profiles**
  - Uses JSON profile files.
  - Supports `actions_player1`, `actions_player2`, etc.
  - Falls back to a generic `mappings` section if no player-specific section is found.

- **Advanced profile features**
  - Button combinations.
  - Conditional activation.
  - Per-combo cooldowns.
  - Global cooldown.
  - Analog-to-mouse movement with deadzone and acceleration.
  - Analog-to-scroll support.

- **EmulationStation integration (needs a Batocera/RetroBat EmulationStation build. May not work with ES-DE)**
  - Reads EmulationStation `es_input.cfg` to resolve controller bindings by name.
  - Matches controllers by GUID.
  - Falls back to Vendor/Product matching when needed.
  - Prefers physical devices over virtual ones when possible.

- **Runtime robustness**
  - Waits for controller connection.
  - Handles controller disconnection.
  - Automatically reconnects and resumes mapping.

- **Manager API**
  - Launches one mapper process per active controller.
  - Automatically selects the appropriate profile based on game, system, emulator, and core.
  - Terminates mapper processes cleanly when the game session ends.

---

## Installation

Gamepadly is a regular Python package (`import gamepadly`, command `gamepadly-mapper`).
It needs Python 3.10+, `pygame` and `evdev`.

**Debian / Ubuntu** (`.deb` from the [releases](https://github.com/manu-romero-411/gamepadly/releases) page):

```bash
sudo apt install ./python3-gamepadly_<version>_all.deb
```

**Fedora** (`.rpm`, one per Fedora release):

```bash
sudo dnf install ./python3-gamepadly-<version>-1.fc<NN>.noarch.rpm
```

Both install the package in the distribution's standard Python directory and pull `pygame`/`evdev`
from the distro. They also ship the `uinput` udev rule and modules-load file.

**Any distro, from a checkout or remotely** (installs with pip into `/usr/local`, installs distro
dependencies with apt/dnf):

```bash
sudo ./install.sh
# or
curl -fsSL https://raw.githubusercontent.com/manu-romero-411/gamepadly/main/install.sh | sudo bash
```

Useful options: `--ref v0.1.0`, `--no-deps`, `--pip-deps`, `--user`, `--uninstall`.
Uninstall with `sudo ./install.sh --uninstall` or `sudo pip uninstall gamepadly`
(the latter leaves the udev rule in `/etc`).

**From PyPI** (once published) or in a virtualenv:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install gamepadly
```

**Development:**

```bash
pip install -e ".[dev]" && pytest
```

---

## Permissions

The mapper needs access to input devices and the `uinput` subsystem.

Add your user to the `input` group:

```bash
sudo usermod -aG input $USER
```

Then use `newgrp $USER` on your current terminal, or better logout or reboot the system.

If your system requires explicit `uinput` access, make sure the `uinput` module is loaded:

```bash
sudo modprobe uinput
```

You can verify input permissions by running:

```bash
gamepadly-mapper --list
```

If no controllers are detected, check:

```bash
groups $USER | grep -w input
```

---

## Quick Start

List connected gamepads:

```bash
gamepadly-mapper --list
```

Run the mapper manually:

```bash
gamepadly-mapper \
  --guid 050000007e0500000920000001800000 \
  --sdl_id 0 \
  --player 1 \
  --es-input ~/.emulationstation/es_input.cfg \
  --profile ~/.config/gamepadly/profiles/example.keys
```

If no profile is provided, a default built-in profile is used.

---

## Command-Line Usage

```text
gamepadly-mapper --list

gamepadly-mapper \
  --guid <GUID> \
  --sdl_id <N> \
  --player <N> \
  --es-input <es_input.cfg> \
  [--profile <profile.keys>] \
  [--debug]
```

### Options

| Option | Description |
|---|---|
| `--list` | List detected gamepads and exit. |
| `--guid` | Controller GUID from SDL/EmulationStation. |
| `--sdl_id` | SDL device index. Useful when multiple identical controllers are connected. |
| `--player` | Player number. Selects `actions_playerN` inside the profile. |
| `--es-input` | Path to EmulationStation `es_input.cfg`. |
| `--profile` | JSON profile file. If omitted, the default profile is used. |
| `--debug` | Enable debug logging. |

Example:

```bash
gamepadly-mapper \
  --guid 050000007e0500000920000001800000 \
  --sdl_id 0 \
  --player 1 \
  --es-input ~/.emulationstation/es_input.cfg \
  --profile ~/.config/gamepadly/profiles/snes.keys \
  --debug
```

---

## Profile Format

Profiles are JSON files. They are compatible with the general `evmapy` style used by Batocera, while supporting some additional options.

Basic structure:

```json
{
  "cooldown": 0.5,
  "actions_player1": [
    {
      "trigger": ["hotkey", "start"],
      "type": "key",
      "target": ["KEY_LEFTALT", "KEY_F4"]
    }
  ]
}
```

Player-specific sections are supported:

```json
{
  "actions_player1": [],
  "actions_player2": [],
  "actions_player3": [],
  "actions_player4": []
}
```

If the selected player section is missing, Gamepadly falls back to:

```json
{
  "mappings": []
}
```

---

## Mapping Types

### Keyboard Key

Presses one or more keyboard keys when the trigger is pressed.

```json
{
  "trigger": ["hotkey", "start"],
  "type": "key",
  "target": ["KEY_LEFTALT", "KEY_F4"]
}
```

This can be used for simple key combinations such as:

- `KEY_ESC`
- `KEY_ENTER`
- `KEY_LEFTMETA`
- `KEY_F4`
- `KEY_VOLUMEUP`
- `KEY_VOLUMEDOWN`

---

### Mouse Button

Mouse buttons are also expressed as `type: "key"`, but using a `BTN_*` target.

```json
{
  "trigger": ["hotkey", "r3"],
  "type": "key",
  "target": "BTN_LEFT"
}
```

Common mouse button names:

- `BTN_LEFT`
- `BTN_RIGHT`
- `BTN_MIDDLE`

If the target is a single `BTN_*` value, the button is held while the gamepad trigger is held.

---

### Mouse Movement

Maps two analog axes to relative mouse movement.

```json
{
  "trigger": "joystick2",
  "type": "mouse",
  "speed": 800,
  "deadzone": 0.15,
  "acceleration": 1.5,
  "condition": "hotkey"
}
```

You can use a full stick name:

```json
"trigger": "joystick1"
```

or explicitly provide two axes:

```json
"trigger": ["joystick2left", "joystick2up"]
```

Supported stick shortcuts:

```json
"joystick1"
"joystick2"
```

They expand internally to:

```json
["joystick1left", "joystick1up"]
["joystick2left", "joystick2up"]
```

---

### Scroll Wheel

Maps an analog axis to vertical and/or horizontal scrolling.

```json
{
  "trigger": "joystick1",
  "type": "scroll",
  "speed": 8,
  "deadzone": 0.15,
  "acceleration": 1.2,
  "condition": "hotkey"
}
```

You can also provide one or two axes explicitly:

```json
{
  "trigger": ["joystick1up", "joystick1left"],
  "type": "scroll"
}
```

For two-axis scroll mappings, the first axis is interpreted as vertical scroll and the second as horizontal scroll.

---

## Conditions

A mapping can require an additional button to be held.

Example:

```json
{
  "trigger": "joystick2",
  "type": "mouse",
  "condition": "hotkey"
}
```

This maps the right stick to mouse movement only while the `hotkey` button is held.

Conditions may also be lists:

```json
"condition": ["hotkey", "select"]
```

For keyboard combinations, conditions are added to the trigger when resolving the final combo.

---

## Cooldowns

Cooldowns help avoid double-triggering combinations.

Global cooldown:

```json
{
  "cooldown": 0.5
}
```

Per-mapping cooldown:

```json
{
  "trigger": ["hotkey", "start"],
  "type": "key",
  "target": ["KEY_ESC"],
  "cooldown": 1.0
}
```

Cooldown rules:

- If a mapping defines `cooldown`, that value is used.
- Single-button mappings without an explicit cooldown default to `0.0`.
- Multi-button combos without an explicit cooldown use the global cooldown.

---

## Example Profile

```json
{
  "cooldown": 0.5,
  "actions_player1": [
    {
      "trigger": ["hotkey", "start"],
      "type": "key",
      "target": ["KEY_LEFTALT", "KEY_F4"]
    },
    {
      "trigger": ["hotkey", "select"],
      "type": "key",
      "target": "KEY_LEFTMETA"
    },
    {
      "trigger": ["hotkey", "a"],
      "type": "key",
      "target": "KEY_ESC"
    },
    {
      "trigger": ["hotkey", "b"],
      "type": "key",
      "target": "KEY_ENTER"
    },
    {
      "trigger": ["hotkey", "pageup"],
      "type": "key",
      "target": ["KEY_LEFTCTRL", "KEY_LEFTALT", "KEY_T"]
    },
    {
      "trigger": ["hotkey", "up"],
      "type": "key",
      "target": "KEY_VOLUMEUP"
    },
    {
      "trigger": ["hotkey", "down"],
      "type": "key",
      "target": "KEY_VOLUMEDOWN"
    },
    {
      "trigger": ["hotkey", "r3"],
      "type": "key",
      "target": "BTN_LEFT"
    },
    {
      "trigger": ["hotkey", "l3"],
      "type": "key",
      "target": "BTN_RIGHT"
    },
    {
      "trigger": "joystick2",
      "type": "mouse",
      "speed": 800,
      "deadzone": 0.15,
      "acceleration": 1.5,
      "condition": "hotkey"
    },
    {
      "trigger": "joystick1",
      "type": "scroll",
      "speed": 8,
      "deadzone": 0.15,
      "acceleration": 1.2,
      "condition": "hotkey"
    }
  ]
}
```

---

## Profile Search Order

The manager searches for profiles in the following order. The first existing file wins.

1. Game-specific override:
   ```text
   <rom>.keys
   ```

   For directory-based games, the current convention is:
   ```text
   <game-directory>/pad2.keys
   ```

2. User profiles:

   ```text
   {system}.{emulator}.{core}.keys
   {system}.{emulator}.keys
   {system}.keys
   {emulator}.keys
   any.keys
   ```

3. System profiles:

   ```text
   {system}.{emulator}.{core}.keys
   {system}.{emulator}.keys
   {system}.keys
   {emulator}.keys
   any.keys
   ```

Example:

```text
profiles/snes.libretro.retroarch.keys
profiles/snes.libretro.keys
profiles/snes.keys
profiles/libretro.keys
profiles/any.keys
```

This allows very precise per-system or per-emulator mappings, while still supporting global fallbacks.

---

## Manager Integration

Gamepadly includes a manager component designed to be used from an emulator launcher or frontend.

Its responsibility is:

1. Find the appropriate profile.
2. Detect active controllers.
3. Launch one mapper process per controller.
4. Terminate all mapper processes when the game exits.

Conceptual usage:

```python
from gamepadly.gamepadly_manager import GamepadManager

with GamepadManager(
    system="snes",
    emulator="libretro",
    core="snes9x",
    rom="/roms/snes/Super Game.sfc",
    controllers=controllers,
):
    run_game()
```

When entering the context, the manager starts the required mapper processes. When exiting, it stops them.

If no profile is found, the manager does nothing. This makes it safe to integrate unconditionally.

---

## EmulationStation Input Resolution

Gamepadly uses EmulationStation's `es_input.cfg` to map logical button names to physical controller inputs.

Supported input types:

| ES Type | Meaning |
|---|---|
| `button` | Physical button |
| `hat` | D-pad hat direction |
| `axis` | Analog axis direction |

The following are the typical names that EmulationStation uses for input settings:

```text
a
b
x
y
start
select
hotkey
up
down
left
right
pageup
pagedown
l2
r2
l3
r3
joystick1left
joystick1up
joystick2left
joystick2up
```

The mapper first tries to match the controller by exact GUID. If that fails, it falls back to Vendor/Product matching. When multiple candidate configurations exist, physical devices are preferred over virtual devices.

---

## Architecture

Gamepadly is conceptually split into several components, in a modular fashion:

```text
gamepadly/
├── __init__.py
├── gamepadly_manager.py
├── gamepadly_mapper.py
└── mapper/
    ├── __init__.py
    ├── __main__.py
    ├── cli.py
    ├── engine.py
    ├── runner.py
    ├── profile.py
    ├── defaults.py
    ├── es_input.py
    ├── resolver.py
    ├── inputs.py
    ├── actions.py
    ├── joystick.py
    ├── ecodes.py
    ├── exceptions.py
    └── uinput_backend.py
```

### Manager

High-level component used by the frontend/launcher.

Responsibilities:

- Profile discovery.
- Controller iteration.
- Mapper process lifecycle.
- Cleanup on exit.

### Mapper

The actual input translation daemon.

Responsibilities:

- Read controller events through `pygame`.
- Resolve ES input names to internal virtual codes.
- Track pressed buttons, hats, and axis directions.
- Detect valid combos.
- Apply cooldown rules.
- Convert analog stick motion into mouse or scroll events.
- Emit events through `evdev.UInput`.

### Profile Loader

Parses `.keys` JSON files.

Responsibilities:

- Validate entries.
- Normalize trigger and target values.
- Expand stick shortcuts.
- Build key/click actions.
- Build mouse and scroll axis configurations.
- Resolve cooldowns.

### ES Input Parser

Parses `es_input.cfg`:

- Find the matching controller configuration.
- Convert ES input entries into abstract button/hat/axis objects.
- Provide a name-to-input map.

### Resolver

Converts abstract profile data into runtime-ready data:

- Convert ES names into internal virtual codes.
- Ignore unavailable bindings.
- Detect physically collapsed combos.
- Resolve mouse and scroll axis configurations.
- Resolve conditional button sets.

### UInput Backend

Creates virtual input devices.

Two virtual devices are used:

- one keyboard-like device for `KEY_*` events;
- one mouse-like device for `BTN_*` and relative axis events.

This separation avoids issues where the compositor or input stack misclassifies mouse button events.

---

## Running as a Module

If the project is installed or executed from the parent directory, the mapper can be run as a Python module:

```bash
python3 -m gamepadly.mapper --list
```

For example:

```bash
cd ~/Escritorio
python3 -m gamepadly.mapper --list
```

If running from inside the `gamepadly` directory, a launcher script can also be used:

```bash
cd ~/Escritorio/gamepadly
gamepadly-mapper --list
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'gamepadly'`

This usually means Python cannot see the parent directory containing the `gamepadly` package.

Run from the parent directory:

```bash
cd ~/Escritorio
python3 -m gamepadly.mapper --list
```

or use a launcher script that adds the parent directory to `sys.path`.

---

### No gamepads found

Check that your user belongs to the `input` group:

```bash
groups $USER | grep -w input
```

If not:

```bash
sudo usermod -aG input $USER
```

Then log out and log back in.

---

### Permission denied when creating UInput devices

Ensure the `uinput` kernel module is loaded:

```bash
sudo modprobe uinput
```

Also verify that your user has permission to access input devices.

---

### Mouse movement does not work

Check the following:

- The analog axis names exist in `es_input.cfg`.
- The `condition` button is being held.
- The correct stick is being used.
- The deadzone is not too high.
- Debug logging is enabled:

```bash
gamepadly-mapper --debug ...
```

---

### Combo does not trigger

Possible causes:

- One of the required buttons is missing from `es_input.cfg`.
- The combo contains names that physically collapse to the same internal input.
- The combo is still in cooldown.
- The condition button is not held.
- The selected player section does not exist in the profile.

Use debug mode to inspect combo resolution:

```bash
gamepadly-mapper --debug ...
```

---

## License

See `LICENSE` file for more details.

---

## Python API

```python
from gamepadly import GamepadManager

with GamepadManager(system="snes", emulator="libretro", core="snes9x", rom=rom_path,
                    controllers=controllers,  # objects with .guid, .index, .player_number
                    profiles_dir=system_profiles, user_profiles_dir=user_profiles,
                    es_input=es_input_cfg):
    run_game()
```

The mapper is launched as `python -m gamepadly.mapper`; pass `mapper_command=(...)` to override it.
