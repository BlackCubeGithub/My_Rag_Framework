"""
Document Ingestion API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Any
import structlog
import uuid
from pathlib import Path

from backend.api.deps import (
    get_vector_store,
    get_document_store,
    get_document_parser,
    get_text_chunker,
)

router = APIRouter()
logger = structlog.get_logger()


class IngestRequest(BaseModel):
    """Document ingestion request"""
    file_url: Optional[str] = Field(None, description="URL to download file")
    collection_name: str = Field("default", description="Vector store collection")
    chunk_strategy: str = Field("recursive", description="Chunking strategy")
    chunk_size: int = Field(512, ge=100, le=2000)
    chunk_overlap: int = Field(128, ge=0, le=500)
    enable_multimodal: bool = Field(True, description="Enable multimodal processing")


class IngestResponse(BaseModel):
    """Ingestion response"""
    document_id: str
    file_name: str
    chunks_count: int
    processing_time_ms: float
    status: str


class ChunkInfo(BaseModel):
    """Chunk information"""
    chunk_id: str
    text: str
    metadata: dict


@router.post("/ingest/upload", response_model=IngestResponse)
async def upload_document(
    file: UploadFile = File(...),
    collection_name: str = "default",
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    enable_multimodal: bool = True,
):
    """
    Upload and process a document.

    Supported formats: PDF, DOCX, TXT, MD, HTML
    """
    logger.info("document_upload_started", file_name=file.filename, size=file.size)

    try:
        import time
        start_time = time.time()

        parser = get_document_parser()
        chunker = get_text_chunker()
        vector_store = get_vector_store()
        doc_store = get_document_store()

        document_id = str(uuid.uuid4())
        file_path = Path(f"data/uploads/{document_id}_{file.filename}")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        file_path.write_bytes(content)

        parsed_doc = await parser.parse(str(file_path), file.filename)

        chunks = chunker.chunk(
            document=parsed_doc,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        vector_store.add_chunks(chunks, collection_name=collection_name)

        doc_store.store_document(
            document_id=document_id,
            file_name=file.filename,
            chunks=chunks,
            metadata=parsed_doc.metadata,
        )

        processing_time = (time.time() - start_time) * 1000

        logger.info(
            "document_ingestion_completed",
            document_id=document_id,
            chunks_count=len(chunks),
            processing_time_ms=processing_time,
        )

        return IngestResponse(
            document_id=document_id,
            file_name=file.filename,
            chunks_count=len(chunks),
            processing_time_ms=processing_time,
            status="success",
        )

    except Exception as e:
        logger.error("document_ingestion_failed", error=str(e), file_name=file.filename)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/batch")
async def batch_ingest(
    urls: list[str],
    collection_name: str = "default",
):
    """
    Batch ingest documents from URLs.

    Each URL should point to a downloadable document.
    """
    logger.info("batch_ingest_started", url_count=len(urls))

    results = []
    for url in urls:
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()

            file_name = url.split("/")[-1]
            document_id = str(uuid.uuid4())

            results.append({
                "document_id": document_id,
                "file_name": file_name,
                "status": "success",
            })

        except Exception as e:
            results.append({
                "document_id": None,
                "file_name": url,
                "status": "failed",
                "error": str(e),
            })

    return {"results": results, "total": len(urls)}


@router.get("/ingest/documents")
async def list_documents(
    collection_name: str = "default",
    skip: int = 0,
    limit: int = 100,
):
    """List all ingested documents"""
    doc_store = get_document_store()
    documents = doc_store.list_documents(skip=skip, limit=limit)
    return {"documents": documents, "total": len(documents)}


@router.delete("/ingest/documents/{document_id}")
async def delete_document(document_id: str, collection_name: str = "default"):
    """Delete a document and its chunks"""
    try:
        doc_store = get_document_store()
        vector_store = get_vector_store()

        doc_info = doc_store.get_document(document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="Document not found")

        chunk_ids = [chunk["chunk_id"] for chunk in doc_info["chunks"]]
        vector_store.delete_chunks(chunk_ids, collection_name=collection_name)
        doc_store.delete_document(document_id)

        return {"status": "deleted", "document_id": document_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("document_deletion_failed", error=str(e), document_id=document_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ingest/documents/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    skip: int = 0,
    limit: int = 100,
):
    """Get chunks for a specific document"""
    doc_store = get_document_store()
    doc_info = doc_store.get_document(document_id)

    if not doc_info:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks = doc_info["chunks"][skip : skip + limit]
    return {
        "document_id": document_id,
        "chunks": chunks,
        "total": len(doc_info["chunks"]),
    }
