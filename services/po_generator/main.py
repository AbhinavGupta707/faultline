"""po_generator — renders a $defs/draft_po_payload to a branded PDF in GCS.

Contract (contracts/http_api.md):
  POST /po/render   body: draft_po_payload → 200 {ok, po_id, pdf_gcs_uri}
  GET  /health      → health_response (service: "po-generator")

Golden input: contracts/fixtures/draft_po.json.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from gcs import upload_pdf
from pdf import build_po_pdf

app = FastAPI(title="po-generator")


@app.get("/health")
def health():
    return {"ok": True, "service": "po-generator", "version": "0.1.0"}


@app.post("/po/render")
def render_po(po: dict):
    po_id = po.get("po_id")
    if not po_id:
        return JSONResponse(status_code=400, content={"error": "po_id is required"})
    try:
        data = build_po_pdf(po)
    except Exception as exc:  # malformed payload shouldn't 500 silently
        return JSONResponse(status_code=422, content={"error": f"render failed: {exc}"})

    uri, uploaded = upload_pdf(po_id, data)
    return {
        "ok": True,
        "po_id": po_id,
        "pdf_gcs_uri": uri,
        "uploaded": uploaded,
        "bytes": len(data),
        "mode": "live" if uploaded else os.getenv("PO_UPLOAD", "auto"),
    }
