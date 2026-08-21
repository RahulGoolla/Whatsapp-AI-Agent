from typing import Any


class RAGeniusError(Exception):
    """Base error class for RAGenius AI"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class AuthError(RAGeniusError):
    """Raised when authentication token validation fails"""

    def __init__(
        self,
        message: str = "Authentication failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, status_code=401, details=details)


class PermissionDeniedError(RAGeniusError):
    """Raised when a user attempts to access a resource they do not own"""

    def __init__(
        self, message: str = "Permission denied", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, status_code=403, details=details)


class NotFoundError(RAGeniusError):
    """Raised when a requested resource is not found"""

    def __init__(
        self, message: str = "Resource not found", details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message, status_code=404, details=details)


class StorageError(RAGeniusError):
    """Raised when local or cloud storage operations fail"""

    def __init__(
        self,
        message: str = "Storage operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, status_code=500, details=details)


class AIError(RAGeniusError):
    """Raised when interaction with OpenAI, Gemini, or vector databases fail"""

    def __init__(
        self,
        message: str = "AI Engine operation failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, status_code=502, details=details)


class IngestionError(RAGeniusError):
    """Raised when parsing or document ingestion fails"""

    def __init__(
        self,
        message: str = "Document ingestion failed",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, status_code=422, details=details)
