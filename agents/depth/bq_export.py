"""bq_export — stream completed runs into BigQuery, + a 60-day historical backfill.

`export_run(state)` turns a RunState into rows for faultline.runs / .exposures /
.decisions and streams them through the active warehouse (BigQuery online, NDJSON
offline — see warehouse.py). The orchestrator's BQExport depth agent calls this after
every run; it never blocks the core loop (exceptions are swallowed by the caller).

`backfill()` generates ~60 days of *plausible, clearly-labelled* historical runs from
the seed entities so the Analytics panel is rich on camera. Every backfilled row carries
`backfill: true` — this is synthetic history, documented as such in HANDOFF.md and the
README section handed to Session F. It is NOT presented as real incident data.

CLI:
    python -m agents.depth.bq_export create        # create dataset + tables
    python -m agents.depth.bq_export stream        # stream the golden run
    python -m agents.depth.bq_export backfill [--days 60] [--end 2026-06-10] [--reset]
    python -m agents.depth.bq_export counts        # row counts per table
    python -m agents.depth.bq_export query [--window 60]   # print analytics summary
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .runstate import FIXTURES, RunState
from .warehouse import get_warehouse

_SEED = 42


def _suppliers() -> dict[str, dict[str, Any]]:
    rows = json.loads((FIXTURES / "suppliers.json").read_text(encoding="utf-8"))
    return {s["supplier_id"]: s for s in rows}


def _products() -> dict[str, dict[str, Any]]:
    rows = json.loads((FIXTURES / "products.json").read_text(encoding="utf-8"))
    return {p["product_id"]: p for p in rows}


def _run_status(state: RunState) -> str:
    if state.secured:
        return "secured"
    if any(e.get("status") == "at_risk" for e in state.exposures):
        return "at_risk"
    return "watch"


# ── RunState → warehouse rows ───────────────────────────────────────────────────
def run_rows(state: RunState, *, backfill: bool = False, ended_at: str | None = None,
            decisions: list[dict[str, Any]] | None = None) -> dict[str, list[dict[str, Any]]]:
    sup = _suppliers()
    meta = state.run_meta
    started = meta.get("started_at") or _now_iso()
    run_date = started[:10]
    root = state.root_event

    runs_row = {
        "run_id": state.run_id,
        "run_date": run_date,
        "started_at": started,
        "ended_at": ended_at or _now_iso(),
        "mode": state.mode,
        "simulated": state.simulated,
        "root_cause_event_id": root.get("event_id"),
        "root_event_type": root.get("event_type"),
        "place_name": root.get("place_name"),
        "exposures_count": len(state.exposures),
        "dollars_at_risk_total_usd": round(state.dollars_at_risk_total),
        "dollars_at_risk_avoided_usd": round(state.dollars_at_risk_avoided),
        "secured": state.secured,
        "status": _run_status(state),
        "backfill": backfill,
        "generated_at": _now_iso(),
    }

    exposure_rows = []
    for e in state.exposures:
        s = sup.get(e.get("chokepoint_supplier_id"), {})
        exposure_rows.append(
            {
                "exposure_id": e["exposure_id"],
                "run_id": state.run_id,
                "run_date": run_date,
                "rank": e.get("rank"),
                "product_id": e.get("product_id"),
                "product_name": e.get("product_name"),
                "component_id": e.get("component_id"),
                "root_cause_event_id": e.get("root_cause_event_id"),
                "chokepoint_supplier_id": e.get("chokepoint_supplier_id"),
                "chokepoint_name": s.get("name"),
                "chokepoint_country": s.get("country"),
                "chokepoint_tier": s.get("tier"),
                "days_of_cover": e.get("days_of_cover"),
                "est_disruption_days": e.get("est_disruption_days"),
                "dollars_at_risk_usd": e.get("dollars_at_risk_usd"),
                "monthly_revenue_usd": e.get("monthly_revenue_usd"),
                "severity": e.get("severity"),
                "status": e.get("status"),
                "simulated": e.get("simulated", state.simulated),
                "backfill": backfill,
            }
        )

    decision_rows = []
    for d in decisions or []:
        decision_rows.append(
            {
                "decision_id": d["decision_id"],
                "run_id": d.get("run_id", state.run_id),
                "run_date": (d.get("ts") or started)[:10],
                "ts": d.get("ts"),
                "agent": d.get("agent"),
                "kind": d.get("kind"),
                "summary": d.get("summary"),
                "detail": d.get("detail"),
                "evidence_event_ids": d.get("evidence_event_ids") or [],
                "simulated": d.get("simulated", state.simulated),
                "backfill": backfill,
                "related_json": json.dumps(d.get("related") or {}),
            }
        )

    return {"runs": [runs_row], "exposures": exposure_rows, "decisions": decision_rows}


def export_run(state: RunState, *, warehouse=None, backfill: bool = False,
              decisions: list[dict[str, Any]] | None = None) -> dict[str, int]:
    wh = warehouse or get_warehouse()
    wh.ensure_tables()
    rows = run_rows(state, backfill=backfill, decisions=decisions)
    return {t: wh.insert(t, r) for t, r in rows.items()}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ── 60-day backfill ─────────────────────────────────────────────────────────────
# Each seed chain, with the hazard that recurrently hits it and a cadence (mean days
# between incidents). Tuned so the chokepoint ranking resembles the live picture:
# the sole-source Vadodara emulsifier plant recurs most, then the Busan-routed mill,
# then the Minas coffee belt.
_CHAINS = [
    {
        "name": "emulsifier", "chokepoint": "sup-vadodara-chem", "component": "cmp-emulsifier",
        "products": ["prd-granola-bar", "prd-sparkling-botanical"],
        "event_types": ["flood", "industrial_accident", "storm"], "cadence": 4,
        "base_sev": 0.55, "cover": {"prd-granola-bar": 9, "prd-sparkling-botanical": 18},
        "place": "Vadodara, Gujarat, India",
    },
    {
        "name": "aluminium", "chokepoint": "sup-ulsan-mill", "component": "cmp-alu-can",
        "products": ["prd-coldbrew-12oz", "prd-sparkling-botanical"],
        "event_types": ["strike", "storm", "port_disruption"], "cadence": 5,
        "base_sev": 0.42, "cover": {"prd-coldbrew-12oz": 16, "prd-sparkling-botanical": 20},
        "place": "Port of Busan, South Korea",
    },
    {
        "name": "coffee", "chokepoint": "sup-minas-coop", "component": "cmp-coffee-arabica",
        "products": ["prd-coldbrew-12oz"],
        "event_types": ["frost", "drought"], "cadence": 7,
        "base_sev": 0.38, "cover": {"prd-coldbrew-12oz": 11},
        "place": "Varginha, Minas Gerais, Brazil",
    },
    {
        "name": "pet-film", "chokepoint": "sup-gulf-petchem", "component": "cmp-pet-film",
        "products": ["prd-granola-bar"],
        "event_types": ["hurricane", "storm"], "cadence": 9,
        "base_sev": 0.30, "cover": {"prd-granola-bar": 34},
        "place": "Lake Charles, Louisiana, US",
    },
]


def _backfill_run(rng: random.Random, chain: dict, day: date, idx: int,
                 products: dict) -> tuple[RunState, list[dict], bool]:
    run_id = f"run-bf-{day.isoformat()}-{idx:02d}"
    started = f"{day.isoformat()}T09:00:00Z"
    ended = f"{day.isoformat()}T09:03:30Z"
    evt_type = rng.choice(chain["event_types"])
    event_id = f"evt-bf-{chain['name']}-{day.isoformat()}"
    severity = max(0.08, min(0.95, rng.gauss(chain["base_sev"], 0.16)))
    disruption = round(6 + severity * 22)  # 6..27 days scaled by severity

    exposures = []
    for rank, pid in enumerate(chain["products"], start=1):
        prod = products[pid]
        cover = max(2, round(chain["cover"][pid] + rng.gauss(0, 2)))
        daily_rev = prod["monthly_revenue_usd"] / 30.0
        at_risk = round(daily_rev * max(0, disruption - cover))
        status = "at_risk" if (at_risk > 0 and severity >= 0.5) else "watch"
        exposures.append(
            {
                "exposure_id": f"exp-{run_id}-{rank}",
                "rank": rank,
                "product_id": pid,
                "product_name": prod["name"],
                "component_id": chain["component"],
                "root_cause_event_id": event_id,
                "chokepoint_supplier_id": chain["chokepoint"],
                "days_of_cover": cover,
                "est_disruption_days": disruption,
                "dollars_at_risk_usd": at_risk,
                "monthly_revenue_usd": prod["monthly_revenue_usd"],
                "severity": round(severity, 3),
                "status": status,
                "evidence_event_ids": [event_id],
                "path_ids": [],
                "simulated": False,
            }
        )

    # Did the tower secure the top exposure? More likely when severe enough to act on.
    top = exposures[0]
    secured = top["status"] == "at_risk" and rng.random() < 0.72
    verify = {}
    if secured:
        top["status"] = "secured"
        verify = {
            "exposure_id": top["exposure_id"], "product_id": top["product_id"],
            "gap_closed": True, "days_of_cover": top["days_of_cover"],
            "alternate_lead_time_days": max(1, top["days_of_cover"] - rng.randint(1, 3)),
            "margin_days": rng.randint(1, 4),
            "residual_risk": {"level": rng.choice(["low", "medium"]), "factors": ["backfill"]},
            "summary": "Backfilled historical resolution.",
            "evidence_event_ids": [event_id],
        }

    state = RunState(
        {
            "run_meta": {"run_id": run_id, "mode": "live", "started_at": started},
            "relevant_events": {
                "events": [
                    {
                        "event_id": event_id, "title": f"{evt_type} near {chain['place']}",
                        "source": "seed", "event_type": evt_type, "severity_raw": round(severity, 3),
                        "location": {"lat": 0.0, "lon": 0.0}, "place_name": chain["place"],
                        "published_at": started, "simulated": False,
                        "why_relevant": f"Historical {chain['name']} chain incident (backfill).",
                        "supplier_hints": [chain["chokepoint"]],
                    }
                ]
            },
            "ranked_exposures": {"exposures": exposures},
            "verify_result": verify,
        }
    )

    decisions = [
        {
            "decision_id": f"dec-{run_id}-assess", "run_id": run_id, "ts": started,
            "agent": "assessor", "kind": "assess",
            "summary": f"{chain['name']} chain {evt_type}: {len(exposures)} exposure(s), "
                       f"${state.dollars_at_risk_total:,.0f} at risk.",
            "evidence_event_ids": [event_id],
            "related": {"supplier_ids": [chain["chokepoint"]],
                        "product_ids": chain["products"], "component_ids": [chain["component"]]},
        }
    ]
    if secured:
        decisions.append(
            {
                "decision_id": f"dec-{run_id}-verify", "run_id": run_id, "ts": ended,
                "agent": "verifier", "kind": "verify",
                "summary": f"Gap closed for {top['product_name']} (backfill).",
                "evidence_event_ids": [event_id],
                "related": {"product_ids": [top["product_id"]]},
            }
        )
    return state, decisions, secured


def generate_backfill(days: int = 60, end: date | None = None,
                     seed: int = _SEED) -> list[tuple[RunState, list[dict]]]:
    end = end or datetime.now(timezone.utc).date()
    rng = random.Random(seed)
    products = _products()
    out: list[tuple[RunState, list[dict]]] = []
    for chain in _CHAINS:
        # walk the window day-by-day, firing on a jittered cadence
        gap = rng.randint(2, chain["cadence"])
        d = end - timedelta(days=days)
        while d <= end:
            if gap <= 0:
                idx = sum(1 for s, _ in out if s.run_id.startswith(f"run-bf-{d.isoformat()}"))
                state, decisions, _ = _backfill_run(rng, chain, d, idx, products)
                out.append((state, decisions))
                gap = max(3, round(rng.gauss(chain["cadence"], chain["cadence"] / 3)))
            gap -= 1
            d += timedelta(days=1)
    out.sort(key=lambda sd: sd[0].run_meta.get("started_at", ""))
    return out


def backfill(days: int = 60, end: date | None = None, reset: bool = False, warehouse=None) -> dict[str, int]:
    wh = warehouse or get_warehouse()
    wh.ensure_tables()
    if reset and hasattr(wh, "truncate"):
        for t in ("runs", "exposures", "decisions"):
            wh.truncate(t)
    totals = {"runs": 0, "exposures": 0, "decisions": 0}
    for state, decisions in generate_backfill(days=days, end=end):
        rows = run_rows(state, backfill=True, decisions=decisions,
                        ended_at=state.run_meta.get("started_at"))
        for t, r in rows.items():
            totals[t] += wh.insert(t, r)
    return totals


# ── CLI ──────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agents.depth.bq_export")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create")
    sub.add_parser("stream")
    bf = sub.add_parser("backfill")
    bf.add_argument("--days", type=int, default=60)
    bf.add_argument("--end", type=str, default=None, help="YYYY-MM-DD (default: today)")
    bf.add_argument("--reset", action="store_true")
    sub.add_parser("counts")
    q = sub.add_parser("query")
    q.add_argument("--window", type=int, default=60)
    args = ap.parse_args(argv)

    wh = get_warehouse()
    print(f"warehouse backend: {wh.backend}")

    if args.cmd == "create":
        wh.ensure_tables()
        print(f"tables ready: {list(wh.counts().keys() if hasattr(wh,'counts') else [])}")
    elif args.cmd == "stream":
        from .runstate import RunState as RS
        decisions = json.loads((FIXTURES / "decision_log.json").read_text(encoding="utf-8"))
        n = export_run(RS.golden(), warehouse=wh, decisions=decisions)
        print(f"streamed golden run: {n}")
    elif args.cmd == "backfill":
        end = date.fromisoformat(args.end) if args.end else None
        totals = backfill(days=args.days, end=end, reset=args.reset, warehouse=wh)
        print(f"backfilled {totals}")
    elif args.cmd == "counts":
        print(json.dumps(wh.counts(), indent=2))
    elif args.cmd == "query":
        print(json.dumps(wh.query_summary(args.window), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
