"""
Filesystem storage backend (default for local / beta).

Keys map directly to paths under `root`. For example, key "papers/abc.pdf"
becomes `<root>/papers/abc.pdf`. Subdirectories are created as needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .interface import Storage


class LocalStorage(Storage):
    backend = "local"

    def __init__(self, root: str = "./data"):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        # disallow .. traversal — keys come from app code, but defense in depth
        if ".." in Path(key).parts:
            raise ValueError(f"invalid storage key {key!r} (contains '..')")
        return self.root / key

    def put(self, key: str, data: bytes, *, content_type: str = "application/octet-stream") -> str:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.exists():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def signed_url(self, key: str, *, expires_seconds: int = 3600) -> Optional[str]:
        # LocalStorage has no notion of a publicly fetchable URL; callers stream
        # the file via the backend instead (FileResponse from local_path()).
        return None

    def local_path(self, key: str) -> Optional[Path]:
        return self._path_for(key)
