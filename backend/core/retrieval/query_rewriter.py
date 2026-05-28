"""
Query Rewriter
Expands, decomposes, and refines user queries
"""
import json
import structlog
from typing import Optional
from enum import Enum

from backend.core.agent.prompts import SYSTEM_PROMPTS
from backend.config import settings

logger = structlog.get_logger()


class RewriteMode(str, Enum):
    """Query rewrite modes"""
    EXPAND = "expand"
    DECOMPOSE = "decompose"
    CLARIFY = "clarify"
    BOTH = "both"


class QueryRewriter:
    """
    Rewrites queries for better retrieval performance.

    Supports:
    - Expansion: Generate alternative phrasings
    - Decomposition: Split into sub-questions for multi-hop
    - Clarification: Resolve ambiguity
    """

    def __init__(self, generator):
        self.generator = generator

    async def expand_query(self, query: str) -> list[str]:
        """
        Expand query with alternative phrasings.

        Generates multiple versions of the query with different
        wordings and synonyms to improve recall.
        """
        logger.info("expanding_query", query=query[:100])

        prompt = f"""你是一个查询扩展专家。为给定的查询生成3-5个语义等价但表述不同的替代查询。

原始查询：{query}

请生成替代查询，每个查询应该：
1. 保持相同的语义意图
2. 使用不同的词汇或句式
3. 可能包含同义词或相关概念

以JSON数组格式输出：
["替代查询1", "替代查询2", "替代查询3", ...]
"""

        try:
            response = await self.generator.generate(prompt, system_prompt=None)

            expanded = self._parse_json_array(response)

            all_queries = [query] + expanded

            logger.info("query_expanded", original=query[:50], alternatives=len(expanded))

            return all_queries

        except Exception as e:
            logger.error("query_expansion_failed", error=str(e))
            return [query]

    async def decompose_query(self, query: str) -> list[list[str]]:
        """
        Decompose complex query into sub-questions.

        For multi-hop queries, breaks down into simpler sub-questions
        that can be answered independently and combined.
        """
        logger.info("decomposing_query", query=query[:100])

        prompt = f"""你是一个查询分解专家。将复杂问题分解为更简单的子问题。

复杂问题：{query}

请分析这个问题：
1. 是否需要多步推理？
2. 需要哪些独立的信息片段？
3. 子问题的回答如何组合？

如果问题是简单的（不需要多步推理），直接返回空数组。
如果问题复杂，按以下JSON格式输出：
{{
    "is_multi_hop": true/false,
    "sub_questions": ["子问题1", "子问题2", ...],
    "reasoning_steps": ["推理步骤1", ...]
}}
"""

        try:
            response = await self.generator.generate(prompt, system_prompt=None)

            data = self._parse_json_object(response)

            if not data.get("is_multi_hop", False):
                logger.info("query_not_multi_hop", query=query[:50])
                return [[query]]

            sub_questions = data.get("sub_questions", [])
            if not sub_questions:
                return [[query]]

            logger.info(
                "query_decomposed",
                original=query[:50],
                sub_questions=len(sub_questions),
            )

            return [sub_questions]

        except Exception as e:
            logger.error("query_decomposition_failed", error=str(e))
            return [[query]]

    async def clarify_query(self, query: str) -> dict:
        """
        Clarify ambiguous queries.

        Identifies ambiguity and generates clarifying questions
        or most likely interpretations.
        """
        logger.info("clarifying_query", query=query[:100])

        prompt = f"""你是一个查询消歧专家。分析以下查询中的歧义。

查询：{query}

检查以下方面：
1. 模糊的指代（如"它"、"这个"）
2. 多义词（如"苹果"可以指水果或公司）
3. 隐含的上下文（谁？什么时间？在哪里？）
4. 不完整的条件

输出JSON格式：
{{
    "is_ambiguous": true/false,
    "ambiguities": ["歧义1", "歧义2", ...],
    "clarifying_questions": ["澄清问题1", ...],
    "most_likely_interpretation": "最可能的解释"
}}
"""

        try:
            response = await self.generator.generate(prompt, system_prompt=None)
            result = self._parse_json_object(response)

            return result

        except Exception as e:
            logger.error("query_clarification_failed", error=str(e))
            return {"is_ambiguous": False, "ambiguities": []}

    async def rewrite(
        self,
        query: str,
        mode: RewriteMode = RewriteMode.EXPAND,
    ) -> dict:
        """
        Full query rewrite pipeline.

        Args:
            query: Original query
            mode: Rewrite mode

        Returns:
            Dictionary with rewritten queries and metadata
        """
        result = {
            "original_query": query,
            "expanded_queries": [],
            "decomposed_queries": [],
            "clarification": {},
        }

        if mode in [RewriteMode.EXPAND, RewriteMode.BOTH]:
            result["expanded_queries"] = await self.expand_query(query)

        if mode in [RewriteMode.DECOMPOSE, RewriteMode.BOTH]:
            result["decomposed_queries"] = await self.decompose_query(query)

        if mode == RewriteMode.CLARIFY:
            result["clarification"] = await self.clarify_query(query)

        return result

    async def rewrite_for_retrieval(
        self,
        query: str,
        top_k_expansions: int = 3,
    ) -> list[str]:
        """
        Rewrite query specifically for retrieval.

        Returns a list of queries to use for retrieval.
        """
        rewrite_result = await self.rewrite(query, mode=RewriteMode.BOTH)

        retrieval_queries = []

        if rewrite_result["expanded_queries"]:
            retrieval_queries.extend(rewrite_result["expanded_queries"][:top_k_expansions])

        if rewrite_result["decomposed_queries"]:
            retrieval_queries.extend(rewrite_result["decomposed_queries"][0][:top_k_expansions])

        if not retrieval_queries:
            retrieval_queries = [query]

        return list(dict.fromkeys(retrieval_queries))[:5]

    def _parse_json_array(self, text: str) -> list[str]:
        """Parse JSON array from text"""
        text = text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        start = text.find("[")
        end = text.rfind("]") + 1

        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        lines = text.strip().split("\n")
        queries = []
        for line in lines:
            line = line.strip().strip('"').strip("'")
            if line and not line.startswith("{") and not line.startswith("["):
                queries.append(line)

        return queries

    def _parse_json_object(self, text: str) -> dict:
        """Parse JSON object from text"""
        text = text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        start = text.find("{")
        end = text.rfind("}") + 1

        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        return {}
