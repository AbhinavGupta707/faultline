"""Test env: mock mode, no cloud deps, no pacing, no background control loop."""
import os
import sys
from pathlib import Path

# Default is hermetic mock; FAULTLINE_TEST_ELASTIC=live runs the same suite
# against the real cluster (the S1 gate: same test green for real).
os.environ["ELASTIC_MODE"] = os.getenv("FAULTLINE_TEST_ELASTIC", "mock")
os.environ["GEMINI_MODE"] = "off"
os.environ["CONTROL_LOOP"] = "0"
os.environ["NARRATION_DELAY_S"] = "0"
os.environ["APPROVAL_TIMEOUT_S"] = "15"

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from agents.mocks import elastic_fake  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_mock_state():
    elastic_fake.reset_state()
    yield
    elastic_fake.reset_state()
