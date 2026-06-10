"""USGS normalizer — offline tests against a captured all_hour.geojson sample."""
from __future__ import annotations

from conftest import load_sample

from es_writer import dedupe
from sources import usgs


def parsed():
    return usgs.parse(load_sample("usgs_all_hour.json"))


def test_parses_features_with_usable_geometry():
    events = parsed()
    # 4 features in the sample; one has empty coordinates and is dropped.
    assert len(events) == 3
    ids = {e["id"] for e in events}
    assert "usgs-us7000qx2026" in ids
    assert "usgs-nodata" not in ids  # empty geometry → dropped


def test_docs_are_contract_valid(assert_valid_events):
    assert_valid_events(parsed())


def test_field_normalization():
    by_id = {e["id"]: e for e in parsed()}
    manay = by_id["usgs-us7000qx2026"]
    assert manay["source"] == "usgs"
    assert manay["event_type"] == "earthquake"
    assert manay["simulated"] is False
    assert manay["location"] == {"lat": 6.9214, "lon": 126.5523}
    assert manay["region"] == "southeast-asia"
    assert manay["place_name"] == "18 km SSE of Manay, Philippines"
    assert manay["url"].endswith("us7000qx2026")
    # event_semantic must never be set by the producer — it auto-populates server-side.
    assert "event_semantic" not in manay


def test_severity_is_normalized_0_1():
    for e in parsed():
        assert 0.0 <= e["severity_raw"] <= 1.0
    by_id = {e["id"]: e for e in parsed()}
    assert by_id["usgs-us7000qx2026"]["severity_raw"] == 0.57  # M5.7 / 10
    assert by_id["usgs-us7000qx9999"]["severity_raw"] == 0.68  # M6.8 / 10


def test_region_bucketing_across_hemispheres():
    by_id = {e["id"]: e for e in parsed()}
    assert by_id["usgs-ci40123456"]["region"] == "north-america"  # Ridgecrest, CA
    assert by_id["usgs-us7000qx9999"]["region"] == "oceania"      # South of Fiji


def test_dedupe_drops_repeat_ids_and_urls():
    events = parsed()
    unique, skipped = dedupe(events + events)  # feed the same batch twice
    assert len(unique) == len(events)
    assert skipped == len(events)
