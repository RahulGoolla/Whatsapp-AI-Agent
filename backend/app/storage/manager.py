from app.core.config import settings
from app.storage.base import BaseStorage
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


def get_storage_client() -> BaseStorage:
    """
    Factory function returning the active storage driver instance
    based on configuration provider settings.
    """
    provider = settings.STORAGE_PROVIDER.lower()
    if provider == "s3":
        return S3Storage()
    elif provider == "local":
        return LocalStorage()
    else:
        raise ValueError(
            f"Unsupported storage provider type: {settings.STORAGE_PROVIDER}"
        )


# Expose a singleton instance for system-wide imports
storage_client = get_storage_client()
