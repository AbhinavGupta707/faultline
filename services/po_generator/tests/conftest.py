"""Test wiring for po_generator — offline (no GCS, no network)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
FIXTURE = REPO_ROOT / "contracts" / "fixtures" / "draft_po.json"

if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


@pytest.fixture(scope="session")
def draft_po() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))
