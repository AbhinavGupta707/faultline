"""GDACS RSS/XML normalizer — offline tests against a captured rss.xml sample."""
from __future__ import annotations

from pathlib import Path

from sources import gdacs

SAMPLE = Path(__file__).resolve().parent / "samples" / "gdacs_rss.xml"


def parsed():
    return gdacs.parse(SAMPLE.read_text(encoding="utf-8"))


def test_parses_items_with_coordinates():
    events = parsed()
    # 4 items; the last has no geo point and is skipped.
    assert len(events) == 3
    ids = {e["id"] for e in events}
    assert "gdacs-FL-1062026" in ids
    assert not any(e["id"] == "gdacs-VO-000000" for e in events)


def test_event_type_and_severity_mapping():
    by_id = {e["id"]: e for e in parsed()}
    assert by_id["gdacs-FL-1062026"]["event_type"] == "flood"
    assert by_id["gdacs-FL-1062026"]["severity_raw"] == 0.6   # Orange
    assert by_id["gdacs-TC-900012"]["event_type"] == "hurricane"
    assert by_id["gdacs-TC-900012"]["severity_raw"] == 0.9    # Red
    assert by_id["gdacs-EQ-770088"]["event_type"] == "earthquake"
    assert by_id["gdacs-EQ-770088"]["severity_raw"] == 0.3    # Green


def test_coordinates_from_geo_point_and_georss():
    by_id = {e["id"]: e for e in parsed()}
    # geo:Point form
    assert by_id["gdacs-FL-1062026"]["location"] == {"lat": 22.31, "lon": 73.18}
    assert by_id["gdacs-FL-1062026"]["region"] == "south-asia"
    # flat geo:lat/geo:long form
    assert by_id["gdacs-TC-900012"]["location"] == {"lat": 29.76, "lon": -93.3}
    # georss:point fallback
    assert by_id["gdacs-EQ-770088"]["location"] == {"lat": -23.65, "lon": -70.4}


def test_pubdate_to_iso_utc():
    by_id = {e["id"]: e for e in parsed()}
    assert by_id["gdacs-FL-1062026"]["published_at"] == "2026-06-10T08:42:00Z"


def test_fields_and_url():
    by_id = {e["id"]: e for e in parsed()}
    fl = by_id["gdacs-FL-1062026"]
    assert fl["source"] == "gdacs"
    assert fl["place_name"] == "India"
    assert fl["url"].endswith("eventtype=FL")
    assert "Gujarat" in fl["summary"]


def test_docs_are_contract_valid(assert_valid_events):
    assert_valid_events(parsed())
