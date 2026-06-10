"""Per-source feed normalizers.

Each module exposes two functions kept deliberately separate so the parsing logic
is unit-testable with zero network:

    async fetch(client) -> raw payload        # the only network call
    parse(raw) -> list[world_event dict]       # pure, deterministic, tested offline

`REGISTRY` maps the source key (the `?source=` query param) to its module.
"""
from __future__ import annotations

from . import gdacs, gdelt, noaa, openfda, usgs

REGISTRY = {
    "usgs": usgs,
    "openfda": openfda,
    "noaa": noaa,
    "gdacs": gdacs,
    "gdelt": gdelt,
}

# Build order from impl plan §10 — value lands early.
ORDER = ["usgs", "openfda", "noaa", "gdacs", "gdelt"]
