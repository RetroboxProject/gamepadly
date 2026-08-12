class GamepadlyError(RuntimeError):
    """Error genérico de gamepadly."""


class ProfileError(GamepadlyError):
    """Error cargando o parseando un perfil."""


class ESInputError(GamepadlyError):
    """Error leyendo o parseando es_input.cfg."""


class JoystickError(GamepadlyError):
    """Error relacionado con pygame/SDL o el mando."""