from app.core.config import settings
from app.core.logging import logger

try:
    import redis.asyncio as redis

    class RedisConnectionManager:
        """Manages the connection pool for the async Redis client."""

        def __init__(self) -> None:
            self.redis_url = settings.REDIS_URL
            self._pool = None

        def get_pool(self):
            if self._pool is None:
                logger.info("Initializing Redis connection pool...")
                self._pool = redis.ConnectionPool.from_url(
                    self.redis_url,
                    max_connections=50,
                    decode_responses=True,
                )
            return self._pool

        def get_client(self):
            pool = self.get_pool()
            return redis.Redis(connection_pool=pool)

        async def check_health(self) -> bool:
            try:
                client = self.get_client()
                await client.ping()
                return True
            except Exception as e:
                logger.warning(f"Redis health check notice: {e}")
                return False

        async def close(self) -> None:
            if self._pool is not None:
                logger.info("Closing Redis connection pool...")
                await self._pool.disconnect()
                self._pool = None

except ImportError:
    class RedisConnectionManager:
        """Fallback mock Redis manager when redis library is not installed."""

        def __init__(self) -> None:
            self._pool = None

        def get_pool(self):
            return None

        def get_client(self):
            return None

        async def check_health(self) -> bool:
            return True

        async def close(self) -> None:
            pass


redis_manager = RedisConnectionManager()
