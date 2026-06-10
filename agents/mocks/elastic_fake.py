"""Fixture-backed fake Elastic tools — identical names/signatures to the MCP tools.

Lets Session B build the full pipeline before Elastic exists (ELASTIC_MODE=mock).
I/O shapes are FROZEN per contracts/elastic_tools.md.

Behaviour (extended per the Phase 0 note "Session B extends behaviour"):
- Dataset-backed: loads the mutually-consistent golden fixtures (suppliers, graph,
  inventory, products, components, world events) and implements real logic over
  them — keyword+geo supplier matching, BFS graph traversal, inventory joins —
  so what-if scenarios anywhere on the map flow through the identical pipeline.
- Golden-input fidelity: the canonical Gujarat-flood text returns
  fixtures/supplier_matches.json verbatim, and cmp-emulsifier alternates return
  fixtures/alternate_search.json verbatim, keeping the golden path byte-faithful.
- Stateful: `write_world_event` (what-if synthetic events) and `write_decision`
  record in-memory; tests inspect via `decisions()` / reset via `reset_state()`.
"""
import json
import math
import os
import re
from pathlib import Path

FIXTURES = Path(os.getenv("CONTRACTS_DIR", Path(__file__).resolve().parents[2] / "contracts")) / "fixtures"

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "for", "to", "with", "at",
    "is", "are", "after", "near", "from", "by", "its", "his", "her", "their",
    "this", "that", "has", "have", "was", "were", "will", "be", "as", "into",
}


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ── in-memory state ──────────────────────────────────────────────
_extra_events: list[dict] = []   # what-if synthetic docs written by the runtime
_decisions: list[dict] = []      # decision-log writes (tests assert on these)
_datasets: dict = {}


def _data(name: str):
    if name not in _datasets:
        _datasets[name] = _load({
            "events": "world_events.json", "suppliers": "suppliers.json",
            "graph": "supplier_graph.json", "inventory": "inventory.json",
            "products": "products.json", "components": "components.json",
        }[name])
    return _datasets[name]


def reset_state() -> None:
    _extra_events.clear()
    _decisions.clear()
    _datasets.clear()


def decisions() -> list[dict]:
    return list(_decisions)


def write_world_event(doc: dict) -> None:
    """What-if path: the runtime indexes a synthetic simulated:true event here."""
    _extra_events.append(doc)


