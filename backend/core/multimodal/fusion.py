"""
Multimodal Fusion
Fuses retrieval results from different modalities
"""
import structlog
from typing import Optional
from dataclasses import dataclass
import numpy as np

logger = structlog.get_logger()


@dataclass
class MultimodalChunk:
    """A chunk with multimodal content"""
    chunk_id: str
    text: str
    image_descriptions: list[str] = None
    table_data: str = ""
    source_modality: str = "text"
    metadata: dict = None


class MultimodalFusion:
    """
    Fuses retrieval results from different modalities.

    Handles:
    - Text chunks
    - Image descriptions
    - Table contents
    - Cross-modal relevance
    """

    def __init__(
        self,
        text_weight: float = 0.5,
        image_weight: float = 0.3,
        table_weight: float = 0.2,
    ):
        """
        Initialize fusion.

        Args:
            text_weight: Weight for text relevance
            image_weight: Weight for image relevance
            table_weight: Weight for table relevance
        """
        self.text_weight = text_weight
        self.image_weight = image_weight
        self.table_weight = table_weight

    async def fuse(
        self,
        text_results: list[dict],
        image_results: list[dict],
        table_results: list[dict],
        query: str,
        top_k: int = 10,
    ) -> list[dict]:
        """
        Fuse results from different modalities.

        Args:
            text_results: Retrieved text chunks
            image_results: Retrieved image descriptions
            table_results: Retrieved table results
            query: Search query
            top_k: Number of final results

        Returns:
            Fused and ranked results
        """
        logger.info(
            "fusing_multimodal_results",
            text=len(text_results),
            images=len(image_results),
            tables=len(table_results),
        )

        fused_scores = {}

        for chunk in text_results:
            chunk_id = chunk.get("chunk_id", "")
            score = chunk.get("score", 0) * self.text_weight

            fused_scores[chunk_id] = {
                "chunk": chunk,
                "score": score,
                "modality": "text",
            }

        for img in image_results:
            chunk_id = img.get("image_id", f"img_{len(fused_scores)}")
            score = img.get("score", 0) * self.image_weight

            if chunk_id in fused_scores:
                fused_scores[chunk_id]["score"] += score
            else:
                fused_scores[chunk_id] = {
                    "chunk": {
                        "chunk_id": chunk_id,
                        "text": img.get("description", img.get("caption", "")),
                        "source_modality": "image",
                        "metadata": img,
                    },
                    "score": score,
                    "modality": "image",
                }

        for table in table_results:
            chunk_id = table.get("table_id", f"table_{len(fused_scores)}")
            score = table.get("score", 0) * self.table_weight

            if chunk_id in fused_scores:
                fused_scores[chunk_id]["score"] += score
            else:
                fused_scores[chunk_id] = {
                    "chunk": {
                        "chunk_id": chunk_id,
                        "text": table.get("markdown", table.get("text", "")),
                        "source_modality": "table",
                        "metadata": table,
                    },
                    "score": score,
                    "modality": "table",
                }

        sorted_results = sorted(
            fused_scores.values(),
            key=lambda x: x["score"],
            reverse=True,
        )

        final_results = []
        for item in sorted_results[:top_k]:
            result = item["chunk"].copy()
            result["fused_score"] = item["score"]
            result["modality"] = item["modality"]
            result["score"] = item["score"]
            final_results.append(result)

        logger.info("fusion_completed", results=len(final_results))
        return final_results

    async def rerank_by_modality(
        self,
        results: list[dict],
        query: str,
        preferred_modality: Optional[str] = None,
    ) -> list[dict]:
        """
        Rerank results based on modality preference.

        Args:
            results: Fused results
            query: Search query
            preferred_modality: Preferred modality (text/image/table/any)

        Returns:
            Reranked results
        """
        if preferred_modality == "any" or not preferred_modality:
            return results

        modality_scores = {
            "text": self.text_weight,
            "image": self.image_weight,
            "table": self.table_weight,
        }

        preferred_weight = modality_scores.get(preferred_modality, 1.0)

        def modality_boost(result: dict) -> float:
            modality = result.get("modality", "text")
            if modality == preferred_modality:
                return preferred_weight * 1.5
            return modality_scores.get(modality, 0.1)

        reranked = sorted(
            results,
            key=lambda x: x.get("score", 0) * modality_boost(x),
            reverse=True,
        )

        return reranked

    def create_multimodal_context(
        self,
        results: list[dict],
        max_length: int = 8000,
    ) -> str:
        """
        Create a unified context string from mixed results.

        Args:
            results: Fused results
            max_length: Maximum context length

        Returns:
            Formatted context string
        """
        context_parts = []
        total_length = 0

        for i, result in enumerate(results):
            modality = result.get("modality", "text")
            text = result.get("text", "")

            if modality == "image":
                prefix = f"[图片{i+1}] "
            elif modality == "table":
                prefix = f"[表格{i+1}]\n"
            else:
                prefix = f"[来源{i+1}] "

            content = prefix + text[:1000]

            if total_length + len(content) <= max_length:
                context_parts.append(content)
                total_length += len(content)
            else:
                break

        return "\n\n".join(context_parts)
