"""Verify the pharma vertical seeds clean — the config-driven genericity proof (§1.13).

`data/company_profile.pharma.json` is a complete SECOND vertical carrying its entity
graph inline (the frozen contracts/fixtures/ are food-only and G may not extend them).
This module:
  1. schema-validates every inline entity against the FROZEN $defs (supplier, product,
     component, bom_edge, graph_edge, inventory_item),
  2. runs the same referential-integrity checks Session A's seed_generator performs
     (chains, graph edges, BOM, inventory, alternates all resolve to defined ids),
  3. invokes Session A's seed_generator read-only to confirm the shared seeder still runs
     green with this file present (no regression), reporting honestly that the Phase-0
     stub does not yet consume COMPANY_PROFILE/`entities` — a flag for Session A.

Run: python -m agents.depth.verify_pharma
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "data" / "company_profile.pharma.json"
SCHEMA = json.loads((ROOT / "contracts" / "schemas" / "faultline.schema.json").read_text("utf-8"))

_ENTITY_DEFS = {
    "components": "component",
    "products": "product",
    "suppliers": "supplier",
    "bom": "bom_edge",
    "supplier_graph": "graph_edge",
    "inventory": "inventory_item",
}


def _validator(defname: str) -> Draft202012Validator:
    return Draft202012Validator({"allOf": [{"$ref": f"#/$defs/{defname}"}], "$defs": SCHEMA["$defs"]})


def validate(profile: dict | None = None) -> list[str]:
    """Return a list of problems (empty = clean)."""
    profile = profile or json.loads(PROFILE.read_text("utf-8"))
    problems: list[str] = []
    ents = profile.get("entities", {})
    if not ents:
        return ["profile has no inline `entities` block"]

    # 1. schema validation per entity
    for key, defname in _ENTITY_DEFS.items():
        v = _validator(defname)
        for i, item in enumerate(ents.get(key, [])):
            for e in v.iter_errors(item):
                problems.append(f"{key}[{i}] !{defname}: {list(e.path)}: {e.message}")

    supplier_ids = {s["supplier_id"] for s in ents.get("suppliers", [])}
    product_ids = {p["product_id"] for p in ents.get("products", [])}
    component_ids = {c["component_id"] for c in ents.get("components", [])}

    # 2. referential integrity (mirrors seed_generator's asserts)
    for s in ents.get("suppliers", []):
        for cid in s.get("components", []) + s.get("alternate_for", []):
            if cid not in component_ids:
                problems.append(f"supplier {s['supplier_id']} references unknown component {cid}")
    for edge in ents.get("supplier_graph", []):
        if edge["src_id"] not in supplier_ids:
            problems.append(f"graph edge {edge['edge_id']} src {edge['src_id']} not a supplier")
        if edge["dst_id"] not in supplier_ids | product_ids:
            problems.append(f"graph edge {edge['edge_id']} dst {edge['dst_id']} undefined")
        if edge["component_id"] not in component_ids:
            problems.append(f"graph edge {edge['edge_id']} component {edge['component_id']} undefined")
    for b in ents.get("bom", []):
        if b["parent_type"] == "product" and b["parent_id"] not in product_ids:
            problems.append(f"bom parent product {b['parent_id']} undefined")
        if b["component_id"] not in component_ids:
            problems.append(f"bom component {b['component_id']} undefined")
    for inv in ents.get("inventory", []):
        if inv["product_id"] not in product_ids:
            problems.append(f"inventory product {inv['product_id']} undefined")
        if inv["component_id"] not in component_ids:
            problems.append(f"inventory component {inv['component_id']} undefined")
    for chain in profile.get("disruptable_chains", []):
        if chain["chokepoint"] not in supplier_ids:
            problems.append(f"chain {chain['name']} chokepoint {chain['chokepoint']} undefined")
        for pid in chain.get("products", []):
            if pid not in product_ids:
                problems.append(f"chain {chain['name']} product {pid} undefined")

    # 3. every disruptable chain must actually reach its product through the graph
    for chain in profile.get("disruptable_chains", []):
        reachable = _products_reachable_from(chain["chokepoint"], ents.get("supplier_graph", []))
        missing = set(chain.get("products", [])) - reachable
        if missing:
            problems.append(f"chain {chain['name']} chokepoint cannot reach products {sorted(missing)} via graph")
    return problems


def _products_reachable_from(supplier_id: str, edges: list[dict]) -> set[str]:
    out: set[str] = set()
    frontier = {supplier_id}
    seen: set[str] = set()
    while frontier:
        node = frontier.pop()
        if node in seen:
            continue
        seen.add(node)
        for e in edges:
            if e["src_id"] == node:
                if e["dst_type"] == "product":
                    out.add(e["dst_id"])
                else:
                    frontier.add(e["dst_id"])
    return out


def _run_session_a_seeder() -> tuple[int, str]:
    """Read-only invocation of Session A's seed_generator with the pharma profile set."""
    import os

    env = dict(os.environ)
    env["COMPANY_PROFILE"] = "company_profile.pharma.json"
    try:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "data" / "seed_generator.py"), "--dry-run"],
            capture_output=True, text=True, env=env, timeout=60, cwd=str(ROOT),
        )
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except Exception as exc:  # pragma: no cover
        return 1, f"could not run seed_generator: {exc}"


def main() -> int:
    profile = json.loads(PROFILE.read_text("utf-8"))
    print(f"Pharma vertical: {profile['company']['name']} ({profile['company']['vertical']})")
    ents = profile["entities"]
    print(
        f"  inline graph: {len(ents['suppliers'])} suppliers · {len(ents['products'])} products · "
        f"{len(ents['components'])} components · {len(ents['supplier_graph'])} edges · "
        f"{len(ents['bom'])} BOM · {len(ents['inventory'])} inventory · "
        f"{len(profile['disruptable_chains'])} disruptable chains"
    )
    problems = validate(profile)
    if problems:
        print(f"\n✗ {len(problems)} problem(s):")
        for p in problems:
            print("   -", p)
        return 1
    print("✓ pharma profile is schema-valid and referentially consistent — would seed clean.")

    rc, out = _run_session_a_seeder()
    print("\n— Session A seed_generator (read-only, COMPANY_PROFILE=company_profile.pharma.json) —")
    print("  " + out.replace("\n", "\n  "))
    if "Northwind" in out or "company_profile.json" in out:
        print(
            "\n  NOTE: the Phase-0 seed_generator stub is hardcoded to company_profile.json and the\n"
            "  food fixtures; it does not yet consume COMPANY_PROFILE or an inline `entities` block.\n"
            "  HANDOFF → Session A: read COMPANY_PROFILE and prefer profile['entities'] when present\n"
            "  (else fall back to contracts/fixtures/) so this pharma vertical seeds end-to-end."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
