"""S1 gate, part 2 (manual): every live tool's reshaped output must validate
against its frozen contract output schema ($defs/<tool>_output)."""
import asyncio
import json
from pathlib import Path

import jsonschema

from agents.tools.elastic_mcp import live_call

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "contracts/schemas/faultline.schema.json").read_text(encoding="utf-8"))

CASES = [
    ("search_events", {"query": "flood Gujarat industrial estates", "size": 5}),
    ("match_event_to_suppliers",
     {"event_text": "Severe flooding in Vadodara district, Gujarat — industrial estates "
                    "inundated; production halts at chemical plants in the GIDC estates."}),
    ("traverse_supply_graph", {"supplier_ids": ["sup-vadodara-chem"], "max_hops": 4}),
    ("lookup_exposure", {"product_ids": ["prd-granola-bar", "prd-sparkling-botanical"],
                         "component_ids": ["cmp-emulsifier"]}),
    ("find_alternate_suppliers",
     {"component_id": "cmp-emulsifier",
      "constraints": {"exclude_supplier_ids": ["sup-vadodara-chem"]}, "size": 5}),
    ("write_decision", {
        "decision_id": "dec-s1-adapter-0001", "run_id": "run-s1-adapter",
        "ts": "2026-06-10T23:59:00Z", "agent": "orchestrator", "kind": "other",
        "summary": "S1 adapter validation write", "simulated": False,
        "evidence_event_ids": ["evt-gdacs-flood-guj-20260610"]}),
]


async def main() -> None:
    for tool, args in CASES:
        out = await live_call(tool, args)
        jsonschema.validate(out, {"$ref": f"#/$defs/{tool}_output", "$defs": SCHEMA["$defs"]})
        if tool == "search_events":
            detail = f"{len(out['events'])} events, top: {out['events'][0]['id']}"
        elif tool == "match_event_to_suppliers":
            detail = ", ".join(f"{m['supplier']['supplier_id']}={m['score']:.2f}"
                               for m in out["matches"][:3])
        elif tool == "traverse_supply_graph":
            detail = "; ".join(f"{p['root_supplier_id']}→{p['product_id']} ({p['hops']} hops)"
                               for p in out["paths"])
        elif tool == "lookup_exposure":
            detail = "; ".join(f"{r['product_id']}: cover {r['days_of_cover']}d, "
                               f"${r['monthly_revenue_usd']:,.0f}/mo" for r in out["exposures"])
        elif tool == "find_alternate_suppliers":
            detail = ", ".join(f"{a['supplier']['supplier_id']}={a['score']:.2f}"
                               for a in out["alternates"])
        else:
            detail = json.dumps(out)
        print(f"✓ {tool}: contract-valid · {detail}")


if __name__ == "__main__":
    asyncio.run(main())
