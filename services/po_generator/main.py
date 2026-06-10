"""po_generator — renders a $defs/draft_po_payload to a branded PDF in GCS.

Phase 0 stub — Session D implements per contracts/http_api.md (POST /po/render).
Golden input: contracts/fixtures/draft_po.json.
"""
from fastapi import FastAPI

app = FastAPI(title="po-generator")


@app.get("/health")
def health():
    return {"ok": True, "service": "po-generator", "version": "phase0-stub"}


@app.post("/po/render")
def render_po(po: dict):
    return {"ok": True, "po_id": po.get("po_id", ""),
            "pdf_gcs_uri": f"gs://stub/po/{po.get('po_id', 'unknown')}.pdf"}
