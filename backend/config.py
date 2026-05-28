"""
Application Configuration
"""
from __future__ import annotations
from pydantic_settings import BaseSettings
from typing import Literal
from pathlib import Path


class Settings(BaseSettings):
    """Global application settings"""

    # Project
    PROJECT_NAME: str = "My RAG Framework"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # API
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["*"]

    # LLM Configuration
    LLM_PROVIDER: Literal["openai", "deepseek", "claude"] = "openai"
    LLM_MODEL: str = "gpt-4-turbo"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096
    LLM_TIMEOUT: float = 120.0  # seconds — increase for slow models

    # Embedding Configuration
    EMBEDDING_MODEL: str = "BAAI/bge-large-zh-v1.5"
    EMBEDDING_LOCAL_PATH: Path = Path("./models/bge-large-zh-v1.5")
    EMBEDDING_DEVICE: Literal["cpu", "cuda"] = "cpu"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DIM: int = 1024

    # Reranker Configuration
    RERANKER_MODEL: str = "BAAI/bge-reranker-large"
    RERANKER_LOCAL_PATH: Path = Path("./models/bge-reranker-large")
    RERANKER_TOP_K: int = 20

    # Vector Store
    VECTOR_STORE_TYPE: Literal["chroma", "qdrant"] = "chroma"
    VECTOR_STORE_PERSIST_DIR: Path = Path("./data/vector_store")
    VECTOR_STORE_COLLECTION_NAME: str = "documents"

    # Document Processing
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 128
    CHUNK_STRATEGY: Literal["fixed", "recursive", "semantic"] = "recursive"

    # Retrieval
    RETRIEVAL_TOP_K: int = 10
    HYBRID_ALPHA: float = 0.5  # Weight for vector search (1-alpha for BM25)

    # Agentic RAG
    MAX_REFLECTION_ROUNDS: int = 3
    REFLECTION_THRESHOLD: float = 0.7
    VERIFICATION_THRESHOLD: float = 0.8

    # Observability
    OTEL_SERVICE_NAME: str = "my-rag-framework"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    ENABLE_TRACING: bool = True
    ENABLE_METRICS: bool = True

    # Storage
    UPLOAD_DIR: Path = Path("./data/uploads")
    DOC_STORE_PATH: Path = Path("./data/documents")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


def ensure_directories():
    """Ensure all required directories exist"""
    dirs = [
        settings.VECTOR_STORE_PERSIST_DIR,
        settings.UPLOAD_DIR,
        settings.DOC_STORE_PATH,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
