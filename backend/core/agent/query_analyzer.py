"""
Query Analyzer
Analyzes user queries to determine retrieval strategy
"""
import json
import structlog
from typing import Optional
from enum import Enum
from pydantic import BaseModel

from backend.core.agent.prompts import SYSTEM_PROMPTS

logger = structlog.get_logger()


class QueryType(str, Enum):
    """Query classification types"""
    SIMPLE = "simple"
    MULTI_HOP = "multi_hop"
    AMBIGUOUS = "ambiguous"


class QueryAnalysisResult(BaseModel):
    """Query analysis result"""
    query_type: QueryType
    entities: list[str]
    key_concepts: list[str]
    requires_reasoning: bool
    suggested_approach: str
    original_query: str = ""


class QueryAnalyzer:
    """Analyzes user queries for routing decisions"""

    def __init__(self, generator):
        self.generator = generator

    async def analyze(self, query: str) -> QueryAnalysisResult:
        """
        Analyze a user query and determine the best retrieval strategy.

        Returns a structured analysis with query type, entities, and suggested approach.
        """
        logger.info("analyzing_query", query=query[:100])

        prompt = f"""{SYSTEM_PROMPTS['query_analyzer']}

【待分析查询】
{query}

请分析这个查询并输出JSON格式的结果。
"""

        try:
            response = await self.generator.generate(prompt, system_prompt=None)
            result = self._parse_analysis_response(response)
            result.original_query = query

            logger.info(
                "query_analyzed",
                query_type=result.query_type,
                entities=result.entities,
                suggested_approach=result.suggested_approach,
            )

            return result

        except Exception as e:
            logger.error("query_analysis_failed", error=str(e))
            return self._fallback_analysis(query)

    def _parse_analysis_response(self, response: str) -> QueryAnalysisResult:
        """Parse the LLM response into structured result"""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            query_type_str = data.get("query_type", "simple")
            try:
                query_type = QueryType(query_type_str.lower())
            except ValueError:
                logger.warning("unknown_query_type", value=query_type_str)
                query_type = QueryType.SIMPLE

            return QueryAnalysisResult(
                query_type=query_type,
                entities=data.get("entities", []),
                key_concepts=data.get("key_concepts", []),
                requires_reasoning=data.get("requires_reasoning", False),
                suggested_approach=data.get("suggested_retrieval_approach", "直接检索"),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("parse_failed", error=str(e))
            return self._fallback_analysis(response)

    def _extract_json(self, text: str) -> str:
        """Extract JSON from response text"""
        text = text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        start = text.find("{")
        end = text.rfind("}") + 1

        if start >= 0 and end > start:
            return text[start:end]

        raise ValueError("No JSON found in response")

    def _fallback_analysis(self, query: str) -> QueryAnalysisResult:
        """Fallback analysis when LLM parsing fails"""
        has_connector = any(
            word in query for word in ["和", "与", "还是", "还是", "或者", "以及", "比较", "哪个"]
        )

        query_type = QueryType.MULTI_HOP if has_connector else QueryType.SIMPLE

        return QueryAnalysisResult(
            query_type=query_type,
            entities=[],
            key_concepts=[],
            requires_reasoning=query_type == QueryType.MULTI_HOP,
            suggested_approach="分解检索" if query_type == QueryType.MULTI_HOP else "直接检索",
            original_query=query,
        )

    async def quick_classify(self, query: str) -> QueryType:
        """Quick query type classification without full analysis"""
        has_why = any(word in query for word in ["为什么", "为何", "原因", "怎么", "如何"])
        has_compare = any(word in query for word in ["比较", "区别", "差异", "哪个好", "vs"])
        has_multi = any(word in query for word in ["和", "与", "还是", "以及"])

        if has_why or (has_compare and has_multi):
            return QueryType.MULTI_HOP

        words = len(query)
        if words > 30 or has_compare:
            return QueryType.MULTI_HOP

        return QueryType.SIMPLE
