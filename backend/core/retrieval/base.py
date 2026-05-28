"""
Retrieval Base Classes
"""
from abc import ABC, abstractmethod
from typing import Optional
import structlog

logger = structlog.get_logger()


class BaseRetriever(ABC):
    """Abstract base class for all retrievers"""

    @abstractmethod
    async def search(
        self,
        query: str,
        top_k: int = 10,
        **kwargs,
    ) -> list[dict]:
        """
        Search for relevant chunks.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of retrieved chunks with scores
        """
        pass

    @abstractmethod
    async def add(self, chunks: list[dict], **kwargs):
        """Add chunks to the retriever"""
        pass

    @abstractmethod
    async def delete(self, chunk_ids: list[str], **kwargs):
        """Delete chunks from the retriever"""
        pass


class RetrievalResult:
    """Container for retrieval results"""

    def __init__(
        self,
        chunks: list[dict],
        scores: list[float],
        query: str,
        retrieval_method: str = "unknown",
    ):
        self.chunks = chunks
        self.scores = scores
        self.query = query
        self.retrieval_method = retrieval_method

    def __len__(self):
        return len(self.chunks)

    def get_top_k(self, k: int):
        """Get top k results"""
        if k >= len(self.chunks):
            return self

        indices = sorted(range(len(self.scores)), key=lambda i: self.scores[i], reverse=True)[:k]
        return RetrievalResult(
            chunks=[self.chunks[i] for i in indices],
            scores=[self.scores[i] for i in indices],
            query=self.query,
            retrieval_method=self.retrieval_method,
        )
