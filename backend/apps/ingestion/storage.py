"""
Supabase Storage integration service.

Handles file upload/download to Supabase Storage.
Falls back to local filesystem storage when Supabase is not configured.
"""

import logging
import os
import uuid
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


class StorageBackend:
    """Abstract storage interface."""

    def upload(self, file_content: bytes, path: str) -> str:
        raise NotImplementedError

    def download(self, path: str) -> bytes:
        raise NotImplementedError

    def delete(self, path: str) -> bool:
        raise NotImplementedError


class SupabaseStorageBackend(StorageBackend):
    """Upload/download files using Supabase Storage REST API."""

    def __init__(self):
        self.url = settings.SUPABASE_URL
        self.key = settings.SUPABASE_SERVICE_KEY
        self.bucket = settings.SUPABASE_STORAGE_BUCKET

        if not self.url or not self.key:
            raise ValueError("Supabase URL and service key must be configured.")

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.key}",
            "apikey": self.key,
        }

    def upload(self, file_content: bytes, path: str) -> str:
        import requests

        url = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        response = requests.post(
            url,
            headers={**self._headers(), "Content-Type": "application/octet-stream"},
            data=file_content,
        )
        response.raise_for_status()
        logger.info("Uploaded to Supabase Storage: %s", path)
        return path

    def download(self, path: str) -> bytes:
        import requests

        url = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        response = requests.get(url, headers=self._headers())
        response.raise_for_status()
        return response.content

    def delete(self, path: str) -> bool:
        import requests

        url = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        response = requests.delete(url, headers=self._headers())
        return response.status_code in (200, 204)


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage for development/testing."""

    def __init__(self):
        self.base_dir = Path(settings.BASE_DIR) / "local_uploads"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, file_content: bytes, path: str) -> str:
        file_path = self.base_dir / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_content)
        logger.info("Stored locally: %s", file_path)
        return path

    def download(self, path: str) -> bytes:
        file_path = self.base_dir / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return file_path.read_bytes()

    def delete(self, path: str) -> bool:
        file_path = self.base_dir / path
        if file_path.exists():
            file_path.unlink()
            return True
        return False


def get_storage_backend() -> StorageBackend:
    """Factory — returns Supabase backend if configured, else local."""
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
        try:
            return SupabaseStorageBackend()
        except Exception as e:
            logger.warning("Supabase not available, falling back to local: %s", e)
    return LocalStorageBackend()


def generate_storage_path(org_id: str, filename: str) -> str:
    """Generate a unique storage path that prevents filename collisions."""
    ext = os.path.splitext(filename)[1].lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return f"imports/{org_id}/{unique_name}"
