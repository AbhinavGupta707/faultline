"""Idempotent Elastic setup — applies every mapping in elastic/mappings/.

Phase 0 stub (Session A implements): connect with KIBANA_URL-derived ES endpoint +
ELASTIC_API_KEY, create each index if missing (semantic_text uses the managed default
.elser-2-elasticsearch — do NOT create a custom inference id), then create the six
Agent Builder tools from elastic/tools/*.json via POST kbn:/api/agent_builder/tools.

Run: python3 elastic/setup_elastic.py [--dry-run]
"""
import json
import sys
from pathlib import Path

MAPPINGS = Path(__file__).parent / "mappings"


def main() -> int:
    mappings = sorted(MAPPINGS.glob("*.json"))
    for path in mappings:
        json.loads(path.read_text(encoding="utf-8"))  # validate JSON
        print(f"would apply mapping: {path.stem}")
    print(f"phase0 stub — {len(mappings)} mappings validated; Session A wires the cluster calls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
