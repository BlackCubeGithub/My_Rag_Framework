"""
API Dependencies
"""
from __future__ import annotations
from fastapi import Depends, HTTPException, UploadFile, File
from typing import AsyncGenerator, Optional, Any
import structlog

from backend.config import settings
from backend.core.agent.orchestrator import AgenticRAGOrchestrator
from backend.core.retrieval.hybrid_retriever import HybridRetriever
from backend.core.retrieval.reranker import Reranker
from backend.core.retrieval.query_rewriter import QueryRewriter
from backend.core.retrieval.vector_retriever import VectorRetriever
from backend.core.retrieval.bm25_retriever import BM25Retriever
from backend.core.generation.generator import Generator
from backend.core.storage.vector_store import VectorStoreManager
from backend.core.storage.document_store import DocumentStore
from backend.core.multimodal.document_parser import DocumentParser
from backend.core.multimodal.text_chunker import TextChunker
from backend.observability.rag_trace import RAGTracer

logger = structlog.get_logger()

# Global instances (will be initialized on startup)
_vector_store: Optional[VectorStoreManager] = None
_document_store: Optional[DocumentStore] = None
_generator: Optional[Generator] = None
_vector_retriever: Optional[VectorRetriever] = None
_bm25_retriever: Optional[BM25Retriever] = None
_hybrid_retriever: Optional[HybridRetriever] = None
_reranker: Optional[Reranker] = None
_query_rewriter: Optional[QueryRewriter] = None
_orchestrator: Optional[AgenticRAGOrchestrator] = None
_tracer: Optional[RAGTracer] = None
_document_parser: Optional[DocumentParser] = None
_text_chunker: Optional[TextChunker] = None


async def init_services():
    """Initialize all services on startup"""
    global _vector_store, _document_store, _generator, _vector_retriever
    global _bm25_retriever, _hybrid_retriever, _reranker, _query_rewriter
    global _orchestrator, _tracer, _document_parser, _text_chunker

    logger.info("initializing_services")

    _vector_store = VectorStoreManager(
        persist_dir=str(settings.VECTOR_STORE_PERSIST_DIR),
        collection_name=settings.VECTOR_STORE_COLLECTION_NAME,
    )

    _document_store = DocumentStore(storage_dir=str(settings.DOC_STORE_PATH))

    _generator = Generator(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
    )

    _vector_retriever = VectorRetriever(vector_store=_vector_store)
    _bm25_retriever = BM25Retriever()
    _hybrid_retriever = HybridRetriever(
        vector_retriever=_vector_retriever,
        bm25_retriever=_bm25_retriever,
        alpha=settings.HYBRID_ALPHA,
    )
    _reranker = Reranker(model_name=settings.RERANKER_MODEL)
    _query_rewriter = QueryRewriter(generator=_generator)

    _document_parser = DocumentParser()
    _text_chunker = TextChunker(
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
        strategy=settings.CHUNK_STRATEGY,
    )

    _tracer = RAGTracer(enable_tracing=settings.ENABLE_TRACING)

    _orchestrator = AgenticRAGOrchestrator(
        generator=_generator,
        hybrid_retriever=_hybrid_retriever,
        reranker=_reranker,
        query_rewriter=_query_rewriter,
        tracer=_tracer,
        max_reflection_rounds=settings.MAX_REFLECTION_ROUNDS,
        reflection_threshold=settings.REFLECTION_THRESHOLD,
        verification_threshold=settings.VERIFICATION_THRESHOLD,
    )

    logger.info("services_initialized")


def get_vector_store() -> VectorStoreManager:
    if _vector_store is None:
        raise HTTPException(status_code=503, detail="Vector store not initialized")
    return _vector_store


def get_document_store() -> DocumentStore:
    if _document_store is None:
        raise HTTPException(status_code=503, detail="Document store not initialized")
    return _document_store


def get_generator() -> Generator:
    if _generator is None:
        raise HTTPException(status_code=503, detail="Generator not initialized")
    return _generator


def get_orchestrator() -> AgenticRAGOrchestrator:
    if _orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    return _orchestrator


def get_tracer() -> RAGTracer:
    if _tracer is None:
        raise HTTPException(status_code=503, detail="Tracer not initialized")
    return _tracer


def get_document_parser() -> DocumentParser:
    if _document_parser is None:
        raise HTTPException(status_code=503, detail="Document parser not initialized")
    return _document_parser


def get_text_chunker() -> TextChunker:
    if _text_chunker is None:
        raise HTTPException(status_code=503, detail="Text chunker not initialized")
    return _text_chunker


def get_hybrid_retriever() -> HybridRetriever:
    if _hybrid_retriever is None:
        raise HTTPException(status_code=503, detail="Hybrid retriever not initialized")
    return _hybrid_retriever


def get_reranker() -> Reranker:
    if _reranker is None:
        raise HTTPException(status_code=503, detail="Reranker not initialized")
    return _reranker


def get_query_rewriter() -> QueryRewriter:
    if _query_rewriter is None:
        raise HTTPException(status_code=503, detail="Query rewriter not initialized")
    return _query_rewriter


def get_vector_retriever() -> VectorRetriever:
    if _vector_retriever is None:
        raise HTTPException(status_code=503, detail="Vector retriever not initialized")
    return _vector_retriever


def get_bm25_retriever() -> BM25Retriever:
    if _bm25_retriever is None:
        raise HTTPException(status_code=503, detail="BM25 retriever not initialized")
    return _bm25_retriever
