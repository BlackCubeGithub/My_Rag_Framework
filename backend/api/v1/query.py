"""
Query Management API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Any
import structlog

from backend.api.deps import get_query_rewriter, get_hybrid_retriever

router = APIRouter()
logger = structlog.get_logger()


class QueryRewriteRequest(BaseModel):
    """Query rewrite request"""
    query: str = Field(..., description="Original query")
    rewrite_mode: str = Field("expand", description="Rewrite mode: expand, decompose, or both")


class QueryRewriteResponse(BaseModel):
    """Query rewrite response"""
    original_query: str
    expanded_queries: list[str]
    decomposed_queries: list[list[str]]


class SearchRequest(BaseModel):
    """Direct search request"""
    query: str
    collection_name: str = "default"
    top_k: int = 10
    search_mode: str = "hybrid"  # vector, bm25, hybrid


class SearchResult(BaseModel):
    """Search result"""
    chunk_id: str
    text: str
    score: float
    source: str
    metadata: dict


@router.post("/query/rewrite", response_model=QueryRewriteResponse)
async def rewrite_query(request: QueryRewriteRequest):
    """
    Rewrite and expand the query for better retrieval.

    Modes:
    - expand: Generate alternative phrasings
    - decompose: Break into sub-questions for multi-hop retrieval
    - both: Do both
    """
    logger.info("query_rewrite_requested", mode=request.rewrite_mode)

    try:
        rewriter = get_query_rewriter()

        expanded = []
        decomposed = []

        if request.rewrite_mode in ["expand", "both"]:
            expanded = await rewriter.expand_query(request.query)

        if request.rewrite_mode in ["decompose", "both"]:
            decomposed = await rewriter.decompose_query(request.query)

        return QueryRewriteResponse(
            original_query=request.query,
            expanded_queries=expanded,
            decomposed_queries=decomposed,
        )

    except Exception as e:
        logger.error("query_rewrite_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/search", response_model=list[SearchResult])
async def search(
    request: SearchRequest,
):
    """
    Direct search without full RAG pipeline.

    Useful for testing retrieval quality.
    """
    logger.info("search_requested", query=request.query, mode=request.search_mode)

    try:
        retriever = get_hybrid_retriever()

        results = await retriever.search(
            query=request.query,
            top_k=request.top_k,
        )

        return [
            SearchResult(
                chunk_id=r["chunk_id"],
                text=r["text"][:500],  # Truncate for display
                score=r["score"],
                source=r.get("source", "unknown"),
                metadata=r.get("metadata", {}),
            )
            for r in results
        ]

    except Exception as e:
        logger.error("search_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/query/suggestions")
async def get_query_suggestions(
    partial_query: str,
    limit: int = 5,
):
    """Get query suggestions based on partial input"""
    suggestions = [
        f"{partial_query} 的实现原理",
        f"{partial_query} 的使用方法",
        f"{partial_query} 和其他框架的区别",
        f"如何使用 {partial_query}",
        f"{partial_query} 最佳实践",
    ]
    return {"suggestions": suggestions[:limit]}
