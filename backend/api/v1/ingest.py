"""
Document Ingestion API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from pathlib import Path
import structlog
import uuid
import time

from backend.api.deps import (
    get_vector_retriever,
    get_bm25_retriever,
    get_document_store,
    get_document_parser,
    get_text_chunker,
)

router = APIRouter()
logger = structlog.get_logger()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".htm"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def _sanitize_filename(filename: str) -> str:
    """Sanitize upload filename to prevent path traversal."""
    original = Path(filename).name
    safe = original.replace("\\", "_").replace("/", "_").replace("..", "_")
    if not safe or len(safe) > 200:
        safe = "uploaded_file"
    return safe


@router.post("/ingest/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection_name: str = "documents",
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    enable_multimodal: bool = True,
):
    """
    Upload and process a document.

    Supported formats: PDF, DOCX, TXT, MD, HTML
    """
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB",
        )

    suffix = Path(file.filename or "unknown").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Supported: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    logger.info("document_upload_started", file_name=file.filename, size=file.size)

    try:
        start_time = time.time()

        parser = get_document_parser()
        chunker = get_text_chunker()
        vector_retriever = get_vector_retriever()
        bm25_retriever = get_bm25_retriever()
        doc_store = get_document_store()

        document_id = str(uuid.uuid4())
        safe_filename = _sanitize_filename(file.filename or "unknown")
        file_path = Path(f"data/uploads/{document_id}_{safe_filename}")
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = await file.read()
        file_path.write_bytes(content)

        try:
            parsed_doc = await parser.parse(str(file_path), safe_filename)
        finally:
            try:
                file_path.unlink(missing_ok=True)
            except Exception:
                pass

        chunks = chunker.chunk(
            document=parsed_doc,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        if not chunks:
            raise HTTPException(status_code=422, detail="No content could be extracted from the document")

        await vector_retriever.add(chunks, collection_name=collection_name)
        await bm25_retriever.add(chunks)

        doc_store.store_document(
            document_id=document_id,
            file_name=safe_filename,
            chunks=chunks,
            metadata={
                **parsed_doc.metadata,
                "source": safe_filename,
                "collection": collection_name,
            },
        )

        processing_time = (time.time() - start_time) * 1000

        logger.info(
            "document_ingestion_completed",
            document_id=document_id,
            chunks_count=len(chunks),
            processing_time_ms=processing_time,
        )

        return {
            "document_id": document_id,
            "file_name": safe_filename,
            "chunks_count": len(chunks),
            "processing_time_ms": processing_time,
            "status": "success",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("document_ingestion_failed", error=str(e), file_name=file.filename)
        raise HTTPException(status_code=500, detail=str(e))


class BatchIngestRequest(BaseModel):
    urls: list[str] = Field(..., min_length=1, max_length=50)
    collection_name: str = "documents"
    chunk_size: int = 512
    chunk_overlap: int = 128


@router.post("/ingest/batch")
async def batch_ingest(request: BatchIngestRequest):
    """
    Batch ingest documents from URLs.

    Each URL should point to a downloadable document.
    """
    logger.info("batch_ingest_started", url_count=len(request.urls))

    import httpx

    results = []
    for url in request.urls:
        parsed_url = str(Path(url))
        if parsed_url.startswith(("http://", "https://")):
            pass
        else:
            results.append({
                "document_id": None,
                "file_name": url,
                "status": "failed",
                "error": "Only HTTP/HTTPS URLs are supported",
            })
            continue

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()

            safe_filename = _sanitize_filename(url.split("/")[-1] or "downloaded_file")
            document_id = str(uuid.uuid4())
            file_path = Path(f"data/uploads/{document_id}_{safe_filename}")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(response.content)

            parser = get_document_parser()
            chunker = get_text_chunker()
            vector_retriever = get_vector_retriever()
            bm25_retriever = get_bm25_retriever()
            doc_store = get_document_store()

            try:
                parsed_doc = await parser.parse(str(file_path), safe_filename)
            finally:
                try:
                    file_path.unlink(missing_ok=True)
                except Exception:
                    pass

            chunks = chunker.chunk(
                document=parsed_doc,
                chunk_size=request.chunk_size,
                chunk_overlap=request.chunk_overlap,
            )

            await vector_retriever.add(chunks, collection_name=request.collection_name)
            await bm25_retriever.add(chunks)

            doc_store.store_document(
                document_id=document_id,
                file_name=safe_filename,
                chunks=chunks,
                metadata={"source": safe_filename, "url": url, "collection": request.collection_name},
            )

            results.append({
                "document_id": document_id,
                "file_name": safe_filename,
                "chunks_count": len(chunks),
                "status": "success",
            })

        except HTTPException:
            results.append({
                "document_id": None,
                "file_name": url,
                "status": "failed",
                "error": "Unsupported or invalid URL",
            })
        except Exception as e:
            results.append({
                "document_id": None,
                "file_name": url,
                "status": "failed",
                "error": str(e),
            })

    success_count = sum(1 for r in results if r["status"] == "success")
    logger.info("batch_ingest_completed", total=len(results), success=success_count)

    return {"results": results, "total": len(results), "success_count": success_count}


@router.get("/ingest/documents")
async def list_documents(
    skip: int = 0,
    limit: int = 100,
):
    """List all ingested documents"""
    doc_store = get_document_store()
    documents = doc_store.list_documents(skip=skip, limit=limit)
    return {"documents": documents, "total": len(documents)}


@router.delete("/ingest/documents/{document_id}")
async def delete_document(document_id: str, collection_name: str = "documents"):
    """Delete a document and its chunks"""
    try:
        doc_store = get_document_store()
        vector_retriever = get_vector_retriever()
        bm25_retriever = get_bm25_retriever()

        doc_info = doc_store.get_document(document_id)
        if not doc_info:
            raise HTTPException(status_code=404, detail="Document not found")

        chunks, _ = doc_store.get_chunks(document_id)
        chunk_ids = [c["chunk_id"] for c in chunks]
        if chunk_ids:
            await vector_retriever.delete(chunk_ids, collection_name=collection_name)
            await bm25_retriever.delete(chunk_ids)

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

    chunks, total = doc_store.get_chunks(document_id, skip=skip, limit=limit)
    return {
        "document_id": document_id,
        "chunks": chunks,
        "total": total,
    }
