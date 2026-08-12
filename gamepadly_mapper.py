#!/usr/bin/env python3
"""
Lanzador externo del mapper.

Permite ejecutar directamente:

    python3 gamepadly_mapper.py --list

incluso desde dentro del propio directorio del paquete `gamepadly`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrapping de importación.
#
# Si este archivo está en:
#   ~/Escritorio/gamepadly/gamepadly_mapper.py
#
# parents[1] será:
#   ~/Escritorio
#
# Así Python puede importar:
#   gamepadly.mapper.cli
# ---------------------------------------------------------------------------
_PACKAGE_PARENT = Path(__file__).resolve().parents[1]

if str(_PACKAGE_PARENT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_PARENT))

# ---------------------------------------------------------------------------
# SDL sin vídeo/audio reales.
# Debe ponerse antes de importar pygame.
# ---------------------------------------------------------------------------
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from gamepadly.mapper.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())