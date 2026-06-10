# po_generator

Cloud Run FastAPI service (Session D). Renders a contingent purchase order to a clean,
branded PDF and stores it in GCS.

Input spec: `$defs/draft_po_payload` in `contracts/schemas/faultline.schema.json` (FROZEN).
Golden input: `contracts/fixtures/draft_po.json`.

## Endpoints
- `POST /po/render` — body is a `draft_po_payload` → `200 {ok, po_id, pdf_gcs_uri, uploaded, bytes}`.
  `400` if `po_id` is missing; `422` on an unrenderable payload.
- `GET /health` → `health_response` (`service: "po-generator"`).

## Rendering
`pdf.build_po_pdf(po) -> bytes` is a pure reportlab renderer (midnight-nautical palette):
branded header, an amber **CONTINGENT** banner ("binding only on operator approval"),
order/terms grid, line item with total, and notes. Missing optional fields degrade
gracefully so a sparse draft still renders.

## Storage
`gcs.upload_pdf` uses a lazily-built `google-cloud-storage` client. With no
`GCS_BUCKET`/credentials (or `PO_UPLOAD=off`), it **dry-runs**: returns the canonical
`gs://{GCS_BUCKET}/po/{po_id}.pdf` URI with `uploaded:false` and writes the bytes under
`/tmp/faultline-po/` for inspection. An upload error never fails the request.

## Config
| env | meaning |
|---|---|
| `GCS_BUCKET` | target bucket (no `gs://`); unset → dry-run |
| `PO_UPLOAD` | `auto` (default) \| `off` |

## Tests
Offline: `python3 -m pytest tests/` — renders the golden fixture and asserts the endpoint
contract shape (no GCS, no network).
