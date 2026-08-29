from typing import ClassVar


class GamepadlyError(RuntimeError):
    """Error genérico de gamepadly."""
    EXIT_CODE: ClassVar = 1

    @property
    def exit_code(self) -> int:
        return self.EXIT_CODE


class ProfileError(GamepadlyError):
    """Error cargando o parseando un perfil."""
    EXIT_CODE = 200

class ESInputError(GamepadlyError):
    """Error leyendo o parseando es_input.cfg."""
    EXIT_CODE = 201

class JoystickError(GamepadlyError):
    """Error relacionado con pygame/SDL o el mando."""
    EXIT_CODE = 202