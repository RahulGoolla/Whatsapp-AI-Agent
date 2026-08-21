import time

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.core.redis import redis_manager
from app.db.session import get_db
from app.vector_db.client import chroma_manager

router = APIRouter()


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Deep health-check endpoint. Validates connectivity and responsiveness
    of Database, Redis, and ChromaDB.
    """
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "services": {
            "database": {"status": "unhealthy", "latency_ms": 0.0},
            "redis": {"status": "standalone_disabled", "latency_ms": 0.0},
            "chromadb": {"status": "unhealthy", "latency_ms": 0.0},
        },
    }

    overall_healthy = True

    # 1. Check Database
    start_time = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start_time) * 1000
        health_status["services"]["database"] = {
            "status": "healthy",
            "latency_ms": round(latency, 2),
        }
    except Exception as e:
        logger.error(f"Health Check: Database is unhealthy - {e}")
        health_status["services"]["database"]["error"] = str(e)
        overall_healthy = False

    # 2. Check Redis (Optional in standalone cloud mode)
    start_time = time.perf_counter()
    try:
        redis_ok = await redis_manager.check_health()
        latency = (time.perf_counter() - start_time) * 1000
        if redis_ok:
            health_status["services"]["redis"] = {
                "status": "healthy",
                "latency_ms": round(latency, 2),
            }
        else:
            health_status["services"]["redis"] = {
                "status": "standalone_disabled",
                "latency_ms": 0.0,
            }
    except Exception as e:
        logger.warning(f"Health Check: Redis is in standalone mode - {e}")
        health_status["services"]["redis"] = {
            "status": "standalone_disabled",
            "latency_ms": 0.0,
        }

    # 3. Check ChromaDB
    start_time = time.perf_counter()
    try:
        chroma_ok = chroma_manager.check_health()
        latency = (time.perf_counter() - start_time) * 1000
        if chroma_ok:
            health_status["services"]["chromadb"] = {
                "status": "healthy",
                "latency_ms": round(latency, 2),
            }
        else:
            health_status["services"]["chromadb"]["error"] = "Heartbeat check failed"
            overall_healthy = False
    except Exception as e:
        logger.error(f"Health Check: ChromaDB is unhealthy - {e}")
        health_status["services"]["chromadb"]["error"] = str(e)
        overall_healthy = False

    if not overall_healthy:
        health_status["status"] = "unhealthy"
        logger.warning(f"Health check failed: {health_status}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=health_status,
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content=health_status)
