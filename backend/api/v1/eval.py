"""
Evaluation API
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Any
import structlog

from backend.api.deps import get_orchestrator

router = APIRouter()
logger = structlog.get_logger()


class EvaluationRequest(BaseModel):
    """Evaluation request"""
    query: str = Field(..., description="Test query")
    ground_truth: str = Field(..., description="Expected answer")
    top_k: int = Field(10, description="Retrieval top_k")


class EvaluationResult(BaseModel):
    """Evaluation result"""
    retrieval_metrics: dict
    generation_metrics: dict
    overall_score: float


@router.post("/eval/run")
async def run_evaluation(request: EvaluationRequest):
    """
    Run evaluation on a single query.

    Returns retrieval and generation metrics.
    """
    logger.info("evaluation_started", query=request.query)

    try:
        orchestrator = get_orchestrator()

        result = await orchestrator.query(
            query=request.query,
            top_k=request.top_k,
            enable_reflection=True,
            enable_verification=True,
        )

        answer = result["answer"]
        ground_truth = request.ground_truth

        from backend.observability.evaluator import RAGEvaluator
        evaluator = RAGEvaluator()

        metrics = evaluator.evaluate_single(
            query=request.query,
            answer=answer,
            ground_truth=ground_truth,
            retrieved_chunks=result.get("sources", []),
        )

        return EvaluationResult(
            retrieval_metrics=metrics.get("retrieval", {}),
            generation_metrics=metrics.get("generation", {}),
            overall_score=metrics.get("overall", 0.0),
        )

    except Exception as e:
        logger.error("evaluation_failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/eval/batch")
async def batch_evaluation(
    test_cases: list[dict],
):
    """
    Run batch evaluation on multiple test cases.

    Each test case should have: query, ground_truth
    """
    logger.info("batch_evaluation_started", test_count=len(test_cases))

    results = []
    orchestrator = get_orchestrator()

    for i, case in enumerate(test_cases):
        try:
            result = await orchestrator.query(
                query=case["query"],
                top_k=case.get("top_k", 10),
            )

            from backend.observability.evaluator import RAGEvaluator
            evaluator = RAGEvaluator()

            metrics = evaluator.evaluate_single(
                query=case["query"],
                answer=result["answer"],
                ground_truth=case["ground_truth"],
                retrieved_chunks=result.get("sources", []),
            )

            results.append({
                "query": case["query"],
                "status": "success",
                "metrics": metrics,
            })

        except Exception as e:
            results.append({
                "query": case["query"],
                "status": "failed",
                "error": str(e),
            })

    avg_score = sum(
        r.get("metrics", {}).get("overall", 0) for r in results if r["status"] == "success"
    ) / max(len([r for r in results if r["status"] == "success"]), 1)

    return {
        "results": results,
        "summary": {
            "total": len(test_cases),
            "passed": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "average_score": avg_score,
        },
    }


@router.get("/eval/benchmarks")
async def get_benchmarks():
    """Get available benchmark datasets"""
    return {
        "benchmarks": [
            {"name": "HotpotQA", "description": "Multi-hop reasoning", "size": 90447},
            {"name": "NaturalQuestions", "description": "Real user questions", "size": 36361},
            {"name": "TriviaQA", "description": "Question answering", "size": 78368},
            {"name": "2WikiMultiHopQA", "description": "Multi-hop from Wikipedia", "size": 22996},
        ]
    }
