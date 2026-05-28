"""
Planner Module
Multi-hop planning for complex queries
"""
import json
import structlog
from typing import Optional
from enum import Enum
from dataclasses import dataclass

from backend.core.agent.prompts import SYSTEM_PROMPTS

logger = structlog.get_logger()


class PlanType(str, Enum):
    """Planning strategy types"""
    DIRECT = "direct"
    DECOMPOSE = "decompose"
    EXPAND = "expand"
    ITERATIVE = "iterative"


@dataclass
class PlanningStep:
    """Represents a single step in the retrieval plan"""
    step_id: int
    action: str
    sub_query: str
    dependencies: list[int]
    expected_output: str


@dataclass
class RetrievalPlan:
    """Complete retrieval plan for a query"""
    plan_type: PlanType
    steps: list[PlanningStep]
    final_strategy: str
    reasoning: str


from dataclasses import dataclass


class Planner:
    """
    Multi-hop planning for RAG queries.

    Analyzes complex queries and creates retrieval plans
    that may involve multiple steps, dependencies, and strategies.
    """

    def __init__(self, generator):
        self.generator = generator

    async def create_plan(
        self,
        query: str,
        query_type: str,
        analysis_result: Optional[dict] = None,
    ) -> RetrievalPlan:
        """
        Create a retrieval plan based on query analysis.

        Args:
            query: User query
            query_type: Type of query (simple, multi_hop, ambiguous)
            analysis_result: Optional detailed analysis

        Returns:
            RetrievalPlan with steps and strategy
        """
        logger.info("creating_plan", query_type=query_type, query=query[:100])

        if query_type == "simple":
            return self._create_direct_plan(query)
        elif query_type == "multi_hop":
            return await self._create_decompose_plan(query)
        elif query_type == "ambiguous":
            return await self._create_iterative_plan(query)

        return self._create_direct_plan(query)

    def _create_direct_plan(self, query: str) -> RetrievalPlan:
        """Create a direct single-step retrieval plan"""
        return RetrievalPlan(
            plan_type=PlanType.DIRECT,
            steps=[
                PlanningStep(
                    step_id=0,
                    action="retrieve",
                    sub_query=query,
                    dependencies=[],
                    expected_output="Direct answer from retrieval",
                )
            ],
            final_strategy="direct_retrieval",
            reasoning="Simple query, single retrieval step sufficient",
        )

    async def _create_decompose_plan(self, query: str) -> RetrievalPlan:
        """Create a plan that decomposes the query into sub-questions"""
        prompt = f"""{SYSTEM_PROMPTS['planner']}

【用户查询】
{query}

请为这个复杂问题创建检索计划。分解为多个子问题，并确定每个子问题之间的关系。
"""

        try:
            response = await self.generator.generate(prompt, system_prompt=None)
            plan_data = self._parse_plan_response(response)

            steps = []
            for i, step_data in enumerate(plan_data.get("steps", [])):
                steps.append(PlanningStep(
                    step_id=i,
                    action=step_data.get("action", "retrieve"),
                    sub_query=step_data.get("sub_query", query),
                    dependencies=step_data.get("dependencies", []),
                    expected_output=step_data.get("expected_output", ""),
                ))

            logger.info(
                "decompose_plan_created",
                query=query[:50],
                steps=len(steps),
            )

            return RetrievalPlan(
                plan_type=PlanType.DECOMPOSE,
                steps=steps,
                final_strategy=plan_data.get("final_strategy", "combine_answers"),
                reasoning=plan_data.get("reasoning", "Multi-hop query decomposed"),
            )

        except Exception as e:
            logger.error("plan_creation_failed", error=str(e))
            return self._create_direct_plan(query)

    async def _create_iterative_plan(self, query: str) -> RetrievalPlan:
        """Create an iterative plan with reflection"""
        return RetrievalPlan(
            plan_type=PlanType.ITERATIVE,
            steps=[
                PlanningStep(
                    step_id=0,
                    action="retrieve",
                    sub_query=query,
                    dependencies=[],
                    expected_output="Initial retrieval results",
                ),
                PlanningStep(
                    step_id=1,
                    action="reflect",
                    sub_query="Evaluate if results are sufficient",
                    dependencies=[0],
                    expected_output="Reflection on completeness",
                ),
                PlanningStep(
                    step_id=2,
                    action="refine",
                    sub_query="If needed, refine and retry",
                    dependencies=[1],
                    expected_output="Refined retrieval",
                ),
            ],
            final_strategy="iterative_retrieval_with_feedback",
            reasoning="Ambiguous query requires iterative refinement",
        )

    async def refine_plan(
        self,
        plan: RetrievalPlan,
        reflection_result: dict,
    ) -> RetrievalPlan:
        """
        Refine an existing plan based on reflection.

        Args:
            plan: Original plan
            reflection_result: Reflection feedback

        Returns:
            Refined plan or original if no changes needed
        """
        needs_refinement = reflection_result.get("decision") == "refine"

        if not needs_refinement:
            return plan

        logger.info("refining_plan", original_steps=len(plan.steps))

        additional_queries = reflection_result.get("supplementary_queries", [])

        new_steps = list(plan.steps)
        next_id = len(plan.steps)

        for sub_query in additional_queries:
            new_steps.append(PlanningStep(
                step_id=next_id,
                action="supplementary_retrieve",
                sub_query=sub_query,
                dependencies=[s.step_id for s in plan.steps],
                expected_output="Supplementary information",
            ))
            next_id += 1

        return RetrievalPlan(
            plan_type=plan.plan_type,
            steps=new_steps,
            final_strategy=plan.final_strategy,
            reasoning=f"Plan refined with {len(additional_queries)} additional steps",
        )

    def _parse_plan_response(self, response: str) -> dict:
        """Parse plan from LLM response"""
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
            logger.warning("plan_parse_failed", error=str(e))

        return {
            "steps": [{"action": "retrieve", "sub_query": response, "dependencies": []}],
            "final_strategy": "direct",
        }
