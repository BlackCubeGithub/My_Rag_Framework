"""
FastAPI Application Entry Point
"""
from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import structlog

from backend.config import settings, ensure_directories
from backend.api.v1 import rag, ingest, query, eval, observability
from backend.api.deps import init_services

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    logger.info("application_starting", version=settings.VERSION)
    ensure_directories()
    await init_services()
    logger.info("services_initialized")
    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Agentic RAG Framework with Full Observability",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(rag.router, prefix=settings.API_V1_PREFIX, tags=["RAG"])
    app.include_router(ingest.router, prefix=settings.API_V1_PREFIX, tags=["Ingestion"])
    app.include_router(query.router, prefix=settings.API_V1_PREFIX, tags=["Query"])
    app.include_router(eval.router, prefix=settings.API_V1_PREFIX, tags=["Evaluation"])
    app.include_router(observability.router, prefix=settings.API_V1_PREFIX, tags=["Observability"])

    @app.get("/")
    async def root():
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "status": "running",
        }

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
