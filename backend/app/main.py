import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import app.models
from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import RAGeniusError
from app.core.logging import logger, setup_logging
from app.core.redis import redis_manager
from app.db.base import Base
from app.db.session import engine
from app.services.seeder import seed_default_knowledge_base


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup actions
    setup_logging()
    logger.info("Starting up AI Vastra WhatsApp AI Agent Backend Service...")
    logger.info(f"Loaded environment configuration: {settings.ENV}")

    # Initialize database tables if they do not exist
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database schema: {e}")

    # Auto-seed knowledge base workspace with AI_Vastra_WhatsApp_AI_FAQ.pdf
    try:
        await seed_default_knowledge_base()
    except Exception as e:
        logger.warning(f"Knowledge base auto-seed notice: {e}")

    yield
    # Shutdown actions
    logger.info("Shutting down AI Vastra Backend Service...")
    try:
        await redis_manager.close()
    except Exception:
        pass


app = FastAPI(
    title="AI Vastra WhatsApp Sales Agent Platform",
    description="Production-grade WhatsApp AI Sales Agent for AI Vastra / Nice Digitals",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Robust CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.options("/{full_path:path}")
async def catch_all_options(full_path: str, request: Request) -> Response:
    """Catch-all OPTIONS route handler for CORS preflight requests across all endpoints."""
    origin = request.headers.get("origin", "*")
    req_headers = request.headers.get("access-control-request-headers", "*")
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": req_headers,
        },
    )


# Custom Global Exception Handler for Domain Specific Errors
@app.exception_handler(RAGeniusError)
async def ragenius_exception_handler(
    request: Request, exc: RAGeniusError
) -> JSONResponse:
    logger.warning(
        f"Domain Exception on {request.method} {request.url.path} - "
        f"Status: {exc.status_code} - Error: {exc.message}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error_code": exc.__class__.__name__,
            "details": exc.details,
        },
    )


# General catch-all exception handler
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        f"Unhandled system error on {request.method} {request.url.path}: {exc}"
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected internal server error occurred.",
            "error_code": "InternalServerError",
        },
    )


# Mount main API endpoints
app.include_router(api_router, prefix="/api")

# Static files directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
@app.get("/simulator", response_class=HTMLResponse)
async def web_simulator() -> FileResponse:
    """Serves the interactive Obsidian glassmorphism web workspace and WhatsApp phone simulator."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>AI Vastra WhatsApp AI Sales Agent Online</h1>")
