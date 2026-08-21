import uuid
from pathlib import Path

import anyio

from app.core.config import settings
from app.core.exceptions import StorageError
from app.core.logging import logger
from app.storage.base import BaseStorage


class LocalStorage(BaseStorage):
    """
    Local filesystem implementation of the storage interface.
    Saves documents to a configured local directory.
    """

    def __init__(self) -> None:
        self.base_dir = Path(settings.LOCAL_STORAGE_DIR)
        # Ensure base upload directory exists
        try:
            self.base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.critical(
                f"Failed to create local upload directory {self.base_dir}: {e}"
            )
            raise StorageError(message="Local storage initialization failed") from e

    def _get_absolute_path(self, storage_key: str) -> Path:
        """Resolves a storage key into an absolute local path, preventing path traversal."""
        path = (self.base_dir / storage_key).resolve()
        # Verify resolved path is strictly under base upload directory
        if not path.is_relative_to(self.base_dir.resolve()):
            raise StorageError(message="Access denied: path traversal attempt detected")
        return path

    async def upload_file(
        self, file_content: bytes, filename: str, path_prefix: str = ""
    ) -> str:
        """
        Saves file bytes to local disk.
        Generates a unique path prefix key using UUIDs to prevent name collisions.
        """
        # Create key: "path_prefix/uuid_filename" or "uuid_filename"
        unique_name = f"{uuid.uuid4()}_{filename}"
        storage_key = (
            str(Path(path_prefix) / unique_name) if path_prefix else unique_name
        )
        abs_path = self._get_absolute_path(storage_key)

        try:
            # Ensure parent subdirectories exist
            def ensure_dir():
                abs_path.parent.mkdir(parents=True, exist_ok=True)

            await anyio.to_thread.run_sync(ensure_dir)

            # Write file content asynchronously in a threadpool to prevent blocking the event loop
            def write_file():
                with abs_path.open("wb") as f:
                    f.write(file_content)

            await anyio.to_thread.run_sync(write_file)
            logger.info(f"File uploaded locally: {storage_key}")
            return storage_key
        except Exception as e:
            logger.error(f"Failed to write file locally: {e}")
            raise StorageError(message="Failed to write file to local disk") from e

    async def download_file(self, storage_key: str) -> bytes:
        """Reads file bytes from local disk."""
        abs_path = self._get_absolute_path(storage_key)
        if not abs_path.exists():
            logger.warning(f"File not found in local storage: {storage_key}")
            raise StorageError(message="Requested file does not exist")

        try:

            def read_file() -> bytes:
                with abs_path.open("rb") as f:
                    return f.read()

            return await anyio.to_thread.run_sync(read_file)
        except Exception as e:
            logger.error(f"Failed to read file from disk: {e}")
            raise StorageError(message="Failed to read file from local disk") from e

    async def delete_file(self, storage_key: str) -> None:
        """Removes the file from local disk."""
        abs_path = self._get_absolute_path(storage_key)
        if not abs_path.exists():
            logger.warning(f"File to delete not found in local storage: {storage_key}")
            return

        try:

            def remove_file():
                if abs_path.exists():
                    abs_path.unlink()

            await anyio.to_thread.run_sync(remove_file)
            logger.info(f"File deleted from local storage: {storage_key}")
        except Exception as e:
            logger.error(f"Failed to delete file from disk: {e}")
            raise StorageError(message="Failed to delete file from local disk") from e
