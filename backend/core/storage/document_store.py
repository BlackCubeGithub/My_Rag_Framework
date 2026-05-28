"""
Document Store
Manages document metadata and chunks in file system
"""
import json
import uuid
from pathlib import Path
from typing import Optional
import structlog
from datetime import datetime

logger = structlog.get_logger()


class DocumentStore:
    """File-based document metadata store"""

    def __init__(self, storage_dir: str = "./data/documents"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index.json"
        self._load_index()

    def _load_index(self):
        """Load or initialize the document index"""
        if self.index_file.exists():
            with open(self.index_file, "r", encoding="utf-8") as f:
                self.index = json.load(f)
        else:
            self.index = {"documents": {}}

    def _save_index(self):
        """Save the document index"""
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)

    def store_document(
        self,
        document_id: str,
        file_name: str,
        chunks: list[dict],
        metadata: dict,
    ) -> str:
        """Store document metadata and chunks"""
        doc_info = {
            "document_id": document_id,
            "file_name": file_name,
            "created_at": datetime.now().isoformat(),
            "chunks_count": len(chunks),
            "chunks": chunks,
            "metadata": metadata,
        }

        self.index["documents"][document_id] = doc_info
        self._save_index()

        logger.info("document_stored", document_id=document_id, chunks=len(chunks))
        return document_id

    def get_document(self, document_id: str) -> Optional[dict]:
        """Get document info by ID"""
        return self.index["documents"].get(document_id)

    def list_documents(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """List all documents with pagination"""
        docs = list(self.index["documents"].values())
        docs.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        for doc in docs:
            doc.pop("chunks", None)

        return docs[skip : skip + limit]

    def delete_document(self, document_id: str) -> bool:
        """Delete a document"""
        if document_id in self.index["documents"]:
            del self.index["documents"][document_id]
            self._save_index()
            logger.info("document_deleted", document_id=document_id)
            return True
        return False

    def update_chunk(
        self,
        document_id: str,
        chunk_id: str,
        updates: dict,
    ) -> bool:
        """Update a chunk's metadata or text"""
        doc = self.get_document(document_id)
        if not doc:
            return False

        for chunk in doc.get("chunks", []):
            if chunk.get("chunk_id") == chunk_id:
                chunk.update(updates)
                self.index["documents"][document_id] = doc
                self._save_index()
                return True

        return False

    def get_statistics(self) -> dict:
        """Get overall statistics"""
        docs = self.index["documents"]
        total_chunks = sum(doc.get("chunks_count", 0) for doc in docs.values())

        return {
            "total_documents": len(docs),
            "total_chunks": total_chunks,
            "documents": list(docs.keys()),
        }
