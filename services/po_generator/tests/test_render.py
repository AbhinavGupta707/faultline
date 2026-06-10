"""po_generator — renders the golden draft_po fixture to a PDF, offline."""
from __future__ import annotations

import os

from fastapi.testclient import TestClient

import gcs
import main
from pdf import build_po_pdf


def test_renders_valid_pdf_from_fixture(draft_po):
    data = build_po_pdf(draft_po)
    assert data[:5] == b"%PDF-"          # valid PDF header
    assert b"%%EOF" in data[-1024:]      # proper trailer
    assert len(data) > 3000              # non-trivial, branded content


def test_render_survives_sparse_payload():
    # Only po_id present — every other field optional; must not raise.
    data = build_po_pdf({"po_id": "po-minimal"})
    assert data[:5] == b"%PDF-"


def test_gcs_uri_format():
    assert gcs.gcs_uri("po-2026-0042", bucket="faultline-assets") == (
        "gs://faultline-assets/po/po-2026-0042.pdf"
    )


def test_dry_run_returns_uri_without_upload(draft_po, monkeypatch):
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    uri, uploaded = gcs.upload_pdf(draft_po["po_id"], build_po_pdf(draft_po))
    assert uploaded is False
    assert uri == "gs://faultline-assets/po/po-2026-0042.pdf"


def test_endpoint_renders_and_returns_contract_shape(draft_po, monkeypatch):
    monkeypatch.delenv("GCS_BUCKET", raising=False)
    client = TestClient(main.app)
    resp = client.post("/po/render", json=draft_po)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["po_id"] == "po-2026-0042"
    assert body["pdf_gcs_uri"] == "gs://faultline-assets/po/po-2026-0042.pdf"
    assert body["bytes"] > 3000


def test_endpoint_rejects_missing_po_id():
    client = TestClient(main.app)
    resp = client.post("/po/render", json={"supplier_name": "x"})
    assert resp.status_code == 400
    assert "po_id" in resp.json()["error"]


def test_health():
    client = TestClient(main.app)
    body = client.get("/health").json()
    assert body == {"ok": True, "service": "po-generator", "version": "0.1.0"}
