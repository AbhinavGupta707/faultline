"""Create the six Faultline Agent Builder tools (and their workflow backend).

Idempotent: deletes any existing same-named workflow / same-id tools, then (re)creates
from the checked-in definitions in elastic/tools/*.json + elastic/tools/_workflows/*.yaml.
Once created they are automatically exposed at {KIBANA_URL}/api/agent_builder/mcp.

  search_events · match_event_to_suppliers · traverse_supply_graph ·
  lookup_exposure · find_alternate_suppliers   -> ES|QL tools
  write_decision                                -> workflow tool (elasticsearch.index step)

Run:
  python3 elastic/setup_tools.py            # create/update on the cluster
  python3 elastic/setup_tools.py --check    # just list what's currently registered
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
TOOLS_DIR = HERE / "tools"
WF_DIR = TOOLS_DIR / "_workflows"
WRITE_DECISION_WF_NAME = "faultline_write_decision"

# the five ES|QL tool definition files (write_decision is built after its workflow exists)
ESQL_TOOL_FILES = [
    "search_events.json",
    "match_event_to_suppliers.json",
    "traverse_supply_graph.json",
    "lookup_exposure.json",
    "find_alternate_suppliers.json",
]
TOOL_IDS = [json.loads((TOOLS_DIR / f).read_text())["id"] for f in ESQL_TOOL_FILES] + ["write_decision"]


def _delete_workflows_by_name(es, name: str) -> None:
    ws = es.kbn("GET", "/api/workflows").json().get("results", [])
    ids = [w["id"] for w in ws if w["name"] == name]
    if ids:
        es.s.delete(f"{es.kbn_url}/api/workflows",
                    headers={"kbn-xsrf": "true", "Content-Type": "application/json"},
                    data=json.dumps({"ids": ids}), timeout=30)


def ensure_workflow(es) -> str:
    """(Re)create the write_decision workflow; return its id. Asserts it validates."""
    yaml = (WF_DIR / "write_decision.yaml").read_text(encoding="utf-8")
    _delete_workflows_by_name(es, WRITE_DECISION_WF_NAME)
    r = es.kbn("POST", "/api/workflows", json={"workflows": [{"yaml": yaml}]})
    j = r.json()
    if r.status_code != 200 or not j.get("created"):
        print(f"ERROR creating workflow: {r.status_code} {r.text[:300]}")
        sys.exit(1)
    wf = j["created"][0]
    if not wf.get("valid"):
        print(f"ERROR workflow did not validate: {json.dumps(wf)[:400]}")
        sys.exit(1)
    print(f"workflow ok: {wf['id']} (valid)")
    return wf["id"]


def create_tool(es, body: dict) -> None:
    tid = body["id"]
    es.kbn("DELETE", f"/api/agent_builder/tools/{tid}")  # idempotent: ignore 404
    r = es.kbn("POST", "/api/agent_builder/tools", json=body)
    if r.status_code != 200:
        print(f"ERROR creating tool {tid}: {r.status_code} {r.text[:400]}")
        sys.exit(1)
    print(f"tool ok: {tid} ({body['type']})")


def main() -> int:
    sys.path.insert(0, str(HERE))
    from _env import Elastic

    es = Elastic(timeout=60)

    if "--check" in sys.argv:
        res = es.kbn("GET", "/api/agent_builder/tools").json().get("results", [])
        mine = [t for t in res if t["id"] in TOOL_IDS]
        for t in mine:
            print(f"  {t['id']:28} {t['type']}")
        print(f"{len(mine)}/{len(TOOL_IDS)} Faultline tools registered.")
        return 0

    # 1. workflow backend for write_decision
    wf_id = ensure_workflow(es)

    # 2. the five ES|QL tools, from their checked-in defs
    for fname in ESQL_TOOL_FILES:
        body = json.loads((TOOLS_DIR / fname).read_text(encoding="utf-8"))
        create_tool(es, body)

    # 3. write_decision tool, wired to the workflow id we just created, then re-export
    wd_path = TOOLS_DIR / "write_decision.json"
    wd = json.loads(wd_path.read_text(encoding="utf-8"))
    wd["configuration"]["workflow_id"] = wf_id
    create_tool(es, wd)
    wd_path.write_text(json.dumps(wd, indent=2) + "\n", encoding="utf-8")

    print(f"\nsetup_tools OK — {len(TOOL_IDS)} tools registered; exposed at "
          f"{es.kbn_url}/api/agent_builder/mcp")
    return 0


if __name__ == "__main__":
    sys.exit(main())
