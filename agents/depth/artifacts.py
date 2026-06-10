"""Artifact store — writes report / PO bytes to GCS, or to a local mirror offline.

Online: google-cloud-storage + GCS_BUCKET → gs://bucket/key.
Offline (no client or no bucket): agents/depth/_artifacts/key, with a gs:// URI still
returned so emitted payloads look identical to production. `read(key)` serves bytes back
to the /report endpoint regardless of backend.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_LOCAL_DIR = Path(__file__).resolve().parent / "_artifacts"


@dataclass
class StoredArtifact:
    key: str
    uri: str          # gs://... (always, so payloads match prod)
    local_path: str | None  # filesystem path when stored locally
    content_type: str


class ArtifactStore:
    def __init__(self):
        self.bucket = os.getenv("GCS_BUCKET", "").strip()
        self._gcs = None
        if self.bucket:
            try:
                from google.cloud import storage  # lazy

                self._gcs = storage.Client()
            except Exception:
                self._gcs = None
        self._local_root = _LOCAL_DIR
        self._local_root.mkdir(parents=True, exist_ok=True)

    @property
    def backend(self) -> str:
        return "gcs" if self._gcs else "local"

    def _uri(self, key: str) -> str:
        bucket = self.bucket or "faultline-assets"
        return f"gs://{bucket}/{key}"

    def write(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> StoredArtifact:
        if self._gcs:
            blob = self._gcs.bucket(self.bucket).blob(key)
            blob.upload_from_string(data, content_type=content_type)
            return StoredArtifact(key, self._uri(key), None, content_type)
        p = self._local_root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return StoredArtifact(key, self._uri(key), str(p), content_type)

    def read(self, key: str) -> bytes | None:
        if self._gcs:
            blob = self._gcs.bucket(self.bucket).blob(key)
            if blob.exists():
                return blob.download_as_bytes()
            return None
        p = self._local_root / key
        return p.read_bytes() if p.exists() else None

    def exists(self, key: str) -> bool:
        if self._gcs:
            return self._gcs.bucket(self.bucket).blob(key).exists()
        return (self._local_root / key).exists()
