"""
RAG Chat API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal, Any
import structlog
from datetime import datetime

from backend.api.deps import get_orchestrator, get_tracer

router = APIRouter()
logger = structlog.get_logger()


class RAGQueryRequest(BaseModel):
    """RAG query request"""
    query: str = Field(..., description="User query")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for context")
    enable_reflection: bool = Field(True, description="Enable reflection mechanism")
    enable_verification: bool = Field(True, description="Enable answer verification")
    top_k: int = Field(10, ge=1, le=50, description="Number of chunks to retrieve")
    stream: bool = Field(False, description="Enable streaming response")


class RAGQueryResponse(BaseModel):
    """RAG query response"""
    answer: str
    sources: list[dict]
    trace_id: str
    query_type: str
    metadata: dict


class Citation(BaseModel):
    """Citation model"""
    chunk_id: str
    text: str
    score: float
    source_document: str
    page_number: Optional[int] = None


@router.post("/rag/query", response_model=RAGQueryResponse)
async def query_rag(request: RAGQueryRequest):
    """
    Query the RAG system with a question.

    This endpoint processes the query through the Agentic RAG pipeline:
    1. Query Analysis - Classify query type
    2. Planning - Create retrieval plan
    3. Retrieval - Fetch relevant chunks
    4. Reflection - Evaluate and potentially refine
    5. Generation - Generate answer with citations
    6. Verification - Verify answer against sources
    """
    logger.info("rag_query_received", query=request.query, stream=request.stream)

    try:
        orchestrator = get_orchestrator()
        tracer = get_tracer()

        trace_id = tracer.create_trace(
            query=request.query,
            conversation_id=request.conversation_id,
        )

        result = await orchestrator.query(
            query=request.query,
            trace_id=trace_id,
            enable_reflection=request.enable_reflection,
            enable_verification=request.enable_verification,
            top_k=request.top_k,
        )

        logger.info(
            "rag_query_completed",
            trace_id=trace_id,
            query_type=result.get("query_type"),
            answer_length=len(result.get("answer", "")),
        )

        return RAGQueryResponse(
            answer=result["answer"],
            sources=result.get("sources", []),
            trace_id=trace_id,
            query_type=result.get("query_type", "unknown"),
            metadata={
                "retrieval_rounds": result.get("retrieval_rounds", 0),
                "reflection_rounds": result.get("reflection_rounds", 0),
                "generation_latency_ms": result.get("generation_latency_ms", 0),
                "total_latency_ms": result.get("total_latency_ms", 0),
            },
        )

    except Exception as e:
        logger.error("rag_query_failed", error=str(e), query=request.query)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag/conversation/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    tracer = get_tracer()
    history = tracer.get_conversation_history(conversation_id)
    return {"conversation_id": conversation_id, "messages": history}


@router.get("/rag/health")
async def rag_health():
    """RAG system health check"""
    return {
        "status": "healthy",
        "components": {
            "orchestrator": "ready",
            "generator": "ready",
            "retriever": "ready",
        },
    }
