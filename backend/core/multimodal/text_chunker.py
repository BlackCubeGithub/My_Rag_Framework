"""
Text Chunker
Implements multiple chunking strategies for text documents
"""
import re
import uuid
import structlog
from typing import Literal
from dataclasses import dataclass, field

from backend.config import settings

logger = structlog.get_logger()


@dataclass
class Chunk:
    """Represents a text chunk"""
    chunk_id: str
    text: str
    metadata: dict = field(default_factory=dict)


class TextChunker:
    """Text chunking with multiple strategies"""

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 128,
        strategy: Literal["fixed", "recursive", "semantic"] = "recursive",
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.strategy = strategy

    def chunk(
        self,
        document,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ) -> list[dict]:
        """
        Chunk a parsed document into smaller pieces.

        Args:
            document: ParsedDocument object
            chunk_size: Override default chunk size
            chunk_overlap: Override default overlap

        Returns:
            List of chunk dictionaries
        """
        chunk_size = chunk_size or self.chunk_size
        chunk_overlap = chunk_overlap or self.chunk_overlap

        self.logger = logger
        self.logger.info(
            "chunking_document",
            strategy=self.strategy,
            chunk_size=chunk_size,
            document_length=len(document.content),
        )

        if self.strategy == "fixed":
            chunks = self._fixed_chunking(document.content, chunk_size, chunk_overlap)
        elif self.strategy == "recursive":
            chunks = self._recursive_chunking(document.content, chunk_size, chunk_overlap)
        elif self.strategy == "semantic":
            chunks = self._semantic_chunking(document)
        else:
            chunks = self._recursive_chunking(document.content, chunk_size, chunk_overlap)

        for i, chunk in enumerate(chunks):
            chunk["chunk_id"] = chunk.get("chunk_id") or str(uuid.uuid4())
            chunk["index"] = i
            chunk["metadata"]["total_chunks"] = len(chunks)

        self.logger.info("chunking_completed", chunks_count=len(chunks))
        return chunks

    def _fixed_chunking(
        self,
        text: str,
        chunk_size: int,
        overlap: int,
    ) -> list[dict]:
        """Simple fixed-size chunking with overlap"""
        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + chunk_size
            chunk_text = text[start:end]

            chunks.append({
                "text": chunk_text.strip(),
                "metadata": {
                    "start_char": start,
                    "end_char": end,
                    "chunking_strategy": "fixed",
                },
            })

            start += chunk_size - overlap

            if start >= text_length:
                break

        return chunks

    def _recursive_chunking(
        self,
        text: str,
        chunk_size: int,
        overlap: int,
    ) -> list[dict]:
        """
        Recursive character chunking with separator hierarchy.
        Splits on paragraphs first, then sentences, then words.
        """
        chunks = []

        paragraphs = self._split_by_paragraph(text)

        current_chunk = ""
        current_start = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_chunk) + len(para) + 1 <= chunk_size:
                current_chunk += para + "\n"
            else:
                if current_chunk.strip():
                    chunks.append({
                        "text": current_chunk.strip(),
                        "metadata": {
                            "start_char": current_start,
                            "chunking_strategy": "recursive",
                        },
                    })

                if len(para) > chunk_size:
                    sentences = self._split_by_sentence(para)
                    current_chunk = ""
                    current_start = text.find(para)

                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                            current_chunk += sentence + " "
                        else:
                            if current_chunk.strip():
                                chunks.append({
                                    "text": current_chunk.strip(),
                                    "metadata": {
                                        "start_char": current_start,
                                        "chunking_strategy": "recursive",
                                    },
                                })
                            current_chunk = sentence + " "
                            current_start = text.find(sentence)

                    current_chunk = ""
                else:
                    overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
                    current_chunk = overlap_text + para + "\n"
                    current_start = text.find(para)

        if current_chunk.strip():
            chunks.append({
                "text": current_chunk.strip(),
                "metadata": {
                    "start_char": current_start,
                    "chunking_strategy": "recursive",
                },
            })

        return chunks

    def _semantic_chunking(self, document) -> list[dict]:
        """
        Semantic chunking based on document structure.
        Uses headings and sections to create meaningful chunks.
        """
        chunks = []

        if not document.text_blocks:
            return self._recursive_chunking(document.content, self.chunk_size, self.chunk_overlap)

        current_section = ""
        current_heading = "General"
        section_start = 0

        headings = ["h1", "h2", "h3", "h4"]

        for block in document.text_blocks:
            text = block.get("text", "")
            block_type = block.get("type", "text")

            if block_type.lower() in headings:
                if current_section.strip():
                    chunks.append({
                        "text": current_section.strip(),
                        "metadata": {
                            "section": current_heading,
                            "chunking_strategy": "semantic",
                            "start_char": section_start,
                        },
                    })

                current_heading = text
                current_section = text + "\n"
                section_start = document.content.find(text)

            elif len(current_section) + len(text) + 1 <= self.chunk_size * 1.5:
                current_section += text + "\n"

            else:
                if current_section.strip():
                    chunks.append({
                        "text": current_section.strip(),
                        "metadata": {
                            "section": current_heading,
                            "chunking_strategy": "semantic",
                            "start_char": section_start,
                        },
                    })

                current_section = text + "\n"
                section_start = document.content.find(text)

        if current_section.strip():
            chunks.append({
                "text": current_section.strip(),
                "metadata": {
                    "section": current_heading,
                    "chunking_strategy": "semantic",
                    "start_char": section_start,
                },
            })

        return chunks

    def _split_by_paragraph(self, text: str) -> list[str]:
        """Split text into paragraphs"""
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_by_sentence(self, text: str) -> list[str]:
        """Split text into sentences"""
        sentence_endings = r"[。！？.!?]+"
        sentences = re.split(sentence_endings, text)
        return [s.strip() for s in sentences if s.strip()]
