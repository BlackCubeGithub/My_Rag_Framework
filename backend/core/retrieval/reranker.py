"""
Cross-Encoder Reranker
Re-ranks retrieval results using a cross-encoder model
"""
import os
import time
import structlog
from typing import Optional
import numpy as np

from backend.config import settings

logger = structlog.get_logger()


class Reranker:
    """
    Cross-encoder based reranking.

    Cross-encoders encode (query, document) pairs together,
    providing more accurate relevance scores than bi-encoders.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-large",
        device: str = "cpu",
        batch_size: int = 8,
    ):
        """
        Initialize reranker.

        Args:
            model_name: HuggingFace model name for reranking
            device: 'cpu' or 'cuda'
            batch_size: Batch size for inference
        """
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        """Lazy load the reranker model from local path or HuggingFace mirror"""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                local_path = settings.RERANKER_LOCAL_PATH
                if local_path.exists():
                    logger.info("loading_reranker_model_from_local", path=str(local_path))
                    self._model = CrossEncoder(str(local_path), max_length=512, device=self.device)
                else:
                    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                    logger.info("downloading_reranker_model", source="huggingface-mirror")
                    self._model = CrossEncoder(self.model_name, max_length=512, device=self.device)
                    os.makedirs(local_path.parent, exist_ok=True)
                    self._model.save(str(local_path))
                    logger.info("reranker_model_cached", path=str(local_path))

                logger.info("reranker_model_loaded", model=self.model_name)

            except ImportError:
                logger.warning("sentence-transformers not available for reranking")
                self._model = "mock"
            except Exception as e:
                logger.warning("reranker_model_load_failed", error=str(e))
                self._model = "mock"

    async def rerank(
        self,
        query: str,
        chunks: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """
        Rerank retrieved chunks using cross-encoder.

        Args:
            query: Original search query
            chunks: List of retrieved chunks
            top_k: Number of top results to return

        Returns:
            Reranked list of chunks with cross-encoder scores
        """
        if not chunks:
            return []

        self._load_model()

        start_time = time.time()

        logger.info(
            "reranking_started",
            query=query[:100],
            chunks_count=len(chunks),
            top_k=top_k,
        )

        if self._model == "mock":
            return self._mock_rerank(query, chunks, top_k)

        try:
            texts = [(query, chunk.get("text", "")) for chunk in chunks]

            scores = self._model.predict(texts, batch_size=self.batch_size)

            for i, chunk in enumerate(chunks):
                chunk["rerank_score"] = float(scores[i])

            sorted_chunks = sorted(
                chunks,
                key=lambda x: x.get("rerank_score", 0),
                reverse=True,
            )

            reranked = sorted_chunks[:top_k]

            for i, chunk in enumerate(reranked):
                chunk["rank"] = i + 1
                chunk["retrieval_method"] = f"{chunk.get('retrieval_method', 'unknown')}_reranked"

            latency_ms = (time.time() - start_time) * 1000

            logger.info(
                "reranking_completed",
                results_count=len(reranked),
                latency_ms=latency_ms,
            )

            return reranked

        except Exception as e:
            logger.error("reranking_failed", error=str(e))
            return chunks[:top_k]

    def _mock_rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        """Fallback mock reranking when model is unavailable"""
        query_words = set(query)

        for chunk in chunks:
            chunk_words = set(chunk.get("text", ""))
            overlap = len(query_words & chunk_words)
            chunk["rerank_score"] = overlap / max(len(query_words), 1)

        sorted_chunks = sorted(
            chunks,
            key=lambda x: x.get("rerank_score", 0),
            reverse=True,
        )

        return sorted_chunks[:top_k]

    async def batch_rerank(
        self,
        queries: list[str],
        chunks_list: list[list[dict]],
        top_k: int = 10,
    ) -> list[list[dict]]:
        """Rerank multiple query result sets"""
        import asyncio

        tasks = [
            self.rerank(query, chunks, top_k)
            for query, chunks in zip(queries, chunks_list)
        ]

        return await asyncio.gather(*tasks)

    def get_score_range(self) -> tuple[float, float]:
        """Get the expected score range for this reranker"""
        if self._model == "mock":
            return (0.0, 1.0)

        return (0.0, 1.0)
