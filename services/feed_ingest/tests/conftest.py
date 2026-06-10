"""Test wiring: put the service root on sys.path and expose a contract validator.

Tests run fully offline — no network, no Elasticsearch. They load captured sample
payloads from tests/samples/ and assert the normalized docs satisfy the FROZEN
`$defs/world_event` schema.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
SAMPLES = Path(__file__).resolve().parent / "samples"
# contracts/schemas/faultline.schema.json lives 3 levels up from services/feed_ingest/
REPO_ROOT = SERVICE_ROOT.parents[1]
SCHEMA_PATH = REPO_ROOT / "contracts" / "schemas" / "faultline.schema.json"

if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def load_sample(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def world_event_validator():
    """A jsonschema validator bound to $defs/world_event with $ref resolution."""
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    resolver_schema = {**schema, "$ref": "#/$defs/world_event"}
    return Draft202012Validator(resolver_schema)


@pytest.fixture
def assert_valid_events(world_event_validator):
    def _check(events: list[dict]):
        for ev in events:
            errors = sorted(
                world_event_validator.iter_errors(ev), key=lambda e: e.path
            )
            assert not errors, (
                f"{ev.get('id')}: " + "; ".join(e.message for e in errors)
            )

    return _check
