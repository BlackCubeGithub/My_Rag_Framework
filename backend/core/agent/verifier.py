"""
Verifier Module
Verifies generated answers against retrieved content
"""
import json
import structlog
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from backend.core.agent.prompts import SYSTEM_PROMPTS

logger = structlog.get_logger()


class VerificationDecision(str, Enum):
    """Verification result"""
    ACCEPT = "accept"
    REGENERATE = "regenerate"
    REVISE = "revise"


@dataclass
class VerificationResult:
    """Result of answer verification"""
    decision: VerificationDecision
    faithfulness_score: float
    has_hallucination: bool
    citation_accuracy: float
    issues: list[str]
    revised_answer: Optional[str]


class Verifier:
    """
    Answer verification module.

    Verifies that generated answers are:
    1. Faithful to retrieved content
    2. Free from hallucination
    3. Properly cited
    """

    def __init__(self, generator):
        self.generator = generator

    async def verify(
        self,
        query: str,
        answer: str,
        retrieved_chunks: list[dict],
        threshold: float = 0.8,
    ) -> VerificationResult:
        """
        Verify a generated answer against retrieved content.

        Args:
            query: Original user query
            answer: Generated answer
            retrieved_chunks: Retrieved documents
            threshold: Minimum faithfulness score to accept

        Returns:
            VerificationResult with decision and feedback
        """
        if not answer or not retrieved_chunks:
            return VerificationResult(
                decision=VerificationDecision.REGENERATE,
                faithfulness_score=0.0,
                has_hallucination=True,
                citation_accuracy=0.0,
                issues=["Missing answer or context"],
                revised_answer=None,
            )

        logger.info(
            "verifying_answer",
            answer_length=len(answer),
            chunks_count=len(retrieved_chunks),
        )

        context = self._build_context(retrieved_chunks)

        prompt = f"""{SYSTEM_PROMPTS['verifier']}

【用户问题】
{query}

【生成的答案】
{answer}

【参考内容】
{context}

请验证答案的准确性、完整性和引用正确性。
"""

        try:
            response = await self.generator.generate(prompt, system_prompt=None)
            result = self._parse_verification_response(response)

            decision_str = result.get("decision", "accept")
            try:
                decision = VerificationDecision(decision_str.lower())
            except ValueError:
                logger.warning("unknown_verification_decision", value=decision_str)
                decision = VerificationDecision.ACCEPT

            faithfulness = float(result.get("faithfulness_score", 0.5))
            has_hallucination = result.get("has_hallucination", False)

            logger.info(
                "verification_completed",
                decision=decision,
                faithfulness=faithfulness,
                hallucination=has_hallucination,
            )

            return VerificationResult(
                decision=decision,
                faithfulness_score=faithfulness,
                has_hallucination=has_hallucination,
                citation_accuracy=float(result.get("citation_accuracy", 0.5)),
                issues=result.get("issues", []),
                revised_answer=result.get("revised_answer"),
            )

        except Exception as e:
            logger.error("verification_failed", error=str(e))
            return self._fallback_verification(answer, retrieved_chunks)

    async def quick_verify(
        self,
        answer: str,
        retrieved_chunks: list[dict],
    ) -> VerificationResult:
        """
        Quick verification without LLM call.

        Uses heuristic-based checks for faster verification.
        """
        issues = []
        faithfulness = 1.0

        if not answer:
            issues.append("Empty answer")
            faithfulness = 0.0

        if not retrieved_chunks:
            issues.append("No retrieved context")
            faithfulness = 0.0

        citation_markers = ["来源", "[", "据", "表明"]
        has_citation = any(marker in answer for marker in citation_markers)

        if not has_citation and len(answer) > 50:
            issues.append("No citations found")

        if len(answer) > 0 and len(answer) < 10:
            issues.append("Answer too short")

        return VerificationResult(
            decision=VerificationDecision.ACCEPT if len(issues) == 0 else VerificationDecision.REGENERATE,
            faithfulness_score=faithfulness,
            has_hallucination=len(issues) > 0,
            citation_accuracy=1.0 if has_citation else 0.0,
            issues=issues,
            revised_answer=None,
        )

    def _build_context(self, chunks: list[dict], max_chunks: int = 5) -> str:
        """Build context string from chunks"""
        context_parts = []

        for i, chunk in enumerate(chunks[:max_chunks], 1):
            text = chunk.get("text", "")[:500]
            context_parts.append(f"[来源{i}] {text}")

        return "\n\n".join(context_parts)

    def _parse_verification_response(self, response: str) -> dict:
        """Parse verification result from LLM response"""
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
            logger.warning("verification_parse_failed", error=str(e))

        return {"decision": "accept", "faithfulness_score": 0.5}

    def _fallback_verification(
        self,
        answer: str,
        chunks: list[dict],
    ) -> VerificationResult:
        """Fallback verification when LLM fails"""
        has_citation = "来源" in answer or "[" in answer
        has_content = len(answer) > 20

        return VerificationResult(
            decision=VerificationDecision.ACCEPT if has_content else VerificationDecision.REGENERATE,
            faithfulness_score=0.5,
            has_hallucination=not has_content,
            citation_accuracy=0.5 if has_citation else 0.0,
            issues=[] if has_content else ["Answer too short or empty"],
            revised_answer=None,
        )
