"""openFDA food enforcement normalizer — offline tests.

openFDA records carry place text but no coordinates, so parse() emits docs with a
private `_geo_query` and no `location`; geocoding happens in geocode.resolve_locations.
These tests stub the geocoder so no network is touched.
"""
from __future__ import annotations

import asyncio

from conftest import load_sample

import geocode
from sources import openfda


def parsed():
    return openfda.parse(load_sample("openfda_food_enforcement.json"))


def test_parses_records_with_recall_number():
    events = parsed()
    # 3 records; the third lacks recall_number but has event_id → still parsed.
    assert len(events) == 3
    ids = {e["id"] for e in events}
    assert "openfda-F-1188-2026" in ids


def test_partial_docs_defer_geocoding():
    by_id = {e["id"]: e for e in parsed()}
    asha = by_id["openfda-F-1188-2026"]
    assert asha["source"] == "openfda"
    assert asha["event_type"] == "recall"
    assert "location" not in asha          # geo deferred
    assert asha["_geo_query"] == "Edison, NJ, United States"
    assert asha["place_name"] == "Edison, NJ, United States"
    assert "emulsifier" in asha["summary"].lower()


def test_severity_by_classification():
    by_id = {e["id"]: e for e in parsed()}
    assert by_id["openfda-F-1188-2026"]["severity_raw"] == 0.85   # Class I
    assert by_id["openfda-F-1190-2026"]["severity_raw"] == 0.55   # Class II
    assert by_id["openfda-90873"]["severity_raw"] == 0.3          # Class III, no recall_number


def test_empty_city_falls_back_to_country():
    by_id = {e["id"]: e for e in parsed()}
    assert by_id["openfda-90873"]["_geo_query"] == "United States"


def test_geocoded_docs_are_contract_valid(assert_valid_events, monkeypatch):
    # Stub the geocoder: Edison NJ-ish coords for everything.
    async def fake_geocode(client, query):
        return (40.5187, -74.4121)

    monkeypatch.setattr(geocode, "geocode", fake_geocode)
    resolved, dropped = asyncio.run(geocode.resolve_locations(None, parsed()))
    assert dropped == 0
    assert len(resolved) == 3
    for ev in resolved:
        assert "_geo_query" not in ev
        assert ev["location"] == {"lat": 40.5187, "lon": -74.4121}
        assert ev["region"] == "north-america"
    assert_valid_events(resolved)


def test_ungeocodable_docs_are_dropped(monkeypatch):
    async def fake_geocode(client, query):
        return None

    monkeypatch.setattr(geocode, "geocode", fake_geocode)
    resolved, dropped = asyncio.run(geocode.resolve_locations(None, parsed()))
    assert resolved == []
    assert dropped == 3
