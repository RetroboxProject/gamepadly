from __future__ import annotations

from dataclasses import dataclass

BTN_VIRTUAL_BASE = 0x0000
HAT_VIRTUAL_BASE = 0x1000
AXIS_VIRTUAL_BASE = 0x2000

AXIS_THRESHOLD = 0.5

_HAT_DIR_BIT = {
    1: 0,  # up
    2: 1,  # right
    4: 2,  # down
    8: 3,  # left
}


@dataclass(frozen=True)
class ButtonInput:
    sdl_id: int


@dataclass(frozen=True)
class HatInput:
    hat_id: int
    direction: int


@dataclass(frozen=True)
class AxisInput:
    axis_id: int
    value: int  # -1 o +1


ESInputMap = dict[str, ButtonInput | HatInput | AxisInput]


def button_code(sdl_id: int) -> int:
    return BTN_VIRTUAL_BASE + sdl_id


def hat_code(hat_id: int, direction: int) -> int:
    return HAT_VIRTUAL_BASE + hat_id * 4 + _HAT_DIR_BIT[direction]


def axis_code(axis_id: int, positive: bool) -> int:
    return AXIS_VIRTUAL_BASE + axis_id * 2 + (1 if positive else 0)


def input_to_virtual(inp: ButtonInput | HatInput | AxisInput) -> int:
    if isinstance(inp, ButtonInput):
        return button_code(inp.sdl_id)

    if isinstance(inp, HatInput):
        return hat_code(inp.hat_id, inp.direction)

    if isinstance(inp, AxisInput):
        return axis_code(inp.axis_id, inp.value > 0)

    raise TypeError(f"Tipo desconocido: {type(inp)}")
