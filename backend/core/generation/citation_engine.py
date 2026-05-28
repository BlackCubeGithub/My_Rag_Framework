"""
Citation Engine
Extracts and formats citations from retrieved chunks
"""
import re
import structlog
from typing import Optional

logger = structlog.get_logger()


class CitationEngine:
    """Handles citation extraction and formatting"""

    def __init__(self):
        self.citation_pattern = re.compile(r"\[来源(\d+)\]|来源(\d+)|(\[?\d+\]?)")

    def extract_citations(self, text: str) -> list[int]:
        """Extract citation numbers from text"""
        matches = self.citation_pattern.findall(text)
        citations = []

        for match in matches:
            for group in match:
                if group and group.isdigit():
                    citations.append(int(group))

        return list(set(citations))

    def format_citations(
        self,
        text: str,
        citations: list[dict],
    ) -> str:
        """
        Format citations in text with actual source info.

        Args:
            text: Generated answer text
            citations: List of citation dictionaries with chunk info
        """
        formatted_text = text

        for i, citation in enumerate(citations, 1):
            source_marker = f"[来源{i}]"
            source_info = self._build_source_info(citation)

            if source_marker in formatted_text:
                formatted_text = formatted_text.replace(
                    source_marker,
                    f"[来源{i}: {source_info}]"
                )

        return formatted_text

    def _build_source_info(self, citation: dict) -> str:
        """Build source information string"""
        parts = []

        if citation.get("source"):
            parts.append(citation["source"])

        if citation.get("page"):
            parts.append(f"第{citation['page']}页")

        if citation.get("section"):
            parts.append(citation["section"])

        return " | ".join(parts) if parts else "未知来源"

    def add_inline_citations(
        self,
        text: str,
        retrieved_chunks: list[dict],
    ) -> str:
        """
        Add inline citations to text based on content matching.

        This method tries to match statements in the text to retrieved chunks.
        """
        if not retrieved_chunks:
            return text

        sentences = re.split(r"[。!?\n]", text)
        result_parts = []
        used_sources = set()

        for sentence in sentences:
            if not sentence.strip():
                continue

            best_match = self._find_best_matching_chunk(sentence, retrieved_chunks)

            if best_match and len(sentence) > 20:
                chunk_idx = retrieved_chunks.index(best_match) + 1
                if chunk_idx not in used_sources:
                    sentence_with_cite = f"{sentence.strip()} [来源{chunk_idx}]"
                    used_sources.add(chunk_idx)
                else:
                    sentence_with_cite = sentence.strip()
            else:
                sentence_with_cite = sentence.strip()

            if sentence_with_cite:
                result_parts.append(sentence_with_cite)

        return "。".join(result_parts) + "。" if result_parts else text

    def _find_best_matching_chunk(
        self,
        sentence: str,
        chunks: list[dict],
    ) -> Optional[dict]:
        """Find the best matching chunk for a sentence"""
        sentence_words = set(sentence)
        best_chunk = None
        best_overlap = 0

        for chunk in chunks:
            chunk_text = chunk.get("text", "")
            chunk_words = set(chunk_text)

            overlap = len(sentence_words & chunk_words)

            if overlap > best_overlap:
                best_overlap = overlap
                best_chunk = chunk

        return best_chunk if best_overlap > 5 else None

    def format_source_list(self, sources: list[dict]) -> list[dict]:
        """Format sources for API response"""
        formatted = []

        for i, source in enumerate(sources, 1):
            formatted.append({
                "index": i,
                "chunk_id": source.get("chunk_id", ""),
                "text": source.get("text", "")[:500],
                "source": source.get("metadata", {}).get("source", "未知"),
                "page": source.get("metadata", {}).get("page"),
                "score": source.get("score", 0),
            })

        return formatted
