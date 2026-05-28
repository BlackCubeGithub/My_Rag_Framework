"""
Vector Store Manager
Manages vector database operations using Chroma/Qdrant
"""
from typing import Optional
import json
import uuid
from pathlib import Path
import structlog

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from backend.config import settings

logger = structlog.get_logger()


class VectorStoreManager:
    """Manages vector storage operations"""

    def __init__(
        self,
        persist_dir: str = "./data/vector_store",
        collection_name: str = "documents",
    ):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        if CHROMA_AVAILABLE:
            self.client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        else:
            logger.warning("ChromaDB not available, using mock mode")
            self.client = None

        self.collection_name = collection_name
        self._collections = {}

    def get_collection(self, collection_name: str):
        """Get or create a collection"""
        if self.client is None:
            return None

        if collection_name not in self._collections:
            try:
                self._collections[collection_name] = self.client.get_collection(
                    name=collection_name
                )
            except Exception:
                self._collections[collection_name] = self.client.create_collection(
                    name=collection_name,
                    metadata={"description": f"Collection for {collection_name}"},
                )

        return self._collections[collection_name]

    def add_chunks(
        self,
        chunks: list[dict],
        collection_name: Optional[str] = None,
        embeddings: Optional[list[list[float]]] = None,
    ):
        """Add chunks to the vector store"""
        collection_name = collection_name or self.collection_name
        collection = self.get_collection(collection_name)

        if collection is None:
            logger.warning("Collection not available, skipping add_chunks")
            return

        ids = [chunk.get("chunk_id", str(uuid.uuid4())) for chunk in chunks]
        documents = [chunk.get("text", "") for chunk in chunks]
        metadatas = [chunk.get("metadata", {}) for chunk in chunks]

        if embeddings is None:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
        else:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )

        logger.info("chunks_added", count=len(chunks), collection=collection_name)

    def search(
        self,
        query_embedding: list[float],
        collection_name: Optional[str] = None,
        top_k: int = 10,
        where_filter: Optional[dict] = None,
    ) -> list[dict]:
        """Search for similar chunks"""
        collection_name = collection_name or self.collection_name
        collection = self.get_collection(collection_name)

        if collection is None:
            logger.warning("Collection not available, returning empty results")
            return []

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
            )

            chunks = []
            if results and results.get("ids"):
                for i in range(len(results["ids"][0])):
                    chunks.append({
                        "chunk_id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "score": float(results.get("distances", [[]])[0][i])
                        if results.get("distances")
                        else 0.0,
                        "metadata": results.get("metadatas", [[{}]])[0][i],
                    })

            return chunks

        except Exception as e:
            logger.error("search_failed", error=str(e))
            return []

    def delete_chunks(
        self,
        chunk_ids: list[str],
        collection_name: Optional[str] = None,
    ):
        """Delete chunks by IDs"""
        collection_name = collection_name or self.collection_name
        collection = self.get_collection(collection_name)

        if collection:
            collection.delete(ids=chunk_ids)
            logger.info("chunks_deleted", count=len(chunk_ids))

    def get_chunk(self, chunk_id: str, collection_name: Optional[str] = None) -> Optional[dict]:
        """Get a single chunk by ID"""
        collection_name = collection_name or self.collection_name
        collection = self.get_collection(collection_name)

        if collection is None:
            return None

        try:
            result = collection.get(ids=[chunk_id])
            if result and result.get("ids"):
                return {
                    "chunk_id": result["ids"][0],
                    "text": result["documents"][0],
                    "metadata": result["metadatas"][0] if result.get("metadatas") else {},
                }
        except Exception:
            pass

        return None

    def count(self, collection_name: Optional[str] = None) -> int:
        """Count chunks in collection"""
        collection_name = collection_name or self.collection_name
        collection = self.get_collection(collection_name)

        if collection is None:
            return 0

        return collection.count()

    def clear(self, collection_name: Optional[str] = None):
        """Clear all chunks in collection"""
        collection_name = collection_name or self.collection_name
        collection = self.get_collection(collection_name)

        if collection:
            collection.delete(where={})
            logger.info("collection_cleared", collection=collection_name)
