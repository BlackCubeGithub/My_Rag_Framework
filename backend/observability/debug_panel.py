"""
Debug Panel API
Built-in debugging tools for RAG pipeline inspection
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
import structlog

from backend.api.deps import get_tracer, get_orchestrator

router = APIRouter()
logger = structlog.get_logger()


class DebugQueryRequest(BaseModel):
    """Debug query request"""
    query: str
    trace_enabled: bool = True
    verbose: bool = False


class DebugStepResult(BaseModel):
    """Result of a single debug step"""
    step: str
    status: str
    duration_ms: float
    result: Optional[dict] = None
    error: Optional[str] = None


class DebugTraceResult(BaseModel):
    """Complete debug trace result"""
    query: str
    steps: list[DebugStepResult]
    total_duration_ms: float
    trace_id: str


@router.post("/debug/step", response_model=DebugStepResult)
async def debug_single_step(
    step: str,
    query: str,
):
    """
    Debug a single step of the RAG pipeline.

    Available steps:
    - analyze: Query analysis
    - plan: Retrieval planning
    - retrieve: Retrieval execution
    - reflect: Reflection evaluation
    - generate: Answer generation
    - verify: Answer verification
    """
    import time

    logger.info("debug_step_requested", step=step, query=query[:100])
    start_time = time.time()

    try:
        orchestrator = get_orchestrator()

        if step == "analyze":
            result = await orchestrator.query_analyzer.analyze(query)
            return DebugStepResult(
                step=step,
                status="success",
                duration_ms=(time.time() - start_time) * 1000,
                result={
                    "query_type": result.query_type.value,
                    "entities": result.entities,
                    "suggested_approach": result.suggested_approach,
                },
            )

        elif step == "retrieve":
            chunks = await orchestrator.hybrid_retriever.search(query, top_k=5)
            return DebugStepResult(
                step=step,
                status="success",
                duration_ms=(time.time() - start_time) * 1000,
                result={"chunks_count": len(chunks), "top_scores": [c.get("score", 0) for c in chunks[:5]]},
            )

        else:
            return DebugStepResult(
                step=step,
                status="not_implemented",
                duration_ms=(time.time() - start_time) * 1000,
                error=f"Debug for step '{step}' not implemented",
            )

    except Exception as e:
        logger.error("debug_step_failed", step=step, error=str(e))
        return DebugStepResult(
            step=step,
            status="error",
            duration_ms=(time.time() - start_time) * 1000,
            error=str(e),
        )


@router.post("/debug/trace", response_model=DebugTraceResult)
async def debug_full_trace(request: DebugQueryRequest):
    """
    Debug the full RAG pipeline with detailed step tracking.

    Returns detailed timing and results for each step.
    """
    import time

    logger.info("debug_trace_requested", query=request.query[:100])
    start_time = time.time()

    steps = []

    try:
        orchestrator = get_orchestrator()

        step_start = time.time()
        analysis = await orchestrator.query_analyzer.analyze(request.query)
        steps.append(DebugStepResult(
            step="analyze",
            status="success",
            duration_ms=(time.time() - step_start) * 1000,
            result={"query_type": analysis.query_type.value},
        ))

        step_start = time.time()
        plan = await orchestrator.planner.create_plan(
            request.query,
            analysis.query_type.value,
        )
        steps.append(DebugStepResult(
            step="plan",
            status="success",
            duration_ms=(time.time() - step_start) * 1000,
            result={"plan_type": plan.plan_type.value, "steps": len(plan.steps)},
        ))

        step_start = time.time()
        chunks = await orchestrator.hybrid_retriever.search(request.query, top_k=10)
        steps.append(DebugStepResult(
            step="retrieve",
            status="success",
            duration_ms=(time.time() - step_start) * 1000,
            result={"chunks_count": len(chunks)},
        ))

        step_start = time.time()
        reranked = await orchestrator.reranker.rerank(request.query, chunks, top_k=5)
        steps.append(DebugStepResult(
            step="rerank",
            status="success",
            duration_ms=(time.time() - step_start) * 1000,
            result={"reranked_count": len(reranked)},
        ))

        step_start = time.time()
        context = orchestrator._build_context(reranked)
        steps.append(DebugStepResult(
            step="context",
            status="success",
            duration_ms=(time.time() - step_start) * 1000,
            result={"context_length": len(context)},
        ))

        step_start = time.time()
        answer = await orchestrator.generator.generate(
            f"基于以下内容回答：\n{context}\n\n问题：{request.query}"
        )
        steps.append(DebugStepResult(
            step="generate",
            status="success",
            duration_ms=(time.time() - step_start) * 1000,
            result={"answer_length": len(answer)},
        ))

        total_time = (time.time() - start_time) * 1000

        return DebugTraceResult(
            query=request.query,
            steps=steps,
            total_duration_ms=total_time,
            trace_id="debug",
        )

    except Exception as e:
        logger.error("debug_trace_failed", error=str(e))
        return DebugTraceResult(
            query=request.query,
            steps=steps,
            total_duration_ms=(time.time() - start_time) * 1000,
            trace_id="error",
        )


@router.get("/debug/state")
async def get_current_state():
    """Get current system state"""
    return {
        "status": "running",
        "components": {
            "generator": "ready",
            "retriever": "ready",
            "reranker": "ready",
            "query_rewriter": "ready",
        },
    }
