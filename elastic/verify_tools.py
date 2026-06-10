"""End-to-end verification of the six Faultline tools THROUGH the Elastic MCP endpoint.

This is the Session A definition-of-done gate (parallel plan §3): it connects a real MCP
client to {KIBANA_URL}/api/agent_builder/mcp with the ApiKey header, lists the tools, calls
every one, and asserts the golden event->exposure unit cases against the seeded data and the
contract fixtures. A tool that passes in Kibana but not here is NOT done.

Run (after setup_elastic.py + seed_generator.py + setup_tools.py):
  python3 elastic/verify_tools.py
Exit code 0 = all green (safe to write "S1 READY").
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _env import Elastic, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "contracts" / "fixtures"

from mcp.client.streamable_http import streamablehttp_client  # noqa: E402
from mcp import ClientSession  # noqa: E402

FAULTLINE_TOOLS = [
    "search_events", "match_event_to_suppliers", "traverse_supply_graph",
    "lookup_exposure", "find_alternate_suppliers", "write_decision",
]

_results: list[tuple[bool, str]] = []


def check(cond: bool, msg: str) -> None:
    _results.append((bool(cond), msg))
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")


def parse_rows(mcp_result) -> list[dict]:
    """Turn an MCP tool result into a list of row dicts from the esql_results block."""
    text = next((c.text for c in mcp_result.content if getattr(c, "text", None)), None)
    if not text:
        return []
    payload = json.loads(text)
    block = next((r for r in payload.get("results", []) if r.get("type") == "esql_results"), None)
    if not block:
        return []
    cols = [c["name"] for c in block["data"]["columns"]]
    return [dict(zip(cols, vals)) for vals in block["data"]["values"]]


def workflow_status(mcp_result) -> str:
    text = next((c.text for c in mcp_result.content if getattr(c, "text", None)), None)
    if not text:
        return "unknown"
    for r in json.loads(text).get("results", []):
        ex = r.get("data", {}).get("execution")
        if ex:
            return ex.get("status", "unknown")
    return "unknown"


async def run() -> int:
    env = load_env()
    url = env["KIBANA_URL"].rstrip("/") + "/api/agent_builder/mcp"
    headers = {"Authorization": f"ApiKey {env['ELASTIC_API_KEY']}"}

    events = {e["id"]: e for e in json.loads((FIXTURES / "world_events.json").read_text())}
    flood = events["evt-gdacs-flood-guj-20260610"]
    flood_text = flood["title"] + ". " + flood["summary"]

    async with streamablehttp_client(url, headers=headers) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()

            print("\n# MCP connectivity")
            names = {t.name for t in (await s.list_tools()).tools}
            for t in FAULTLINE_TOOLS:
                check(t in names, f"tool '{t}' exposed via MCP")

            print("\n# search_events")
            rows = parse_rows(await s.call_tool("search_events", {
                "query": "flooding at chemical or industrial plants producing food-grade emulsifier", "size": 5}))
            check(len(rows) > 0, "returns events")
            check(rows and rows[0]["id"] == "evt-gdacs-flood-guj-20260610",
                  f"top event is the Vadodara flood (got {rows[0]['id'] if rows else None})")
            check(all(not r_["simulated"] for r_ in rows), "excludes simulated events")

            print("\n# match_event_to_suppliers (the signature ELSER tool)")
            rows = parse_rows(await s.call_tool("match_event_to_suppliers", {
                "event_text": flood_text, "size": 5}))
            check(len(rows) > 0, "returns supplier matches")
            check(rows and rows[0]["supplier_id"] == "sup-vadodara-chem",
                  f"top match is sup-vadodara-chem (got {rows[0]['supplier_id'] if rows else None})")
            check(rows and rows[0]["score"] >= 0.5, f"top match is confident (score={rows[0]['score']:.2f})")
            check(all(0.0 <= r_["score"] <= 1.0 for r_ in rows), "all scores normalized to [0,1]")

            print("\n# traverse_supply_graph")
            rows = parse_rows(await s.call_tool("traverse_supply_graph", {
                "supplier_ids": ["sup-vadodara-chem"]}))
            prods = {r_["product_id"] for r_ in rows}
            check(prods == {"prd-granola-bar", "prd-sparkling-botanical"},
                  f"reaches granola + sparkling (got {sorted(prods)})")
            for r_ in rows:
                chain = json.loads(r_["supplier_chain_json"])
                check(chain[0]["supplier_id"] == "sup-vadodara-chem",
                      f"chain to {r_['product_id']} is rooted at Vadodara")
                check(r_["hops"] == 2 and len(chain) == 2, f"chain to {r_['product_id']} is 2 hops")

            print("\n# lookup_exposure")
            rows = parse_rows(await s.call_tool("lookup_exposure", {
                "product_ids": ["prd-granola-bar", "prd-sparkling-botanical"]}))
            by_key = {(r_["product_id"], r_["component_id"]): r_ for r_ in rows}
            g = by_key.get(("prd-granola-bar", "cmp-emulsifier"))
            sp = by_key.get(("prd-sparkling-botanical", "cmp-emulsifier"))
            check(g and g["days_of_cover"] == 9, f"granola emulsifier cover = 9 (got {g['days_of_cover'] if g else None})")
            check(g and g["monthly_revenue_usd"] == 1150000, "granola monthly revenue = 1.15M")
            check(sp and sp["days_of_cover"] == 18, f"sparkling emulsifier cover = 18 (got {sp['days_of_cover'] if sp else None})")

            print("\n# find_alternate_suppliers")
            rows = parse_rows(await s.call_tool("find_alternate_suppliers", {
                "component_id": "cmp-emulsifier", "size": 5}))
            alts = {r_["supplier_id"] for r_ in rows}
            check(alts == {"sup-jurong-chem", "sup-guadalajara-ing", "sup-lyon-emuls"},
                  f"qualified emulsifier alternates (got {sorted(alts)})")
            check(not (alts & {"sup-vadodara-chem", "sup-mumbai-blend", "sup-rotterdam-blend"}),
                  "excludes the disrupted/primary chain")
            check(rows and rows[0]["supplier_id"] == "sup-jurong-chem",
                  f"top alternate is Jurong (got {rows[0]['supplier_id'] if rows else None})")
            check(all(0.0 <= r_["score"] <= 1.0 for r_ in rows), "all scores normalized to [0,1]")

            print("\n# write_decision (workflow tool -> decision-log)")
            decision = {
                "decision_id": "dec-verify-001", "run_id": "run-verify", "ts": "2026-06-11T00:00:00Z",
                "agent": "Tracer", "kind": "trace",
                "summary": 'Vadodara flood traces to granola + sparkling via emulsifier; "sole-source" exposure',
                "evidence_event_ids": ["evt-gdacs-flood-guj-20260610"], "simulated": False,
                "related": {"supplier_ids": ["sup-vadodara-chem"],
                            "product_ids": ["prd-granola-bar", "prd-sparkling-botanical"]},
            }
            res = await s.call_tool("write_decision", {"doc_json": json.dumps(decision)})
            check(not res.isError and workflow_status(res) == "completed", "write_decision workflow completed")

    # verify the decision actually persisted as a typed doc
    es = Elastic(timeout=30)
    es.es("POST", "/decision-log/_refresh")
    doc = es.es("GET", "/decision-log/_doc/dec-verify-001")
    src = doc.json().get("_source", {}) if doc.status_code == 200 else {}
    check(doc.status_code == 200, "decision persisted at _id = decision_id (idempotent)")
    check(isinstance(src.get("evidence_event_ids"), list)
          and "evt-gdacs-flood-guj-20260610" in src.get("evidence_event_ids", []),
          "evidence_event_ids stored as a real array")
    check(isinstance(src.get("related"), dict), "related stored as a typed object")

    passed = sum(1 for ok, _ in _results if ok)
    total = len(_results)
    print(f"\n{'='*52}\n  {passed}/{total} checks passed")
    if passed == total:
        print("  ALL GREEN — tools verified end-to-end through MCP.")
        return 0
    print("  FAILURES:")
    for ok, msg in _results:
        if not ok:
            print(f"    - {msg}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
