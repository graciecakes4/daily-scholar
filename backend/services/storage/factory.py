"""
Storage backend factory.

Single global instance is fine — both LocalStorage and B2Storage are
stateless w.r.t. the FastAPI lifecycle (boto3 client is thread-safe).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ...config import get_settings
from .interface import Storage


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    """Return the configured storage backend (cached for the process)."""
    settings = get_settings()
    backend = (settings.storage_backend or "local").strip().lower()

    if backend == "local":
        from .local import LocalStorage
        return LocalStorage(root=settings.local_storage_root)
    if backend == "b2":
        from .b2 import B2Storage
        return B2Storage()
    raise ValueError(
        f"Unknown STORAGE_BACKEND={backend!r}. Use 'local' or 'b2'."
    )


def storage_key_from_legacy_path(legacy_path: str) -> str:
    """
    Migrate legacy PaperPDF.file_path values to storage keys.

    Pre-Chunk-C the column held an OS path like './data/papers/<uuid>.pdf'.
    New writes store a relative storage key like 'papers/<uuid>.pdf'. This
    helper normalizes either form to the key — safe to apply to both legacy
    and current rows.
    """
    p = Path(legacy_path)
    # already a key (no leading slash or ./ prefix) — return as-is
    parts = p.parts
    if not parts:
        return legacy_path
    # strip leading ./ or absolute-root markers
    if parts[0] in (".", "/"):
        parts = parts[1:]
    # strip the data/ prefix if present (legacy LocalStorage root)
    if parts and parts[0] == "data":
        parts = parts[1:]
    return "/".join(parts) if parts else legacy_path
