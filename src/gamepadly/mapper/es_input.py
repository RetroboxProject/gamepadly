from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from .exceptions import ESInputError
from .guid import guid_matches, normalize_guid
from .inputs import AxisInput, ButtonInput, ESInputMap, HatInput

_logger = logging.getLogger(__name__)


def parse_es_input(xml_path: Path | str, guid: str) -> ESInputMap:
    """
    Busca la configuración del mando en es_input.cfg.

    Prioridad:
      1. GUID exacto.
      2. Vendor/Product, prefiriendo dispositivos físicos.
      3. Vendor/Product sin filtrar virtuales.
    """
    xml_path = Path(xml_path)

    try:
        root = ET.parse(xml_path).getroot()
    except FileNotFoundError as exc:
        raise ESInputError(f"es_input file not found: {xml_path}") from exc
    except (OSError, ET.ParseError) as exc:
        raise ESInputError(f"Error while parsing XML {xml_path}: {exc}") from exc

    target_guid = normalize_guid(guid)

    candidates = [
        input_config
        for input_config in root.findall("inputConfig")
        if input_config.get("type") == "joystick"
        and guid_matches(guid, input_config.get("deviceGUID", ""))
    ]

    if not candidates:
        raise ESInputError(
            f"No se encontró ninguna configuración compatible "
            f"para el GUID {guid} en {xml_path}"
        )

    # 1) GUID exacto.
    cfg = next(
        (
            input_config
            for input_config in candidates
            if normalize_guid(input_config.get("deviceGUID", "")) == target_guid
        ),
        None,
    )

    # 2) Físico no virtual.
    if cfg is None:
        cfg = next(
            (
                input_config
                for input_config in candidates
                if "virtual" not in (input_config.get("deviceName") or "").lower()
            ),
            None,
        )

    # 3) Cualquier candidato.
    if cfg is None:
        cfg = candidates[0]

    device_name = cfg.get("deviceName")
    inputs = cfg.findall("input")

    _logger.debug(
        "Cargando mapa de entradas desde ES input: %s (%d entradas)",
        device_name,
        len(inputs),
    )

    result: ESInputMap = {}

    for inp in inputs:
        name = inp.get("name")
        itype = inp.get("type")

        if not name or not itype:
            continue

        try:
            iid = int(inp.get("id", 0))
            ivalue = int(inp.get("value", 1))
        except ValueError as exc:
            raise ESInputError(
                f"Entrada inválida en es_input.cfg: name={name!r}, type={itype!r}"
            ) from exc

        if itype == "button":
            result[name] = ButtonInput(sdl_id=iid)
        elif itype == "hat":
            result[name] = HatInput(hat_id=iid, direction=ivalue)
        elif itype == "axis":
            result[name] = AxisInput(axis_id=iid, value=ivalue)

    return result
