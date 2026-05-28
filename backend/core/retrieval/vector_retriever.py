"""
Vector Retriever
Semantic similarity search using embeddings
"""
import os
import time
import structlog
from typing import Optional
import numpy as np

from backend.core.retrieval.base import BaseRetriever
from backend.core.storage.vector_store import VectorStoreManager
from backend.config import settings

logger = structlog.get_logger()


class VectorRetriever(BaseRetriever):
    """Semantic search using vector embeddings"""

    def __init__(
        self,
        vector_store: VectorStoreManager,
        embedding_model: str = "BAAI/bge-large-zh-v1.5",
    ):
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self._embedding_client = None
        self._model = None

    def _get_embedding_client(self):
        """Lazy load embedding model from local path or HuggingFace mirror"""
        if self._embedding_client is None:
            try:
                from sentence_transformers import SentenceTransformer
                local_path = settings.EMBEDDING_LOCAL_PATH
                if local_path.exists():
                    logger.info("loading_embedding_model_from_local", path=str(local_path))
                    self._model = SentenceTransformer(str(local_path))
                else:
                    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
                    logger.info("downloading_embedding_model", source="huggingface-mirror")
                    self._model = SentenceTransformer(self.embedding_model)
                    os.makedirs(local_path.parent, exist_ok=True)
                    self._model.save(str(local_path))
                    logger.info("embedding_model_cached", path=str(local_path))
                self._embedding_client = True
                logger.info("embedding_model_loaded", model=self.embedding_model)
            except ImportError:
                logger.warning("sentence-transformers not available, using mock embeddings")
                self._embedding_client = "mock"
            except Exception as e:
                logger.warning("embedding_model_load_failed", error=str(e))
                self._embedding_client = "mock"

        return self._embedding_client

    async def _embed_query(self, query: str) -> list[float]:
        """Generate embedding for query"""
        client = self._get_embedding_client()

        if client == "mock":
            return np.random.randn(settings.EMBEDDING_DIM).tolist()

        if self._model:
            embedding = self._model.encode(query, normalize_embeddings=True)
            return embedding.tolist()

        return np.random.randn(settings.EMBEDDING_DIM).tolist()

    async def search(
        self,
        query: str,
        top_k: int = 10,
        collection_name: Optional[str] = None,
        filters: Optional[dict] = None,
        **kwargs,
    ) -> list[dict]:
        """
        Search using semantic similarity.

        Args:
            query: Search query
            top_k: Number of results
            collection_name: Vector collection to search
            filters: Metadata filters

        Returns:
            List of retrieved chunks with similarity scores
        """
        start_time = time.time()

        logger.info("vector_search_started", query=query[:100], top_k=top_k)

        query_embedding = await self._embed_query(query)

        results = self.vector_store.search(
            query_embedding=query_embedding,
            collection_name=collection_name or settings.VECTOR_STORE_COLLECTION_NAME,
            top_k=top_k,
            where_filter=filters,
        )

        latency_ms = (time.time() - start_time) * 1000

        for i, result in enumerate(results):
            result["score"] = result.get("score", 0)
            result["retrieval_method"] = "vector"

        logger.info(
            "vector_search_completed",
            query=query[:50],
            results_count=len(results),
            latency_ms=latency_ms,
        )

        return results

    async def add(
        self,
        chunks: list[dict],
        collection_name: Optional[str] = None,
        embeddings: Optional[list[list[float]]] = None,
        **kwargs,
    ):
        """Add chunks with their embeddings"""
        if not embeddings:
            client = self._get_embedding_client()
            if client != "mock" and self._model:
                texts = [chunk.get("text", "") for chunk in chunks]
                embeddings = self._model.encode(texts, normalize_embeddings=True).tolist()

        self.vector_store.add_chunks(
            chunks=chunks,
            collection_name=collection_name or settings.VECTOR_STORE_COLLECTION_NAME,
            embeddings=embeddings,
        )

        logger.info("chunks_added_to_vector_store", count=len(chunks))

    async def delete(
        self,
        chunk_ids: list[str],
        collection_name: Optional[str] = None,
        **kwargs,
    ):
        """Delete chunks from vector store"""
        self.vector_store.delete_chunks(
            chunk_ids=chunk_ids,
            collection_name=collection_name or settings.VECTOR_STORE_COLLECTION_NAME,
        )

    async def batch_search(
        self,
        queries: list[str],
        top_k: int = 10,
        collection_name: Optional[str] = None,
    ) -> list[list[dict]]:
        """Batch search for multiple queries"""
        import asyncio

        tasks = [
            self.search(query, top_k=top_k, collection_name=collection_name)
            for query in queries
        ]

        return await asyncio.gather(*tasks)
