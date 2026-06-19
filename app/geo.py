"""Region / geo registry for localized signal collection."""

from __future__ import annotations

REGION_MAP: dict[str, dict] = {
    "switzerland": {
        "geo": "CH",
        "currency": "CHF",
        "coords": (47.3769, 8.5417),
        "cities": {
            "Zürich": (47.3769, 8.5417),
            "St. Moritz": (46.4908, 9.8355),
            "Zermatt": (46.0207, 7.7491),
        },
        "country_code": "CH",
    },
    "germany": {
        "geo": "DE",
        "currency": "EUR",
        "coords": (52.52, 13.405),
        "cities": {"Berlin": (52.52, 13.405), "Munich": (48.137, 11.575)},
        "country_code": "DE",
    },
    "united states": {
        "geo": "US",
        "currency": "USD",
        "coords": (40.7128, -74.006),
        "cities": {"New York": (40.7128, -74.006)},
        "country_code": "US",
    },
    "japan": {
        "geo": "JP",
        "currency": "JPY",
        "coords": (35.6762, 139.6503),
        "cities": {"Tokyo": (35.6762, 139.6503)},
        "country_code": "JP",
    },
}

_ALIASES = {
    "swiss": "switzerland",
    "ch": "switzerland",
    "dach": "germany",
    "de": "germany",
    "us": "united states",
    "usa": "united states",
    "jp": "japan",
}


def resolve_region(location: str) -> dict:
    """Map a free-text location to geo metadata. Defaults to Switzerland."""
    key = location.strip().lower()
    key = _ALIASES.get(key, key)
    if key in REGION_MAP:
        return REGION_MAP[key]
    for name, meta in REGION_MAP.items():
        if name in key or key in name:
            return meta
    return REGION_MAP["switzerland"]
