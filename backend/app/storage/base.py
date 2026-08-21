from abc import ABC, abstractmethod


class BaseStorage(ABC):
    """
    Abstract Base Class for file storage drivers.
    Decouples document uploads from storage providers (e.g. local disk vs AWS S3).
    """

    @abstractmethod
    async def upload_file(
        self, file_content: bytes, filename: str, path_prefix: str = ""
    ) -> str:
        """
        Uploads file content to storage.
        Returns a unique storage key/string for file retrieval.
        """
        pass

    @abstractmethod
    async def download_file(self, storage_key: str) -> bytes:
        """
        Retrieves file bytes from storage.
        """
        pass

    @abstractmethod
    async def delete_file(self, storage_key: str) -> None:
        """
        Deletes a file from storage.
        """
        pass
