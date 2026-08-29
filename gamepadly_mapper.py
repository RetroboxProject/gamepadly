#!/usr/bin/env python3
"""
Lanzador externo del mapper.

Permite ejecutar directamente:

    python3 gamepadly_mapper.py --list

incluso desde dentro del propio directorio del paquete.

En Retrobox normalmente vivirá en:

    runtime/gamepadly/gamepadly_mapper.py

y podrá importar como:

    runtime.gamepadly.mapper.cli

o, como fallback:

    gamepadly.mapper.cli
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()

for _idx in (2, 1):
    try:
        _path = _HERE.parents[_idx]
    except IndexError:
        continue

    if _path.exists() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# ---------------------------------------------------------------------------
# SDL sin vídeo/audio reales.
# Debe ponerse antes de importar pygame.
# ---------------------------------------------------------------------------
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

try:
    from runtime.gamepadly.mapper.cli import main  # noqa: E402
except ImportError:
    from gamepadly.mapper.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())