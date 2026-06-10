"""Runtime configuration — every switch is an env var (impl plan §14).

Values are read live (not cached at import) so tests and the mock→live flip
(ELASTIC_MODE) never require a restart of the interpreter. A repo-root `.env`
(copied from infra/env.example) is loaded once at import WITHOUT overriding
real environment variables — Cloud Run env vars and test overrides always win.
"""
import os
from pathlib import Path


def _load_dotenv() -> None:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        else:
            value = value.split(" #")[0].rstrip()  # unquoted inline comments
        os.environ.setdefault(key.strip(), value)


_load_dotenv()


def elastic_mode() -> str:
    """mock | live — the only switch between fixtures and the real cluster."""
    return os.getenv("ELASTIC_MODE", "mock").lower()


def gemini_mode() -> str:
    """auto | off. off = deterministic agent cores only (golden-path test mode)."""
    return os.getenv("GEMINI_MODE", "auto").lower()


def model_pro() -> str:
    return os.getenv("GEMINI_MODEL_PRO", "gemini-3.1-pro")


def model_flash() -> str:
    return os.getenv("GEMINI_MODEL_FLASH", "gemini-3.5-flash")


def kibana_url() -> str:
    return os.getenv("KIBANA_URL", "").rstrip("/")


def elastic_api_key() -> str:
    return os.getenv("ELASTIC_API_KEY", "")


def elasticsearch_url() -> str:
    """Direct ES endpoint — needed only for live-mode what-if event writes.
    Canonical env name is ELASTIC_ES_URL (per infra .env); old alias kept."""
    return (os.getenv("ELASTIC_ES_URL") or os.getenv("ELASTICSEARCH_URL", "")).rstrip("/")


def events_index() -> str:
    return os.getenv("ELASTIC_EVENTS_INDEX", "world-events")


def po_generator_url() -> str:
    return os.getenv("PO_GENERATOR_URL", "").rstrip("/")


def gcs_bucket() -> str:
    return os.getenv("GCS_BUCKET", "faultline-assets")


def buyer_name() -> str:
    return os.getenv("BUYER_NAME", "Northwind Provisions, Inc.")


def control_loop_enabled() -> bool:
    return os.getenv("CONTROL_LOOP", "1") not in ("0", "false", "off")


def poll_interval_s() -> float:
    return float(os.getenv("POLL_INTERVAL_S", "45"))


def narration_delay_s() -> float:
    """Pacing between scripted negotiation-call beats (0 in tests)."""
    return float(os.getenv("NARRATION_DELAY_S", "1.2"))


def approval_timeout_s() -> float:
    """How long a run blocks at the approval gate before treating it as rejected."""
    return float(os.getenv("APPROVAL_TIMEOUT_S", "900"))


def version() -> str:
    return os.getenv("FAULTLINE_VERSION", "0.1.0")
