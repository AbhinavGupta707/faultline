"""Tiny .env loader + Elastic/Kibana HTTP helpers shared by Session A scripts.

No third-party config deps — parses the repo-root .env, strips inline `#` comments,
and exposes thin requests-based clients for the ES data plane and the Kibana control
plane (Agent Builder / workflows). Session A owns elastic/ and data/ only.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path | None = None) -> dict[str, str]:
    """Parse .env into a dict and also populate os.environ (without overriding existing)."""
    env_path = path or (ROOT / ".env")
    env: dict[str, str] = {}
    if not env_path.exists():
        return env
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # strip a trailing inline comment that follows whitespace (keys/urls have no spaces)
        if " #" in val:
            val = val.split(" #", 1)[0].strip()
        # strip surrounding quotes if present
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        env[key] = val
        os.environ.setdefault(key, val)
    return env


class Elastic:
    """Minimal client for the two planes we need."""

    def __init__(self, env: dict[str, str] | None = None, timeout: int = 60):
        self.env = env or load_env()
        self.es_url = self.env["ELASTIC_ES_URL"].rstrip("/")
        self.kbn_url = self.env["KIBANA_URL"].rstrip("/")
        self.api_key = self.env["ELASTIC_API_KEY"]
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"ApiKey {self.api_key}"})

    # --- ES data plane ---
    def es(self, method: str, path: str, **kw) -> requests.Response:
        return self.s.request(
            method, f"{self.es_url}/{path.lstrip('/')}",
            timeout=self.timeout, **kw,
        )

    # --- Kibana control plane (Agent Builder, workflows) ---
    def kbn(self, method: str, path: str, **kw) -> requests.Response:
        headers = {"kbn-xsrf": "true", "Content-Type": "application/json"}
        headers.update(kw.pop("headers", {}))
        return self.s.request(
            method, f"{self.kbn_url}/{path.lstrip('/')}",
            headers=headers, timeout=self.timeout, **kw,
        )
