"""NOAA/NWS active-alerts normalizer — offline tests."""
from __future__ import annotations

import asyncio

from conftest import load_sample

import geocode
from sources import noaa


def parsed():
    return noaa.parse(load_sample("noaa_alerts_active.json"))


def test_filters_noise_and_noncurrent():
    events = parsed()
    ids = {e["id"] for e in events}
    # Kept: Severe tropical storm (polygon) + Moderate flood (null geom).
    assert len(events) == 2
    assert "noaa-urn:oid:2.49.0.1.840.0.delia.2026" in ids
    # Dropped: Minor advisory, Cancel message, Exercise status.
    assert not any("minor" in i for i in ids)
    assert not any("cancel" in i for i in ids)
    assert not any("exercise" in i for i in ids)


def test_polygon_centroid_and_fields():
    by_id = {e["id"]: e for e in parsed()}
    delia = by_id["noaa-urn:oid:2.49.0.1.840.0.delia.2026"]
    assert delia["event_type"] == "storm"
    assert delia["severity_raw"] == 0.75  # Severe
    # Centroid of the 5-point closed ring (last == first vertex averaged in).
    assert delia["location"]["lat"] == round((29.6 * 3 + 30.0 * 2) / 5, 5)
    assert delia["location"]["lon"] == round((-93.6 * 3 + -93.0 * 2) / 5, 5)
    assert delia["region"] == "north-america"
    assert delia["published_at"] == "2026-06-10T08:00:00Z"  # -05:00 → UTC
    assert "location" in delia and "_geo_query" not in delia


def test_null_geometry_defers_geocoding():
    by_id = {e["id"]: e for e in parsed()}
    flood = by_id["noaa-urn:oid:2.49.0.1.840.0.flood.miss.2026"]
    assert flood["event_type"] == "flood"
    assert flood["severity_raw"] == 0.5  # Moderate
    assert "location" not in flood
    assert flood["_geo_query"] == "Hancock County"  # first segment of areaDesc


def test_polygon_docs_are_contract_valid(assert_valid_events):
    # The polygon alert already has a location; validate it directly.
    polygon_docs = [e for e in parsed() if "location" in e]
    assert polygon_docs
    assert_valid_events(polygon_docs)


def test_null_geom_doc_valid_after_geocode(assert_valid_events, monkeypatch):
    async def fake_geocode(client, query):
        return (30.31, -89.42, "Hancock County, MS, USA")

    monkeypatch.setattr(geocode, "geocode", fake_geocode)
    resolved, dropped = asyncio.run(geocode.resolve_locations(None, parsed()))
    assert dropped == 0
    assert len(resolved) == 2
    assert_valid_events(resolved)
