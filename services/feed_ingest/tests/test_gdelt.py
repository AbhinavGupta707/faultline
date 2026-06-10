"""GDELT Doc API normalizer — offline tests (relevance filter, type inference, dedupe)."""
from __future__ import annotations

import asyncio

from conftest import load_sample

import geocode
from sources import gdelt


def parsed():
    return gdelt.parse(load_sample("gdelt_artlist.json"))


def test_relevance_filter_and_url_dedupe():
    events = parsed()
    # 5 articles: 1 irrelevant (sports), 1 duplicate URL → 3 kept.
    assert len(events) == 3
    titles = " ".join(e["title"].lower() for e in events)
    assert "championship" not in titles  # sports article filtered out


def test_event_type_inference():
    by_title = {e["title"]: e for e in parsed()}
    fire = next(e for e in parsed() if "plant fire" in e["title"].lower())
    assert fire["event_type"] == "industrial_accident"
    port = next(e for e in parsed() if "port strike" in e["title"].lower())
    assert port["event_type"] == "port_disruption"
    frost = next(e for e in parsed() if "frost" in e["title"].lower())
    assert frost["event_type"] == "frost"


def test_docs_defer_geocoding_with_refine():
    for e in parsed():
        assert "location" not in e
        assert e["_geo_query"] == e["title"]   # geocode the headline
        assert e["_refine_place"] is True
        assert e["source"] == "gdelt"
        assert 0.0 <= e["severity_raw"] <= 1.0
        assert e["url"].startswith("http")


def test_stable_id_from_url():
    events = parsed()
    ids = {e["id"] for e in events}
    assert len(ids) == len(events)              # unique
    assert all(e["id"].startswith("gdelt-") for e in events)


def test_geocode_refines_place_name_and_validates(assert_valid_events, monkeypatch):
    async def fake_geocode(client, query):
        # Pretend Maps resolved the headline to a clean place.
        return (22.31, 73.18, "Vadodara, Gujarat, India")

    monkeypatch.setattr(geocode, "geocode", fake_geocode)
    resolved, dropped = asyncio.run(geocode.resolve_locations(None, parsed()))
    assert dropped == 0
    for ev in resolved:
        assert ev["place_name"] == "Vadodara, Gujarat, India"   # refined from geocoder
        assert "_refine_place" not in ev
        assert "_geo_query" not in ev
    assert_valid_events(resolved)


def test_ungeocodable_gdelt_docs_dropped(monkeypatch):
    async def fake_geocode(client, query):
        return None

    monkeypatch.setattr(geocode, "geocode", fake_geocode)
    resolved, dropped = asyncio.run(geocode.resolve_locations(None, parsed()))
    assert resolved == []
    assert dropped == 3
