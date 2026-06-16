"""
Storage abstraction.

Two backends share a single interface:
  - LocalStorage  : filesystem under ./data (default; what beta testers use)
  - B2Storage     : Backblaze B2 via S3-compatible boto3 (default for cloud)

Switched at runtime by the STORAGE_BACKEND env var. Code that stores or
retrieves files should never reference Path or boto3 directly — go through
`get_storage()`.
"""

from .interface import Storage
from .factory import get_storage, storage_key_from_legacy_path

__all__ = ["Storage", "get_storage", "storage_key_from_legacy_path"]
