"""Fixture-backed fake Elastic tools — identical names/signatures to the MCP tools.

Lets Session B build the full pipeline before Elastic exists (ELASTIC_MODE=mock).
Returns the golden fixtures from contracts/fixtures/, which are mutually consistent
(same supplier/product/event ids everywhere). Session B extends behaviour (e.g. param
filtering); the I/O shapes are FROZEN per contracts/elastic_tools.md.
"""
import json
import os
from pathlib import Path

FIXTURES = Path(os.getenv("CONTRACTS_DIR", Path(__file__).resolve().parents[2] / "contracts")) / "fixtures"


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def search_events(query: str, **kwargs) -> dict:
    events = _load("world_events.json")
    if not kwargs.get("include_simulated", False):
        events = [e for e in events if not e["simulated"]]
    return {"events": events, "total": len(events)}


def match_event_to_suppliers(event_text: str, **kwargs) -> dict:
    return _load("supplier_matches.json")


def traverse_supply_graph(supplier_ids: list, **kwargs) -> dict:
    return _load("graph_traversal.json")


def lookup_exposure(product_ids: list, **kwargs) -> dict:
    return _load("exposure_lookup.json")


def find_alternate_suppliers(component_id: str, **kwargs) -> dict:
    return _load("alternate_search.json")


def write_decision(**decision) -> dict:
    return {"acknowledged": True, "decision_id": decision.get("decision_id", "dec-mock"), "index": "decision-log"}
