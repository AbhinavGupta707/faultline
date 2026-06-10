"""Deterministic seed generator for the demo company — Northwind Provisions.

Source of truth is contracts/fixtures/ (the FROZEN golden subset) + company_profile.json.
The seeder LOADS those canonical docs and bulk-writes them to Elastic, so seed data and
fixtures cannot drift by construction (impl plan §4: "fixtures and seed data never drift").
It additionally derives, deterministically, two materialized artifacts the live tools need:

  * inventory docs are denormalized with product_name + monthly_revenue_usd (so lookup_exposure
    is a single ES|QL FROM with no join);
  * supplier-graph-paths: every root-supplier -> finished-product path, BFS'd from the
    supplier-graph edges (component-scoped), so traverse_supply_graph is a flat lookup
    (ES|QL cannot recurse). supplier_chain is carried as an ordered JSON string.

Fixed seed = 42 (company_profile.json). Indexing uses each doc's natural id as _id, so the
seeder is idempotent — re-running overwrites in place, never duplicates.

Run:
  python3 data/seed_generator.py --dry-run   # build + consistency-check in memory, no writes
  python3 data/seed_generator.py             # bulk-write all indices to the cluster
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "fixtures"
DATA = Path(__file__).parent

SEED = 42


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def build_docs() -> dict[str, list[dict]]:
    """Build every index's docs deterministically from the canonical fixtures."""
    random.seed(SEED)  # reserved for any future jitter; current build is fully deterministic

    suppliers = _load("suppliers.json")
    components = _load("components.json")
    products = _load("products.json")
    bom = _load("bom.json")
    edges = _load("supplier_graph.json")
    inventory = _load("inventory.json")
    events = _load("world_events.json")

    prod_by_id = {p["product_id"]: p for p in products}
    comp_by_id = {c["component_id"]: c for c in components}
    sup_by_id = {s["supplier_id"]: s for s in suppliers}

    # inventory: denormalize product revenue so lookup_exposure needs no join
    inv_docs = []
    for item in inventory:
        prod = prod_by_id[item["product_id"]]
        inv_docs.append({
            **item,
            "product_name": prod["name"],
            "monthly_revenue_usd": prod["monthly_revenue_usd"],
        })

    # supplier-graph-paths: materialize every root -> product path, component-scoped
    edges_by_src: dict[str, list[dict]] = {}
    for e in edges:
        edges_by_src.setdefault(e["src_id"], []).append(e)

    def chain_node(sid: str) -> dict:
        s = sup_by_id[sid]
        return {
            "supplier_id": sid, "name": s["name"], "tier": s["tier"],
            "location": s["location"], "country": s["country"],
        }

    raw_paths: list[dict] = []

    def walk(root: str, current: str, component: str, chain_ids: list[str], route_via):
        for e in edges_by_src.get(current, []):
            if e["component_id"] != component:
                continue
            rv = e.get("route_via", route_via)
            if e["dst_type"] == "product":
                raw_paths.append({
                    "root_supplier_id": root,
                    "chain_ids": list(chain_ids),
                    "component_id": component,
                    "product_id": e["dst_id"],
                    "route_via": rv,
                })
            else:
                walk(root, e["dst_id"], component, chain_ids + [e["dst_id"]], rv)

    for sid in sup_by_id:
        # components for which this supplier is an edge source (i.e. it can push downstream)
        comps = sorted({e["component_id"] for e in edges_by_src.get(sid, [])})
        for comp in comps:
            walk(sid, sid, comp, [sid], None)

    # deterministic ordering + ids
    raw_paths.sort(key=lambda p: (p["root_supplier_id"], p["product_id"],
                                  p["component_id"], "|".join(p["chain_ids"])))
    path_docs = []
    for i, p in enumerate(raw_paths, start=1):
        chain = [chain_node(s) for s in p["chain_ids"]]
        comp = comp_by_id.get(p["component_id"], {})
        prod = prod_by_id.get(p["product_id"], {})
        doc = {
            "path_id": f"pth-{i:04d}",
            "root_supplier_id": p["root_supplier_id"],
            "supplier_chain_json": json.dumps(chain, separators=(",", ":")),
            "component_id": p["component_id"],
            "component_name": comp.get("name", ""),
            "product_id": p["product_id"],
            "product_name": prod.get("name", ""),
            "hops": len(chain),
        }
        if p["route_via"]:
            doc["route_via"] = p["route_via"]
        path_docs.append(doc)

    return {
        "suppliers": suppliers,
        "components": components,
        "products": products,
        "bom": bom,
        "supplier-graph": edges,
        "inventory": inv_docs,
        "world-events": events,
        "supplier-graph-paths": path_docs,
    }


