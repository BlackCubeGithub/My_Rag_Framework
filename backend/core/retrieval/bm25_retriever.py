"""
BM25 Retriever
Sparse retrieval using BM25 algorithm
"""
import time
import structlog
from typing import Optional
from rank_bm25 import BM25Okapi

from backend.core.retrieval.base import BaseRetriever

logger = structlog.get_logger()


class BM25Retriever(BaseRetriever):
    """BM25-based sparse retrieval"""

    def __init__(
        self,
        tokenizer: Optional[callable] = None,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or self._default_tokenizer

        self._chunks: list[dict] = []
        self._bm25: Optional[BM25Okapi] = None
        self._tokenized_corpus: list[list[str]] = []

    def _default_tokenizer(self, text: str) -> list[str]:
        """Simple Chinese/English tokenizer"""
        import re
        tokens = re.findall(r"[\w]+", text.lower())
        return tokens

    def _build_index(self):
        """Rebuild BM25 index"""
        if not self._chunks:
            self._bm25 = None
            self._tokenized_corpus = []
            return

        self._tokenized_corpus = [
            self.tokenizer(chunk.get("text", ""))
            for chunk in self._chunks
        ]

        self._bm25 = BM25Okapi(self._tokenized_corpus)
        logger.info("bm25_index_built", corpus_size=len(self._chunks))

    async def add(self, chunks: list[dict], **kwargs):
        """Add chunks to BM25 index"""
        self._chunks.extend(chunks)
        self._build_index()
        logger.info("bm25_chunks_added", total_chunks=len(self._chunks))

    async def delete(self, chunk_ids: list[str], **kwargs):
        """Delete chunks from BM25 index"""
        id_set = set(chunk_ids)
        self._chunks = [c for c in self._chunks if c.get("chunk_id") not in id_set]
        self._build_index()

    async def search(
        self,
        query: str,
        top_k: int = 10,
        **kwargs,
    ) -> list[dict]:
        """
        Search using BM25 algorithm.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            List of retrieved chunks with BM25 scores
        """
        if not self._bm25 or not self._chunks:
            logger.warning("bm25_index_empty")
            return []

        start_time = time.time()

        logger.info("bm25_search_started", query=query[:100], top_k=top_k)

        tokenized_query = self.tokenizer(query)
        scores = self._bm25.get_scores(tokenized_query)

        doc_scores = list(enumerate(scores))
        doc_scores.sort(key=lambda x: x[1], reverse=True)

        results = []
        for idx, score in doc_scores[:top_k]:
            chunk = self._chunks[idx].copy()
            chunk["score"] = float(score)
            chunk["retrieval_method"] = "bm25"
            results.append(chunk)

        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            "bm25_search_completed",
            query=query[:50],
            results_count=len(results),
            latency_ms=latency_ms,
        )

        return results

    def clear(self):
        """Clear all indexed chunks"""
        self._chunks = []
        self._bm25 = None
        self._tokenized_corpus = []
        logger.info("bm25_index_cleared")

    @property
    def corpus_size(self) -> int:
        """Get number of indexed documents"""
        return len(self._chunks)
