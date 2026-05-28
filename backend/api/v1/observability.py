"""
Observability API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Any
import structlog

from backend.api.deps import get_tracer

router = APIRouter()
logger = structlog.get_logger()


class TraceResponse(BaseModel):
    """Trace response"""
    trace_id: str
    query: str
    query_type: str
    timestamp: str
    state_history: list[dict]
    retrieval_rounds: list[dict]
    generation: dict
    verification: dict


@router.get("/observability/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Get a specific trace by ID"""
    tracer = get_tracer()
    trace = tracer.get_trace(trace_id)

    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")

    return trace


@router.get("/observability/traces")
async def list_traces(
    skip: int = 0,
    limit: int = 50,
    query_type: Optional[str] = None,
):
    """List all traces with pagination"""
    tracer = get_tracer()
    traces = tracer.list_traces(skip=skip, limit=limit, query_type=query_type)
    return {"traces": traces, "total": len(traces)}


@router.get("/observability/metrics")
async def get_metrics(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    aggregation: str = "hour",
):
    """Get aggregated metrics"""
    tracer = get_tracer()
    metrics = tracer.get_metrics(start_time, end_time, aggregation)

    return {
        "metrics": metrics,
        "aggregation": aggregation,
        "time_range": {"start": start_time, "end": end_time},
    }


@router.get("/observability/retrieval-quality")
async def get_retrieval_quality(
    collection_name: str = "default",
):
    """Get retrieval quality metrics"""
    tracer = get_tracer()
    quality = tracer.get_retrieval_quality(collection_name)
    return quality


@router.get("/observability/generation-quality")
async def get_generation_quality():
    """Get generation quality metrics"""
    tracer = get_tracer()
    quality = tracer.get_generation_quality()
    return quality


@router.get("/observability/dashboard")
async def get_dashboard():
    """Get dashboard overview"""
    tracer = get_tracer()

    return {
        "overview": {
            "total_queries": tracer.get_total_queries(),
            "avg_response_time_ms": tracer.get_avg_response_time(),
            "avg_reflection_rounds": tracer.get_avg_reflection_rounds(),
            "success_rate": tracer.get_success_rate(),
        },
        "query_types": tracer.get_query_type_distribution(),
        "recent_traces": tracer.list_traces(limit=10),
    }


@router.post("/observability/export")
async def export_traces(
    format: str = "json",
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    """Export traces in specified format"""
    tracer = get_tracer()
    data = tracer.export_traces(format=format, start_time=start_time, end_time=end_time)
    return {"format": format, "data": data}


@router.get("/observability/logs")
async def get_logs(
    trace_id: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = 100,
):
    """Get logs with optional filtering"""
    tracer = get_tracer()
    logs = tracer.get_logs(trace_id=trace_id, level=level, limit=limit)
    return {"logs": logs, "total": len(logs)}


# Debug Panel endpoints under /observability/debug/
from pydantic import BaseModel


class DebugQueryRequest(BaseModel):
    query: str
    trace_enabled: bool = True
    verbose: bool = False


class DebugStepResult(BaseModel):
    step: str
    status: str
    duration_ms: float
    result: Optional[dict] = None
    error: Optional[str] = None


class DebugTraceResult(BaseModel):
    query: str
    steps: list[DebugStepResult]
    total_duration_ms: float
    trace_id: str


@router.post("/observability/debug/step", response_model=DebugStepResult)
async def debug_single_step(
    step: str,
    query: str,
):
    """Debug a single step of the RAG pipeline."""
    import time
    logger.info("debug_step_requested", step=step, query=query[:100])
    start_time = time.time()
    try:
        from backend.api.deps import get_orchestrator
        orchestrator = get_orchestrator()
        if step == "analyze":
            result = await orchestrator.query_analyzer.analyze(query)
            return DebugStepResult(
                step=step, status="success", duration_ms=(time.time() - start_time) * 1000,
                result={"query_type": result.query_type.value, "entities": result.entities,
                        "suggested_approach": result.suggested_approach},
            )
        elif step == "retrieve":
            chunks = await orchestrator.hybrid_retriever.search(query, top_k=5)
            return DebugStepResult(
                step=step, status="success", duration_ms=(time.time() - start_time) * 1000,
                result={"chunks_count": len(chunks), "top_scores": [c.get("score", 0) for c in chunks[:5]]},
            )
        return DebugStepResult(
            step=step, status="not_implemented", duration_ms=(time.time() - start_time) * 1000,
            error=f"Debug for step '{step}' not implemented",
        )
    except Exception as e:
        logger.error("debug_step_failed", step=step, error=str(e))
        return DebugStepResult(
            step=step, status="error", duration_ms=(time.time() - start_time) * 1000,
            error=str(e),
        )


@router.post("/observability/debug/trace", response_model=DebugTraceResult)
async def debug_full_trace(request: DebugQueryRequest):
    """Debug the full RAG pipeline with detailed step tracking."""
    import time
    from backend.api.deps import get_orchestrator
    logger.info("debug_trace_requested", query=request.query[:100])
    start_time = time.time()
    steps = []
    try:
        orchestrator = get_orchestrator()
        s = time.time()
        analysis = await orchestrator.query_analyzer.analyze(request.query)
        steps.append(DebugStepResult(step="analyze", status="success", duration_ms=(time.time() - s) * 1000,
                                    result={"query_type": analysis.query_type.value}))

        s = time.time()
        plan = await orchestrator.planner.create_plan(request.query, analysis.query_type.value)
        steps.append(DebugStepResult(step="plan", status="success", duration_ms=(time.time() - s) * 1000,
                                    result={"plan_type": plan.plan_type.value, "steps": len(plan.steps)}))

        s = time.time()
        chunks = await orchestrator.hybrid_retriever.search(request.query, top_k=10)
        steps.append(DebugStepResult(step="retrieve", status="success", duration_ms=(time.time() - s) * 1000,
                                    result={"chunks_count": len(chunks)}))

        s = time.time()
        reranked = await orchestrator.reranker.rerank(request.query, chunks, top_k=5)
        steps.append(DebugStepResult(step="rerank", status="success", duration_ms=(time.time() - s) * 1000,
                                    result={"reranked_count": len(reranked)}))

        s = time.time()
        context = orchestrator._build_context(reranked)
        steps.append(DebugStepResult(step="context", status="success", duration_ms=(time.time() - s) * 1000,
                                    result={"context_length": len(context)}))

        s = time.time()
        answer = await orchestrator.generator.generate(f"基于以下内容回答：\n{context}\n\n问题：{request.query}")
        steps.append(DebugStepResult(step="generate", status="success", duration_ms=(time.time() - s) * 1000,
                                    result={"answer_length": len(answer)}))

        return DebugTraceResult(
            query=request.query, steps=steps,
            total_duration_ms=(time.time() - start_time) * 1000, trace_id="debug",
        )
    except Exception as e:
        logger.error("debug_trace_failed", error=str(e))
        return DebugTraceResult(
            query=request.query, steps=steps,
            total_duration_ms=(time.time() - start_time) * 1000, trace_id="error",
        )


@router.get("/observability/debug/state")
async def get_debug_state():
    """Get current system state"""
    return {
        "status": "running",
        "components": {
            "generator": "ready", "retriever": "ready",
            "reranker": "ready", "query_rewriter": "ready",
        },
    }
