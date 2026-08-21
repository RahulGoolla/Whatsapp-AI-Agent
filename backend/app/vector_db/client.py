import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import settings
from app.core.logging import logger


class ChromaDBClientManager:
    """
    Manages the lifecycle of Chroma Vector Database client.
    Uses embedded PersistentClient for local/cloud standalone operation.
    """

    def __init__(self) -> None:
        self.host = settings.CHROMA_HOST
        self.port = settings.CHROMA_PORT
        self._client = None

    def get_client(self):
        """
        Returns an instant embedded PersistentClient connection to ChromaDB.
        """
        if self._client is None:
            # Use fast persistent embedded client directly
            logger.info("Initializing embedded ChromaDB PersistentClient at ./chroma_data")
            self._client = chromadb.PersistentClient(
                path="./chroma_data",
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    def check_health(self) -> bool:
        try:
            client = self.get_client()
            return client is not None
        except Exception as e:
            logger.warning(f"ChromaDB health check notice: {e}")
            return False


chroma_manager = ChromaDBClientManager()
