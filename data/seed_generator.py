"""Deterministic seed generator for the demo company (Session A implements).

Reads data/company_profile.json (or company_profile.pharma.json via COMPANY_PROFILE),
writes suppliers/components/products/bom/inventory/supplier-graph docs to Elastic, and
re-emits the contracts/fixtures/ golden subset so seed data and fixtures never drift
(impl plan §4). Fixed seed=42 — runs must be byte-identical.

Phase 0: runnable no-op that loads the profile + golden fixtures and verifies the
canonical IDs are mutually consistent. Run: python3 data/seed_generator.py --dry-run
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "fixtures"


def main() -> int:
    profile = json.loads((Path(__file__).parent / "company_profile.json").read_text(encoding="utf-8"))
    suppliers = {s["supplier_id"] for s in json.loads((FIXTURES / "suppliers.json").read_text(encoding="utf-8"))}
    products = {p["product_id"] for p in json.loads((FIXTURES / "products.json").read_text(encoding="utf-8"))}
    edges = json.loads((FIXTURES / "supplier_graph.json").read_text(encoding="utf-8"))

    for chain in profile["disruptable_chains"]:
        assert chain["chokepoint"] in suppliers, f"unknown chokepoint {chain['chokepoint']}"
        assert set(chain["products"]) <= products, f"unknown product in chain {chain['name']}"
    for edge in edges:
        assert edge["src_id"] in suppliers, f"dangling edge src {edge['src_id']}"
        assert edge["dst_id"] in suppliers | products, f"dangling edge dst {edge['dst_id']}"

    print(f"phase0 stub OK — profile '{profile['company']['name']}' consistent with fixtures "
          f"({len(suppliers)} suppliers, {len(products)} products, {len(edges)} graph edges). "
          "Session A implements the Elastic writes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
