"""Validates every contract fixture against its canonical JSON Schema (impl plan §15)."""
import json
from pathlib import Path

import pytest
from jsonschema import validate

ROOT = Path(__file__).parent
SCHEMA = json.loads((ROOT / "schemas" / "faultline.schema.json").read_text(encoding="utf-8"))
FIXTURE_MAP = json.loads((ROOT / "schemas" / "fixture_map.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,spec", sorted(FIXTURE_MAP.items()))
def test_fixture_matches_schema(name, spec):
    path = ROOT / "fixtures" / name
    schema = {"$ref": f"#/$defs/{spec['def']}", "$defs": SCHEMA["$defs"]}
    if spec.get("jsonl"):
        docs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        docs = data if spec.get("each") else [data]
    assert docs, f"{name} is empty"
    for doc in docs:
        validate(doc, schema)
