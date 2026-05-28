"""
Reflector Module
Evaluates retrieval results and determines if refinement is needed
"""
import json
import structlog
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from backend.core.agent.prompts import SYSTEM_PROMPTS

logger = structlog.get_logger()


class ReflectionDecision(str, Enum):
    """Decision from reflection"""
    PROCEED = "proceed"
    REFINE = "refine"
    INSUFFICIENT = "insufficient"


@dataclass
class ReflectionResult:
    """Result of reflection on retrieval results"""
    decision: ReflectionDecision
    confidence_score: float
    missing_aspects: list[str]
    supplementary_queries: list[str]
    reasoning: str


class Reflector:
    """
    Reflection mechanism for RAG pipeline.

    Evaluates the sufficiency of retrieval results and determines
    whether additional retrieval is needed.
    """

    def __init__(self, generator):
        self.generator = generator

    async def reflect(
        self,
        query: str,
        retrieved_chunks: list[dict],
        query_type: str = "simple",
    ) -> ReflectionResult:
        """
        Evaluate retrieval results and decide if refinement is needed.

        Args:
            query: Original user query
            retrieved_chunks: Retrieved document chunks
            query_type: Type of query

        Returns:
            ReflectionResult with decision and recommendations
        """
        if not retrieved_chunks:
            return ReflectionResult(
                decision=ReflectionDecision.INSUFFICIENT,
                confidence_score=0.0,
                missing_aspects=["No retrieval results"],
                supplementary_queries=[query],
                reasoning="No chunks retrieved",
            )

        logger.info(
            "reflecting_on_retrieval",
            query=query[:100],
            chunks_count=len(retrieved_chunks),
        )

        context = self._build_context(query, retrieved_chunks)

        prompt = f"""{SYSTEM_PROMPTS['reflector']}

【用户问题】
{query}

【检索到的内容】
{context}

请评估检索结果是否充分回答了用户问题。
"""

        try:
            response = await self.generator.generate(prompt, system_prompt=None)
            result = self._parse_reflection_response(response)

            decision_str = result.get("decision", "proceed")
            try:
                decision = ReflectionDecision(decision_str.lower())
            except ValueError:
                logger.warning("unknown_reflection_decision", value=decision_str)
                decision = ReflectionDecision.PROCEED

            confidence = float(result.get("confidence_score", 0.5))

            logger.info(
                "reflection_completed",
                decision=decision,
                confidence=confidence,
            )

            return ReflectionResult(
                decision=decision,
                confidence_score=confidence,
                missing_aspects=result.get("missing_aspects", []),
                supplementary_queries=result.get("supplementary_queries", []),
                reasoning=result.get("reasoning", ""),
            )

        except Exception as e:
            logger.error("reflection_failed", error=str(e))
            return self._fallback_reflection(retrieved_chunks)

    async def quick_reflect(
        self,
        query: str,
        retrieved_chunks: list[dict],
        threshold: float = 0.7,
    ) -> ReflectionResult:
        """
        Quick reflection without LLM call.

        Uses heuristic-based evaluation for faster decisions.
        """
        if not retrieved_chunks:
            return ReflectionResult(
                decision=ReflectionDecision.INSUFFICIENT,
                confidence_score=0.0,
                missing_aspects=["No results"],
                supplementary_queries=[query],
                reasoning="No chunks retrieved",
            )

        scores = [chunk.get("score", 0) for chunk in retrieved_chunks]
        avg_score = sum(scores) / len(scores) if scores else 0

        query_keywords = set(query.lower())
        relevant_count = 0

        for chunk in retrieved_chunks:
            chunk_text = chunk.get("text", "").lower()
            overlap = len(query_keywords & set(chunk_text.split()))
            if overlap >= 2:
                relevant_count += 1

        relevance_ratio = relevant_count / len(retrieved_chunks) if retrieved_chunks else 0

        confidence = (avg_score * 0.6 + relevance_ratio * 0.4)

        if confidence >= threshold:
            decision = ReflectionDecision.PROCEED
        elif confidence >= threshold * 0.5:
            decision = ReflectionDecision.REFINE
        else:
            decision = ReflectionDecision.INSUFFICIENT

        return ReflectionResult(
            decision=decision,
            confidence_score=confidence,
            missing_aspects=[],
            supplementary_queries=[],
            reasoning=f"Quick eval: confidence={confidence:.2f}",
        )

    def _build_context(self, query: str, chunks: list[dict], max_chunks: int = 5) -> str:
        """Build context string from retrieved chunks"""
        context_parts = []
        top_chunks = chunks[:max_chunks]

        for i, chunk in enumerate(top_chunks, 1):
            text = chunk.get("text", "")[:500]
            source = chunk.get("metadata", {}).get("source", "未知来源")
            context_parts.append(f"[来源{i}] {text}\n(来源: {source})")

        return "\n\n".join(context_parts)

    def _parse_reflection_response(self, response: str) -> dict:
        """Parse reflection result from LLM response"""
        try:
            text = response.strip()

            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            start = text.find("{")
            end = text.rfind("}") + 1

            if start >= 0 and end > start:
                return json.loads(text[start:end])

        except Exception as e:
            logger.warning("reflection_parse_failed", error=str(e))

        return {"decision": "proceed", "confidence_score": 0.5}

    def _fallback_reflection(self, chunks: list[dict]) -> ReflectionResult:
        """Fallback when LLM call fails"""
        if len(chunks) >= 3:
            return ReflectionResult(
                decision=ReflectionDecision.PROCEED,
                confidence_score=0.6,
                missing_aspects=[],
                supplementary_queries=[],
                reasoning="Fallback: sufficient chunks retrieved",
            )
        else:
            return ReflectionResult(
                decision=ReflectionDecision.REFINE,
                confidence_score=0.3,
                missing_aspects=["Insufficient results"],
                supplementary_queries=["Expand search"],
                reasoning="Fallback: limited chunks retrieved",
            )
