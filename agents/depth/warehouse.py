"""BigQuery warehouse for completed runs — with an offline local backend.

Tables (dataset `faultline`, schemas mirror contracts/ — no translation layer):
    faultline.runs        one row per completed run (timings + run-level $ rollups)
    faultline.exposures   one row per ranked exposure ($defs/exposure + run linkage)
    faultline.decisions   one row per decision-log doc ($defs/decision + run linkage)

Two interchangeable backends, selected by environment:
  * BigQueryWarehouse — used when google-cloud-bigquery is importable AND
    GCP_PROJECT is set (real streaming inserts via insert_rows_json).
  * LocalWarehouse — NDJSON files under agents/depth/_warehouse/ (gitignored).
    Same row shapes, same query results. This is what lets the Analytics panel
    render live off 60 days of backfill with zero cloud dependency for dev/demo.

`get_warehouse()` picks the backend; force one with FAULTLINE_WAREHOUSE=local|bq.
The query logic (`query_summary`) is identical in spirit across backends so the
`/analytics/summary` endpoint behaves the same online and offline.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

DATASET = os.getenv("BQ_DATASET", "faultline")
_LOCAL_DIR = Path(__file__).resolve().parent / "_warehouse"

# ── Table schemas (name, BQ type, mode) — the single source mirrored to BQ ──────
RUNS_SCHEMA = [
    ("run_id", "STRING", "REQUIRED"),
    ("run_date", "DATE", "REQUIRED"),
    ("started_at", "TIMESTAMP", "NULLABLE"),
    ("ended_at", "TIMESTAMP", "NULLABLE"),
    ("mode", "STRING", "NULLABLE"),
    ("simulated", "BOOL", "NULLABLE"),
    ("root_cause_event_id", "STRING", "NULLABLE"),
    ("root_event_type", "STRING", "NULLABLE"),
    ("place_name", "STRING", "NULLABLE"),
    ("exposures_count", "INTEGER", "NULLABLE"),
    ("dollars_at_risk_total_usd", "FLOAT", "NULLABLE"),
    ("dollars_at_risk_avoided_usd", "FLOAT", "NULLABLE"),
    ("secured", "BOOL", "NULLABLE"),
    ("status", "STRING", "NULLABLE"),
    ("backfill", "BOOL", "NULLABLE"),
    ("generated_at", "TIMESTAMP", "NULLABLE"),
]

EXPOSURES_SCHEMA = [
    ("exposure_id", "STRING", "REQUIRED"),
    ("run_id", "STRING", "REQUIRED"),
    ("run_date", "DATE", "REQUIRED"),
    ("rank", "INTEGER", "NULLABLE"),
    ("product_id", "STRING", "NULLABLE"),
    ("product_name", "STRING", "NULLABLE"),
    ("component_id", "STRING", "NULLABLE"),
    ("root_cause_event_id", "STRING", "NULLABLE"),
    ("chokepoint_supplier_id", "STRING", "NULLABLE"),
    ("chokepoint_name", "STRING", "NULLABLE"),
    ("chokepoint_country", "STRING", "NULLABLE"),
    ("chokepoint_tier", "INTEGER", "NULLABLE"),
    ("days_of_cover", "FLOAT", "NULLABLE"),
    ("est_disruption_days", "FLOAT", "NULLABLE"),
    ("dollars_at_risk_usd", "FLOAT", "NULLABLE"),
    ("monthly_revenue_usd", "FLOAT", "NULLABLE"),
    ("severity", "FLOAT", "NULLABLE"),
    ("status", "STRING", "NULLABLE"),
    ("simulated", "BOOL", "NULLABLE"),
    ("backfill", "BOOL", "NULLABLE"),
]

DECISIONS_SCHEMA = [
    ("decision_id", "STRING", "REQUIRED"),
    ("run_id", "STRING", "REQUIRED"),
    ("run_date", "DATE", "REQUIRED"),
    ("ts", "TIMESTAMP", "NULLABLE"),
    ("agent", "STRING", "NULLABLE"),
    ("kind", "STRING", "NULLABLE"),
    ("summary", "STRING", "NULLABLE"),
    ("detail", "STRING", "NULLABLE"),
    ("evidence_event_ids", "STRING", "REPEATED"),
    ("simulated", "BOOL", "NULLABLE"),
    ("backfill", "BOOL", "NULLABLE"),
    ("related_json", "STRING", "NULLABLE"),
]

SCHEMAS = {"runs": RUNS_SCHEMA, "exposures": EXPOSURES_SCHEMA, "decisions": DECISIONS_SCHEMA}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _week_start(d: str) -> str:
    dt = date.fromisoformat(d[:10])
    return (dt - timedelta(days=dt.weekday())).isoformat()


def _summarize_rows(
    runs: list[dict[str, Any]],
    exposures: list[dict[str, Any]],
    window_days: int,
    today: date,
) -> dict[str, Any]:
    """Pure-Python analytics rollup shared by both backends (and unit-tested).

    Returns the analytics_summary body *minus* generated_at/window_days, which the
    endpoint stamps. Buckets risk-over-time by ISO week for a clean sparkline.
    """
    cutoff = today - timedelta(days=window_days)
    runs = [r for r in runs if date.fromisoformat(r["run_date"]) >= cutoff]
    run_ids = {r["run_id"] for r in runs}
    exposures = [e for e in exposures if e["run_id"] in run_ids]

    avoided = sum(float(r.get("dollars_at_risk_avoided_usd") or 0) for r in runs)
    includes_backfill = any(r.get("backfill") for r in runs)

    # risk_over_time: avg severity + avg $ at risk per (week, product)
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for e in exposures:
        run_date = next((r["run_date"] for r in runs if r["run_id"] == e["run_id"]), None)
        if not run_date:
            continue
        key = (_week_start(run_date), e["product_id"])
        b = buckets.setdefault(
            key,
            {"sev": [], "dollars": [], "product_name": e.get("product_name")},
        )
        b["sev"].append(float(e.get("severity") or 0))
        b["dollars"].append(float(e.get("dollars_at_risk_usd") or 0))
    risk_over_time = []
    for (wk, pid), b in sorted(buckets.items()):
        risk_over_time.append(
            {
                "date": wk,
                "product_id": pid,
                "product_name": b["product_name"],
                "severity_avg": round(sum(b["sev"]) / len(b["sev"]), 4),
                "dollars_at_risk_usd": round(sum(b["dollars"]) / len(b["dollars"])),
            }
        )

    # top_chokepoints: distinct runs touching each chokepoint supplier
    chokes: dict[str, dict[str, Any]] = {}
    for e in exposures:
        sid = e.get("chokepoint_supplier_id")
        if not sid:
            continue
        c = chokes.setdefault(
            sid,
            {
                "supplier_id": sid,
                "name": e.get("chokepoint_name") or sid,
                "country": e.get("chokepoint_country") or "",
                "tier": e.get("chokepoint_tier"),
                "_runs": set(),
                "_products": set(),
            },
        )
        c["_runs"].add(e["run_id"])
        if e.get("product_id"):
            c["_products"].add(e["product_id"])
    top_chokepoints = []
    for c in sorted(chokes.values(), key=lambda x: (-len(x["_runs"]), x["supplier_id"])):
        top_chokepoints.append(
            {
                "supplier_id": c["supplier_id"],
                "name": c["name"],
                "country": c["country"],
                "tier": c["tier"],
                "incident_count": len(c["_runs"]),
                "products_affected": sorted(c["_products"]),
            }
        )

    return {
        "runs_count": len(run_ids),
        "dollars_at_risk_avoided_usd": round(avoided),
        "includes_backfill": includes_backfill,
        "risk_over_time": risk_over_time,
        "top_chokepoints": top_chokepoints[:8],
    }


class LocalWarehouse:
    """NDJSON-backed offline twin of the BigQuery dataset."""

    backend = "local"

    def __init__(self, root: Path = _LOCAL_DIR):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, table: str) -> Path:
        return self.root / f"{table}.ndjson"

    def ensure_tables(self) -> None:
        for table in SCHEMAS:
            self._path(table).touch(exist_ok=True)

    def _read(self, table: str) -> list[dict[str, Any]]:
        p = self._path(table)
        if not p.exists():
            return []
        return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]

    def insert(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        existing = self._read(table)
        # de-dupe on the table's first (required) key
        keyname = SCHEMAS[table][0][0]
        seen = {r.get(keyname) for r in existing}
        fresh = [r for r in rows if r.get(keyname) not in seen]
        with self._path(table).open("a", encoding="utf-8") as f:
            for r in fresh:
                f.write(json.dumps(r) + "\n")
        return len(fresh)

    def truncate(self, table: str) -> None:
        self._path(table).write_text("", encoding="utf-8")

    def counts(self) -> dict[str, int]:
        return {t: len(self._read(t)) for t in SCHEMAS}

    def query_summary(self, window_days: int, today: date | None = None) -> dict[str, Any]:
        today = today or datetime.now(timezone.utc).date()
        return _summarize_rows(self._read("runs"), self._read("exposures"), window_days, today)


class BigQueryWarehouse:
    """Real BigQuery backend (streaming inserts via insert_rows_json)."""

    backend = "bq"

    def __init__(self, project: str | None = None, dataset: str = DATASET):
        from google.cloud import bigquery  # lazy

        self._bq = bigquery
        self.client = bigquery.Client(project=project) if project else bigquery.Client()
        self.dataset = dataset

    def _table_id(self, table: str) -> str:
        return f"{self.client.project}.{self.dataset}.{table}"

    def ensure_tables(self) -> None:
        bq = self._bq
        ds_ref = self._bq.Dataset(f"{self.client.project}.{self.dataset}")
        try:
            self.client.get_dataset(ds_ref)
        except Exception:
            self.client.create_dataset(ds_ref, exists_ok=True)
        for table, schema in SCHEMAS.items():
            fields = [bq.SchemaField(n, t, mode=m) for (n, t, m) in schema]
            tbl = bq.Table(self._table_id(table), schema=fields)
            self.client.create_table(tbl, exists_ok=True)

    def insert(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        rows = list(rows)
        if not rows:
            return 0
        errors = self.client.insert_rows_json(self._table_id(table), rows)
        if errors:
            raise RuntimeError(f"BigQuery insert errors on {table}: {errors}")
        return len(rows)

    def counts(self) -> dict[str, int]:
        out = {}
        for t in SCHEMAS:
            row = list(self.client.query(f"SELECT COUNT(*) c FROM `{self._table_id(t)}`").result())
            out[t] = int(row[0].c) if row else 0
        return out

    def query_summary(self, window_days: int, today: date | None = None) -> dict[str, Any]:
        # Pull the windowed rows and reuse the shared rollup so online == offline.
        today = today or datetime.now(timezone.utc).date()
        cutoff = (today - timedelta(days=window_days)).isoformat()
        runs = [
            dict(r)
            for r in self.client.query(
                f"SELECT run_id, CAST(run_date AS STRING) run_date, "
                f"dollars_at_risk_avoided_usd, backfill "
                f"FROM `{self._table_id('runs')}` WHERE run_date >= DATE('{cutoff}')"
            ).result()
        ]
        exposures = [
            dict(r)
            for r in self.client.query(
                f"SELECT exposure_id, run_id, product_id, product_name, severity, "
                f"dollars_at_risk_usd, chokepoint_supplier_id, chokepoint_name, "
                f"chokepoint_country, chokepoint_tier "
                f"FROM `{self._table_id('exposures')}` "
                f"WHERE run_id IN (SELECT run_id FROM `{self._table_id('runs')}` "
                f"WHERE run_date >= DATE('{cutoff}'))"
            ).result()
        ]
        return _summarize_rows(runs, exposures, window_days, today)


def get_warehouse():
    """Pick the backend. FAULTLINE_WAREHOUSE=local|bq forces; else auto-detect."""
    forced = os.getenv("FAULTLINE_WAREHOUSE", "").lower()
    if forced == "local":
        return LocalWarehouse()
    if forced == "bq":
        return BigQueryWarehouse(os.getenv("GCP_PROJECT") or None)
    # auto: real BQ only when the client imports AND a project is configured
    if os.getenv("GCP_PROJECT"):
        try:
            import google.cloud.bigquery  # noqa: F401

            return BigQueryWarehouse(os.getenv("GCP_PROJECT"))
        except Exception:
            pass
    return LocalWarehouse()
