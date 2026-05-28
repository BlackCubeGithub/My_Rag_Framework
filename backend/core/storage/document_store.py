"""
Document Store
Manages document metadata and chunks using SQLite
"""
import sqlite3
import json
import uuid
from pathlib import Path
from typing import Optional
from datetime import datetime
import structlog

logger = structlog.get_logger()

_DB_PATH = "./data/documents/store.db"


def _get_connection() -> sqlite3.Connection:
    """Get a thread-safe SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db():
    """Initialize database schema."""
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id TEXT PRIMARY KEY,
                file_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                text TEXT NOT NULL DEFAULT '',
                metadata TEXT NOT NULL DEFAULT '{}',
                chunk_index INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (document_id) REFERENCES documents(document_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_document_id
                ON chunks(document_id);
        """)
        conn.commit()
    finally:
        conn.close()


class DocumentStore:
    """SQLite-based document and chunk store."""

    _db_initialized = False

    def __init__(self, storage_dir: str = "./data/documents"):
        Path(storage_dir).mkdir(parents=True, exist_ok=True)
        if not DocumentStore._db_initialized:
            _init_db()
            DocumentStore._db_initialized = True

    def store_document(
        self,
        document_id: str,
        file_name: str,
        chunks: list[dict],
        metadata: dict,
    ) -> str:
        """Store document metadata and its chunks."""
        conn = _get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO documents (document_id, file_name, created_at, metadata) VALUES (?, ?, ?, ?)",
                (document_id, file_name, datetime.now().isoformat(), json.dumps(metadata, ensure_ascii=False)),
            )

            conn.execute(
                "DELETE FROM chunks WHERE document_id = ?",
                (document_id,),
            )

            for idx, chunk in enumerate(chunks):
                conn.execute(
                    "INSERT INTO chunks (chunk_id, document_id, text, metadata, chunk_index) VALUES (?, ?, ?, ?, ?)",
                    (
                        chunk.get("chunk_id", str(uuid.uuid4())),
                        document_id,
                        chunk.get("text", ""),
                        json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                        chunk.get("index", idx),
                    ),
                )

            conn.commit()
            logger.info("document_stored", document_id=document_id, chunks=len(chunks))
            return document_id
        finally:
            conn.close()

    def get_document(self, document_id: str) -> Optional[dict]:
        """Get document info (without chunks)."""
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT document_id, file_name, created_at, metadata FROM documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()
            if not row:
                return None

            chunks_count = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]

            return {
                "document_id": row["document_id"],
                "file_name": row["file_name"],
                "created_at": row["created_at"],
                "metadata": json.loads(row["metadata"]),
                "chunks_count": chunks_count,
            }
        finally:
            conn.close()

    def get_chunks(self, document_id: str, skip: int = 0, limit: int = 100) -> tuple[list[dict], int]:
        """Get chunks for a document. Returns (chunks, total_count)."""
        conn = _get_connection()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
                (document_id,),
            ).fetchone()[0]

            rows = conn.execute(
                "SELECT chunk_id, text, metadata, chunk_index FROM chunks WHERE document_id = ? ORDER BY chunk_index LIMIT ? OFFSET ?",
                (document_id, limit, skip),
            ).fetchall()

            chunks = []
            for row in rows:
                chunks.append({
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "metadata": json.loads(row["metadata"]),
                    "index": row["chunk_index"],
                })
            return chunks, total
        finally:
            conn.close()

    def list_documents(self, skip: int = 0, limit: int = 100) -> list[dict]:
        """List all documents."""
        conn = _get_connection()
        try:
            rows = conn.execute(
                """SELECT d.document_id, d.file_name, d.created_at, d.metadata,
                          COUNT(c.chunk_id) AS chunks_count
                   FROM documents d
                   LEFT JOIN chunks c ON d.document_id = c.document_id
                   GROUP BY d.document_id
                   ORDER BY d.created_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, skip),
            ).fetchall()

            return [
                {
                    "document_id": row["document_id"],
                    "file_name": row["file_name"],
                    "created_at": row["created_at"],
                    "metadata": json.loads(row["metadata"]),
                    "chunks_count": row["chunks_count"],
                }
                for row in rows
            ]
        finally:
            conn.close()

    def delete_document(self, document_id: str) -> bool:
        """Delete a document and its chunks."""
        conn = _get_connection()
        try:
            cur = conn.execute(
                "DELETE FROM documents WHERE document_id = ?",
                (document_id,),
            )
            conn.commit()
            deleted = cur.rowcount > 0
            if deleted:
                logger.info("document_deleted", document_id=document_id)
            return deleted
        finally:
            conn.close()

    def update_chunk(
        self,
        document_id: str,
        chunk_id: str,
        updates: dict,
    ) -> bool:
        """Update a chunk's text or metadata."""
        conn = _get_connection()
        try:
            sets = []
            params = []
            if "text" in updates:
                sets.append("text = ?")
                params.append(updates["text"])
            if "metadata" in updates:
                sets.append("metadata = ?")
                params.append(json.dumps(updates["metadata"], ensure_ascii=False))
            if not sets:
                return False
            params.extend([chunk_id, document_id])
            cur = conn.execute(
                f"UPDATE chunks SET {', '.join(sets)} WHERE chunk_id = ? AND document_id = ?",
                params,
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def get_statistics(self) -> dict:
        """Get overall statistics."""
        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT COUNT(*) AS total_documents,
                          (SELECT COUNT(*) FROM chunks) AS total_chunks
                   FROM documents"""
            ).fetchone()
            return {
                "total_documents": row["total_documents"],
                "total_chunks": row["total_chunks"],
            }
        finally:
            conn.close()
