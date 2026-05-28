"""
Hybrid Retriever
Combines vector and BM25 retrieval with RRFS fusion
"""
import time
import structlog
from typing import Optional
from dataclasses import dataclass
import numpy as np

from backend.core.retrieval.base import BaseRetriever
from backend.core.retrieval.vector_retriever import VectorRetriever
from backend.core.retrieval.bm25_retriever import BM25Retriever

logger = structlog.get_logger()


@dataclass
class FusionResult:
    """Result from hybrid retrieval fusion"""
    chunks: list[dict]
    fused_scores: list[float]
    vector_scores: list[float]
    bm25_scores: list[float]


class HybridRetriever(BaseRetriever):
    """
    Hybrid retrieval combining dense (vector) and sparse (BM25) methods.

    Uses Reciprocal Rank Fusion (RRF) for combining results.
    """

    def __init__(
        self,
        vector_retriever: VectorRetriever,
        bm25_retriever: BM25Retriever,
        alpha: float = 0.5,
        rrf_k: int = 60,
    ):
        """
        Initialize hybrid retriever.

        Args:
            vector_retriever: Vector-based retriever
            bm25_retriever: BM25-based retriever
            alpha: Weight for vector scores (1-alpha for BM25), 0-1
            rrf_k: RRF parameter (typically 60)
        """
        self.vector_retriever = vector_retriever
        self.bm25_retriever = bm25_retriever
        self.alpha = alpha
        self.rrf_k = rrf_k

    async def search(
        self,
        query: str,
        top_k: int = 10,
        collection_name: Optional[str] = None,
        fusion_method: str = "rrf",
        **kwargs,
    ) -> list[dict]:
        """
        Hybrid search combining vector and BM25 retrieval.

        Args:
            query: Search query
            top_k: Number of results to return
            collection_name: Collection to search
            fusion_method: 'rrf' (Reciprocal Rank Fusion) or 'score_avg'

        Returns:
            List of retrieved chunks with fused scores
        """
        start_time = time.time()

        logger.info(
            "hybrid_search_started",
            query=query[:100],
            top_k=top_k,
            fusion_method=fusion_method,
        )

        vector_task = self.vector_retriever.search(
            query=query,
            top_k=top_k * 2,
            collection_name=collection_name,
        )

        bm25_task = self.bm25_retriever.search(
            query=query,
            top_k=top_k * 2,
        )

        vector_results, bm25_results = await self._gather_results(vector_task, bm25_task)

        if fusion_method == "rrf":
            fused = self._reciprocal_rank_fusion(vector_results, bm25_results, top_k)
        else:
            fused = self._score_average_fusion(vector_results, bm25_results, top_k)

        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            "hybrid_search_completed",
            query=query[:50],
            results_count=len(fused.chunks),
            latency_ms=latency_ms,
        )

        return fused.chunks

    async def _gather_results(self, vector_task, bm25_task):
        """Gather results from both retrievers concurrently"""
        import asyncio

        try:
            results = await asyncio.gather(vector_task, bm25_task, return_exceptions=True)

            if isinstance(results[0], Exception):
                logger.warning("vector_search_failed", error=str(results[0]))
                vector_results = []
            else:
                vector_results = results[0]

            if isinstance(results[1], Exception):
                logger.warning("bm25_search_failed", error=str(results[1]))
                bm25_results = []
            else:
                bm25_results = results[1]

        except Exception as e:
            logger.error("concurrent_search_failed", error=str(e))
            vector_results = []
            bm25_results = []

        return vector_results, bm25_results

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[dict],
        bm25_results: list[dict],
        top_k: int,
    ) -> FusionResult:
        """
        Reciprocal Rank Fusion (RRF) for combining ranked lists.

        RRF score = sum(1 / (k + rank)) for each retrieval method.

        This method is robust to score normalization issues.
        """
        chunk_scores = {}

        for rank, chunk in enumerate(vector_results):
            chunk_id = chunk.get("chunk_id", f"vec_{rank}")
            rrf_score = 1.0 / (self.rrf_k + rank + 1)

            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    "chunk": chunk,
                    "rrf_score": rrf_score,
                    "vector_score": chunk.get("score", 0),
                    "bm25_score": 0.0,
                    "seen": {chunk_id},
                }
            else:
                chunk_scores[chunk_id]["rrf_score"] += rrf_score
                chunk_scores[chunk_id]["vector_score"] = max(
                    chunk_scores[chunk_id]["vector_score"],
                    chunk.get("score", 0),
                )

        for rank, chunk in enumerate(bm25_results):
            chunk_id = chunk.get("chunk_id", f"bm25_{rank}")
            rrf_score = 1.0 / (self.rrf_k + rank + 1)

            if chunk_id not in chunk_scores:
                chunk_scores[chunk_id] = {
                    "chunk": chunk,
                    "rrf_score": rrf_score,
                    "vector_score": 0.0,
                    "bm25_score": chunk.get("score", 0),
                    "seen": {chunk_id},
                }
            else:
                chunk_scores[chunk_id]["rrf_score"] += rrf_score
                chunk_scores[chunk_id]["bm25_score"] = max(
                    chunk_scores[chunk_id]["bm25_score"],
                    chunk.get("score", 0),
                )

        sorted_chunks = sorted(
            chunk_scores.values(),
            key=lambda x: x["rrf_score"],
            reverse=True,
        )[:top_k]

        result_chunks = []
        fused_scores = []
        vec_scores = []
        bm25_scores = []

        for item in sorted_chunks:
            chunk = item["chunk"].copy()
            chunk["fused_score"] = item["rrf_score"]
            chunk["vector_score"] = item["vector_score"]
            chunk["bm25_score"] = item["bm25_score"]
            chunk["score"] = item["rrf_score"]
            chunk["retrieval_method"] = "hybrid_rrf"

            result_chunks.append(chunk)
            fused_scores.append(item["rrf_score"])
            vec_scores.append(item["vector_score"])
            bm25_scores.append(item["bm25_score"])

        return FusionResult(
            chunks=result_chunks,
            fused_scores=fused_scores,
            vector_scores=vec_scores,
            bm25_scores=bm25_scores,
        )

    def _score_average_fusion(
        self,
        vector_results: list[dict],
        bm25_results: list[dict],
        top_k: int,
    ) -> FusionResult:
        """
        Weighted average of normalized scores.

        Normalizes both score distributions to [0, 1] before averaging.
        """
        vec_scores = [c.get("score", 0) for c in vector_results]
        bm25_scores_list = [c.get("score", 0) for c in bm25_results]

        vec_max = max(vec_scores) if vec_scores else 1
        bm25_max = max(bm25_scores_list) if bm25_scores_list else 1

        vec_norm = {c.get("chunk_id"): c.get("score", 0) / vec_max for c in vector_results}
        bm25_norm = {c.get("chunk_id"): c.get("score", 0) / bm25_max for c in bm25_results}

        all_ids = set(vec_norm.keys()) | set(bm25_norm.keys())

        chunk_scores = {}
        for chunk_id in all_ids:
            vec_s = vec_norm.get(chunk_id, 0)
            bm25_s = bm25_norm.get(chunk_id, 0)

            fused = self.alpha * vec_s + (1 - self.alpha) * bm25_s

            if chunk_id in vec_norm:
                chunk = next(c for c in vector_results if c.get("chunk_id") == chunk_id)
            else:
                chunk = next(c for c in bm25_results if c.get("chunk_id") == chunk_id)

            chunk_scores[chunk_id] = {
                "chunk": chunk,
                "fused_score": fused,
                "vector_score": vec_s * vec_max,
                "bm25_score": bm25_s * bm25_max,
            }

        sorted_chunks = sorted(
            chunk_scores.values(),
            key=lambda x: x["fused_score"],
            reverse=True,
        )[:top_k]

        return FusionResult(
            chunks=[
                {**item["chunk"], "score": item["fused_score"], "retrieval_method": "hybrid_avg"}
                for item in sorted_chunks
            ],
            fused_scores=[item["fused_score"] for item in sorted_chunks],
            vector_scores=[item["vector_score"] for item in sorted_chunks],
            bm25_scores=[item["bm25_score"] for item in sorted_chunks],
        )

    async def add(
        self,
        chunks: list[dict],
        collection_name: Optional[str] = None,
        **kwargs,
    ):
        """Add chunks to both underlying retrievers"""
        await self.vector_retriever.add(
            chunks=chunks,
            collection_name=collection_name,
        )
        await self.bm25_retriever.add(chunks=chunks)

    async def delete(
        self,
        chunk_ids: list[str],
        collection_name: Optional[str] = None,
        **kwargs,
    ):
        """Delete chunks from both retrievers"""
        await self.vector_retriever.delete(chunk_ids, collection_name=collection_name)
        await self.bm25_retriever.delete(chunk_ids)