# ── helpers ──────────────────────────────────────────────────────
def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2 and t not in _STOPWORDS}


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    rl1, rl2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = rl2 - rl1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rl1) * math.cos(rl2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


# ── the six contract tools ───────────────────────────────────────
def search_events(query: str, **kwargs) -> dict:
    events = list(_data("events")) + list(_extra_events)
    if not kwargs.get("include_simulated", False):
        events = [e for e in events if not e["simulated"]]
    if kwargs.get("from"):
        events = [e for e in events if e["published_at"] >= kwargs["from"]]
    if kwargs.get("to"):
        events = [e for e in events if e["published_at"] <= kwargs["to"]]
    size = kwargs.get("size", 20)
    events = sorted(events, key=lambda e: e["severity_raw"], reverse=True)[:size]
    return {"events": events, "total": len(events)}


def match_event_to_suppliers(event_text: str, **kwargs) -> dict:
    text = event_text.lower()
    # Golden-input fidelity: the canonical Gujarat flood returns the golden fixture.
    if ("vadodara" in text or "gujarat" in text) and "flood" in text:
        return _load("supplier_matches.json")

    lat, lon = kwargs.get("lat"), kwargs.get("lon")
    radius_km = kwargs.get("radius_km") or 500
    size = kwargs.get("size", 10)
    ev_tokens = _tokens(event_text)
    matches = []
    for sup in _data("suppliers"):
        prof_tokens = _tokens(f"{sup['name']} {sup.get('profile_semantic', '')}")
        overlap = len(ev_tokens & prof_tokens)
        kw = min(1.0, overlap / 6)
        prox, dist = 0.0, None
        if lat is not None and lon is not None:
            dist = _haversine_km(lat, lon, sup["location"]["lat"], sup["location"]["lon"])
            prox = max(0.0, 1 - dist / radius_km) if dist <= radius_km else 0.0
        score = round(min(0.97, 0.55 * kw + 0.45 * prox), 2)
        if score >= 0.2:
            signals = {"semantic_score": round(kw, 2), "bm25_score": round(overlap * 1.7, 1)}
            if dist is not None:
                signals["geo_distance_km"] = round(dist, 1)
            matches.append({"supplier": sup, "score": score, "signals": signals})
    matches.sort(key=lambda m: m["score"], reverse=True)
    return {"matches": matches[:size]}


def traverse_supply_graph(supplier_ids: list, **kwargs) -> dict:
    max_hops = kwargs.get("max_hops", 4)
    suppliers = {s["supplier_id"]: s for s in _data("suppliers")}
    products = {p["product_id"]: p for p in _data("products")}
    components = {c["component_id"]: c for c in _data("components")}
    edges = _data("graph")

    def node(sid: str) -> dict:
        s = suppliers[sid]
        return {"supplier_id": sid, "name": s["name"], "tier": s["tier"],
                "location": s["location"], "country": s["country"]}

    paths = []

    def walk(current: str, chain: list[str], component_id):
        if len(chain) > max_hops:
            return
        for e in edges:
            if e["src_id"] != current:
                continue
            comp = component_id or e["component_id"]
            if e["component_id"] != comp:
                continue
            if e["dst_type"] == "product":
                paths.append({
                    "root_supplier_id": chain[0],
                    "supplier_chain": [node(s) for s in chain],
                    "component_id": comp,
                    "component_name": components.get(comp, {}).get("name", comp),
                    "product_id": e["dst_id"],
                    "product_name": products.get(e["dst_id"], {}).get("name", e["dst_id"]),
                    "hops": len(chain),
                })
            else:
                walk(e["dst_id"], chain + [e["dst_id"]], comp)

    for root in supplier_ids:
        if root in suppliers:
            walk(root, [root], None)
    return {"paths": paths}


def lookup_exposure(product_ids: list, **kwargs) -> dict:
    component_ids = kwargs.get("component_ids")
    products = {p["product_id"]: p for p in _data("products")}
    rows = []
    for item in _data("inventory"):
        if item["product_id"] not in product_ids:
            continue
        if component_ids and item["component_id"] not in component_ids:
            continue
        prod = products.get(item["product_id"], {})
        rows.append({
            "product_id": item["product_id"],
            "product_name": prod.get("name", item["product_id"]),
            "component_id": item["component_id"],
            "days_of_cover": item["days_of_cover"],
            "on_hand_units": item.get("on_hand_units"),
            "daily_consumption_units": item.get("daily_consumption_units"),
            "unit": item.get("unit"),
            "monthly_revenue_usd": prod.get("monthly_revenue_usd", 0),
        })
    return {"exposures": rows}


def find_alternate_suppliers(component_id: str, **kwargs) -> dict:
    constraints = kwargs.get("constraints") or {}
    exclude = set(constraints.get("exclude_supplier_ids") or [])
    required_certs = set(constraints.get("required_certifications") or [])
    size = kwargs.get("size", 5)

    if component_id == "cmp-emulsifier":
        # Golden-input fidelity: canonical alternates fixture, constraint-filtered.
        alts = _load("alternate_search.json")["alternates"]
    else:
        cap_rank = {"low": 0.0, "medium": 0.1, "high": 0.2}
        alts = [
            {"supplier": s, "score": round(min(0.95, 0.65 + cap_rank[s["capacity"]]
                                               + (0.1 if s.get("expedited_lead_time_days") else 0)), 2)}
            for s in _data("suppliers") if component_id in s.get("alternate_for", [])
        ]
        alts.sort(key=lambda a: a["score"], reverse=True)

    out = []
    for a in alts:
        s = a["supplier"]
        if s["supplier_id"] in exclude:
            continue
        if required_certs and not required_certs.issubset(set(s.get("certifications", []))):
            continue
        if constraints.get("min_capacity"):
            order = ["low", "medium", "high"]
            if order.index(s["capacity"]) < order.index(constraints["min_capacity"]):
                continue
        if constraints.get("max_lead_time_days") is not None:
            effective = s.get("expedited_lead_time_days") or s["lead_time_days"]
            if effective > constraints["max_lead_time_days"]:
                continue
        out.append(a)
    return {"alternates": out[:size]}


def write_decision(**decision) -> dict:
    decision_id = decision.get("decision_id", f"dec-mock-{len(_decisions) + 1:04d}")
    # idempotent on decision_id
    if not any(d.get("decision_id") == decision_id for d in _decisions):
        _decisions.append(dict(decision, decision_id=decision_id))
    return {"acknowledged": True, "decision_id": decision_id, "index": "decision-log"}
