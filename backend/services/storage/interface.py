"""
Storage interface.

All keys are POSIX-style strings ("papers/<uuid>.pdf"). The backend owns the
mapping from key to physical location (a filesystem path, an S3 object, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class Storage(ABC):
    """Vendor-agnostic blob store."""

    # Short identifier for logging / health checks: "local" or "b2".
    backend: str = ""

    @abstractmethod
    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        """Store `data` at `key`. Returns the same key (caller persists it)."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Fetch the bytes stored at `key`. Raises FileNotFoundError if missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove the object. No-op if missing."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if the object exists."""

    @abstractmethod
    def signed_url(self, key: str, *, expires_seconds: int = 3600) -> Optional[str]:
        """
        Time-limited download URL the browser can fetch directly. Returns None
        for backends that don't support presigning (e.g., LocalStorage) — the
        caller must then stream the bytes itself.
        """

    def local_path(self, key: str) -> Optional[Path]:
        """
        For backends that expose a filesystem path (LocalStorage), return it
        so FastAPI can use FileResponse. Returns None for object-store backends.
        """
        return None
