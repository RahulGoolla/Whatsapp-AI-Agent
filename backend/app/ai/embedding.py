from abc import ABC, abstractmethod

import anyio
import google.generativeai as genai
import openai

from app.core.config import settings
from app.core.exceptions import AIError
from app.core.logging import logger


class BaseEmbeddingProvider(ABC):
    """
    Abstract interface for generating vector embeddings from text content.
    Allows swappable AI providers (OpenAI, Gemini).
    """

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """Generates embedding for a single text string."""
        pass

    @abstractmethod
    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generates embeddings for a batch of text strings."""
        pass


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI implementation using the official async client."""

    def __init__(self) -> None:
        self.model = "text-embedding-3-small"
        self.client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0]

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not settings.OPENAI_API_KEY:
            raise AIError(message="OPENAI_API_KEY is not configured.")

        try:
            response = await self.client.embeddings.create(
                input=texts,
                model=self.model,
            )
            return [d.embedding for d in response.data]
        except Exception as e:
            logger.error(f"OpenAI embedding generation failed: {e}")
            raise AIError(message="Failed to generate embeddings from OpenAI") from e


class GeminiEmbeddingProvider(BaseEmbeddingProvider):
    """Gemini implementation wrapping the generative AI SDK in anyio threads."""

    def __init__(self) -> None:
        self.model = "models/embedding-001"
        genai.configure(api_key=settings.GEMINI_API_KEY)

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0]

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not settings.GEMINI_API_KEY:
            raise AIError(message="GEMINI_API_KEY is not configured.")

        try:

            def _embed():
                response = genai.embed_content(
                    model=self.model,
                    content=texts,
                    task_type="retrieval_document",
                )
                return response["embedding"]

            # Wrap blocking sync SDK call in threadpool
            embeddings = await anyio.to_thread.run_sync(_embed)
            return embeddings
        except Exception as e:
            logger.error(f"Gemini embedding generation failed: {e}")
            raise AIError(message="Failed to generate embeddings from Gemini") from e


def get_embedding_provider() -> BaseEmbeddingProvider:
    """
    Factory function returning the configured embedding provider.
    """
    provider = settings.DEFAULT_LLM_PROVIDER.lower()
    if provider == "openai":
        return OpenAIEmbeddingProvider()
    elif provider == "gemini":
        return GeminiEmbeddingProvider()
    else:
        logger.warning(
            f"Unsupported LLM provider: {settings.DEFAULT_LLM_PROVIDER}. Falling back to OpenAI."
        )
        return OpenAIEmbeddingProvider()


# Shared system-wide embedding generator client
embedding_provider = get_embedding_provider()
