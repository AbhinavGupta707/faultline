"""Upload rendered PO PDFs to GCS.

`upload_pdf(po_id, data)` returns `(gcs_uri, uploaded)`. The `google-cloud-storage`
import and the client build are lazy, and any failure (no bucket configured, missing
credentials, network/permission error) degrades to a dry run: the canonical
`gs://{bucket}/po/{po_id}.pdf` URI is still returned with `uploaded=False`, and the
bytes are written under /tmp so the PDF is inspectable locally. The PO contract is
satisfied either way; flipping to real uploads is just bucket + credentials.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

DEFAULT_BUCKET = "faultline-assets"


def object_path(po_id: str) -> str:
    return f"po/{po_id}.pdf"


def gcs_uri(po_id: str, bucket: str | None = None) -> str:
    bucket = bucket or os.getenv("GCS_BUCKET", DEFAULT_BUCKET)
    return f"gs://{bucket}/{object_path(po_id)}"


def upload_pdf(po_id: str, data: bytes) -> tuple[str, bool]:
    bucket_name = os.getenv("GCS_BUCKET", DEFAULT_BUCKET)
    uri = gcs_uri(po_id, bucket_name)

    if os.getenv("PO_UPLOAD", "auto") == "off" or not os.getenv("GCS_BUCKET"):
        return _dry_run(po_id, data, uri)

    try:
        from google.cloud import storage  # noqa: PLC0415 - lazy by design

        client = storage.Client()
        blob = client.bucket(bucket_name).blob(object_path(po_id))
        blob.upload_from_string(data, content_type="application/pdf")
        return uri, True
    except Exception:
        # Never fail the request on an upload problem — fall back to dry run.
        return _dry_run(po_id, data, uri)


def _dry_run(po_id: str, data: bytes, uri: str) -> tuple[str, bool]:
    out = Path(tempfile.gettempdir()) / "faultline-po" / f"{po_id}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return uri, False
