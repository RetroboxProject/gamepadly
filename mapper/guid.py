from __future__ import annotations

import struct


def normalize_guid(guid: str) -> str:
    return guid.lower().replace("-", "")


def guid_vendor_product(guid: str) -> tuple[int, int]:
    raw = bytes.fromhex(normalize_guid(guid))
    vendor = struct.unpack_from("<H", raw, 4)[0]
    product = struct.unpack_from("<H", raw, 8)[0]
    return vendor, product


def guid_matches(a: str, b: str) -> bool:
    """
    Devuelve True si dos GUIDs son iguales o si coinciden en Vendor/Product.
    """
    na = normalize_guid(a)
    nb = normalize_guid(b)

    if na == nb:
        return True

    try:
        return guid_vendor_product(na) == guid_vendor_product(nb)
    except Exception:
        return False