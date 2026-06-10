"""generate_po_pdf tool — renders a $defs/draft_po_payload to PDF in GCS.

Registered on the ToolBelt as a local (non-Elastic) tool so the call still
narrates as a tool.call chip with elastic:false. With PO_GENERATOR_URL set it
POSTs to Session D's service (contracts/http_api.md POST /po/render); otherwise
it returns the deterministic GCS URI the service would produce, so mock-mode
runs and the golden-path test need no network.
"""
from __future__ import annotations

from agents import config


def _fallback_uri(po_id: str) -> str:
    return f"gs://{config.gcs_bucket()}/po/{po_id}.pdf"


async def generate_po_pdf(args: dict) -> dict:
    po = args.get("po") or args
    po_id = po["po_id"]
    base = config.po_generator_url()
    if base:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{base}/po/render", json=po)
                resp.raise_for_status()
                data = resp.json()
                return {"ok": True, "po_id": po_id, "pdf_gcs_uri": data["pdf_gcs_uri"]}
        except Exception:
            # PO rendering must never block the run — fall back to the canonical URI.
            pass
    return {"ok": True, "po_id": po_id, "pdf_gcs_uri": _fallback_uri(po_id)}