def _doc_id(index: str, doc: dict) -> str:
    key = {
        "suppliers": "supplier_id", "components": "component_id", "products": "product_id",
        "supplier-graph": "edge_id", "supplier-graph-paths": "path_id", "world-events": "id",
    }.get(index)
    if key:
        return str(doc[key])
    if index == "inventory":
        return f"{doc['product_id']}::{doc['component_id']}"
    if index == "bom":
        return f"{doc['parent_id']}::{doc['component_id']}"
    raise ValueError(index)


def consistency_check(docs: dict[str, list[dict]]) -> None:
    """Phase-0 invariants: ids mutually consistent, profile chains resolve, no dangling edges."""
    profile = json.loads((DATA / "company_profile.json").read_text(encoding="utf-8"))
    suppliers = {s["supplier_id"] for s in docs["suppliers"]}
    products = {p["product_id"] for p in docs["products"]}
    for chain in profile["disruptable_chains"]:
        assert chain["chokepoint"] in suppliers, f"unknown chokepoint {chain['chokepoint']}"
        assert set(chain["products"]) <= products, f"unknown product in chain {chain['name']}"
    for edge in docs["supplier-graph"]:
        assert edge["src_id"] in suppliers, f"dangling edge src {edge['src_id']}"
        assert edge["dst_id"] in suppliers | products, f"dangling edge dst {edge['dst_id']}"
    # every chokepoint must reach at least one of its listed products via a precomputed path
    paths = docs["supplier-graph-paths"]
    for chain in profile["disruptable_chains"]:
        reached = {p["product_id"] for p in paths if p["root_supplier_id"] == chain["chokepoint"]}
        assert reached & set(chain["products"]), (
            f"chokepoint {chain['chokepoint']} reaches no product in chain {chain['name']}")


def bulk_write(docs: dict[str, list[dict]]) -> None:
    sys.path.insert(0, str(ROOT / "elastic"))
    from _env import Elastic  # noqa: E402

    es = Elastic(timeout=120)
    for index, items in docs.items():
        lines = []
        for doc in items:
            lines.append(json.dumps({"index": {"_index": index, "_id": _doc_id(index, doc)}}))
            lines.append(json.dumps(doc))
        body = "\n".join(lines) + "\n"
        r = es.es("POST", "/_bulk?refresh=wait_for",
                  data=body.encode("utf-8"),
                  headers={"Content-Type": "application/x-ndjson"})
        if r.status_code != 200:
            print(f"ERROR bulk {index}: {r.status_code} {r.text[:300]}")
            sys.exit(1)
        res = r.json()
        if res.get("errors"):
            first = next((it for it in res["items"] if list(it.values())[0].get("error")), None)
            print(f"ERROR bulk {index}: {json.dumps(first)[:400]}")
            sys.exit(1)
        print(f"indexed {len(items):>3} -> {index}")


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    docs = build_docs()
    consistency_check(docs)

    counts = {k: len(v) for k, v in docs.items()}
    if dry_run:
        print("--dry-run — built + consistency-checked, no cluster writes.")
        for k, v in counts.items():
            print(f"  {k}: {v}")
        return 0

    bulk_write(docs)
    print(f"seed_generator OK — Northwind Provisions seeded "
          f"({counts['suppliers']} suppliers, {counts['products']} products, "
          f"{counts['supplier-graph']} edges, {counts['supplier-graph-paths']} paths, "
          f"{counts['world-events']} events).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
