"""
RAG Tracer
Comprehensive tracing for RAG pipeline
"""
import json
import time
import uuid
import structlog
from typing import Optional
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from backend.core.agent.planner import RetrievalPlan

logger = structlog.get_logger()


class QueryType(str, Enum):
    """Query classification types"""
    SIMPLE = "simple"
    MULTI_HOP = "multi_hop"
    AMBIGUOUS = "ambiguous"


@dataclass
class StateTransition:
    """Agent state transition record"""
    from_state: str
    to_state: str
    timestamp: float


@dataclass
class RetrievalRound:
    """Record of a single retrieval round"""
    round_id: int
    sub_query: str
    retrieval_method: str
    top_k: int
    retrieved_chunks: list[dict]
    scores: dict
    latency_ms: float


@dataclass
class GenerationMetadata:
    """Generation metadata"""
    prompt: str
    response: str
    token_count: int
    latency_ms: float
    model: str


@dataclass
class VerificationMetadata:
    """Verification metadata"""
    faithfulness_score: float
    has_hallucination: bool
    citation_accuracy: float
    decision: str


@dataclass
class RAGTrace:
    """Complete trace of a RAG pipeline execution"""
    trace_id: str
    query: str
    query_type: str
    timestamp: str

    state_history: list[dict]
    planning_steps: list[dict]
    reflection_rounds: int

    retrieval_rounds: list[dict]
    total_chunks_retrieved: int

    generation: Optional[dict]
    verification: Optional[dict]

    answer: str
    sources_count: int

    total_latency_ms: float
    error: Optional[str] = None


class RAGTracer:
    """
    Traces and records RAG pipeline executions.

    Provides:
    - Full pipeline tracing
    - Query type classification
    - State transition recording
    - Retrieval metrics
    - Generation metrics
    - Verification results
    """

    def __init__(
        self,
        enable_tracing: bool = True,
        traces_dir: str = "./data/traces",
    ):
        self.enable_tracing = enable_tracing
        self.traces_dir = Path(traces_dir)
        self.traces_dir.mkdir(parents=True, exist_ok=True)

        self._traces: dict[str, RAGTrace] = {}
        self._index_file = self.traces_dir / "index.json"
        self._trace_ids = deque(maxlen=1000)
        self._load_index()

        self._metrics = {
            "total_queries": 0,
            "query_types": {"simple": 0, "multi_hop": 0, "ambiguous": 0},
            "total_latency_ms": 0,
            "reflection_rounds": deque(maxlen=1000),
            "chunks_retrieved": deque(maxlen=1000),
            "success_count": 0,
        }

    def _load_index(self):
        """Load trace index from disk"""
        if self._index_file.exists():
            try:
                with open(self._index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                    trace_ids = index.get("trace_ids", [])
                    for tid in trace_ids[-1000:]:
                        self._trace_ids.append(tid)
            except Exception:
                pass

    def _save_index(self):
        """Save trace index to disk"""
        index = {"trace_ids": list(self._trace_ids)[-100:]}
        with open(self._index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def create_trace(self, query: str, conversation_id: Optional[str] = None) -> str:
        """Create a new trace ID for a query"""
        trace_id = str(uuid.uuid4())[:12]

        trace = RAGTrace(
            trace_id=trace_id,
            query=query,
            query_type="unknown",
            timestamp=datetime.now().isoformat(),
            state_history=[],
            planning_steps=[],
            reflection_rounds=0,
            retrieval_rounds=[],
            total_chunks_retrieved=0,
            generation=None,
            verification=None,
            answer="",
            sources_count=0,
            total_latency_ms=0,
        )

        self._traces[trace_id] = trace
        self._metrics["total_queries"] += 1

        logger.info("trace_created", trace_id=trace_id, query=query[:100])
        return trace_id

    def record_trace(self, ctx):
        """Record a completed trace from orchestrator context"""
        trace_id = ctx.trace_id

        if trace_id not in self._traces:
            logger.warning("trace_not_found", trace_id=trace_id)
            return

        trace = self._traces[trace_id]

        trace.query_type = getattr(ctx, "query_analysis", None)
        if trace.query_type and hasattr(trace.query_type, "query_type"):
            trace.query_type = trace.query_type.query_type.value
        elif isinstance(trace.query_type, dict):
            trace.query_type = trace.query_type.get("query_type", "unknown")
        else:
            trace.query_type = "simple"

        trace.state_history = [
            {
                "from": t.from_state.value if hasattr(t.from_state, 'value') else str(t.from_state),
                "to": t.to_state.value if hasattr(t.to_state, 'value') else str(t.to_state),
                "timestamp": t.timestamp,
            }
            for t in ctx.state_history
        ]

        trace.planning_steps = [
            {
                "step_id": s.step_id,
                "action": s.action,
                "sub_query": s.sub_query,
            }
            for s in (getattr(ctx, "retrieval_plan", None) or RetrievalPlan(
                plan_type="direct", steps=[], final_strategy="", reasoning=""
            )).steps
            if hasattr(s, "step_id")
        ]

        trace.reflection_rounds = ctx.reflection_rounds
        trace.total_chunks_retrieved = len(ctx.all_chunks)

        trace.retrieval_rounds = [
            {
                "round_id": i,
                "chunks_count": len(ctx.all_chunks),
            }
            for i in range(ctx.retrieval_rounds)
        ]

        if ctx.generation:
            trace.answer = ctx.generation

        trace.sources_count = len(ctx.all_chunks)
        trace.total_latency_ms = (ctx.end_time - ctx.start_time) * 1000 if ctx.end_time else 0

        trace.error = ctx.error

        if not ctx.error:
            self._metrics["success_count"] += 1

        type_key = trace.query_type or "simple"
        if type_key in self._metrics["query_types"]:
            self._metrics["query_types"][type_key] += 1

        self._metrics["total_latency_ms"] += trace.total_latency_ms
        self._metrics["reflection_rounds"].append(trace.reflection_rounds)
        self._metrics["chunks_retrieved"].append(trace.total_chunks_retrieved)

        self._save_trace(trace)

        self._trace_ids.append(trace_id)
        self._save_index()

        logger.info("trace_recorded", trace_id=trace_id, latency_ms=trace.total_latency_ms)

    def _save_trace(self, trace: RAGTrace):
        """Save trace to disk"""
        trace_file = self.traces_dir / f"{trace.trace_id}.json"

        trace_data = {
            "trace_id": trace.trace_id,
            "query": trace.query,
            "query_type": trace.query_type,
            "timestamp": trace.timestamp,
            "state_history": trace.state_history,
            "planning_steps": trace.planning_steps,
            "reflection_rounds": trace.reflection_rounds,
            "retrieval_rounds": trace.retrieval_rounds,
            "total_chunks_retrieved": trace.total_chunks_retrieved,
            "generation": trace.generation,
            "verification": trace.verification,
            "answer": trace.answer,
            "sources_count": trace.sources_count,
            "total_latency_ms": trace.total_latency_ms,
            "error": trace.error,
        }

        with open(trace_file, "w", encoding="utf-8") as f:
            json.dump(trace_data, f, ensure_ascii=False, indent=2)

    def get_trace(self, trace_id: str) -> Optional[dict]:
        """Get a trace by ID"""
        trace_file = self.traces_dir / f"{trace_id}.json"

        if not trace_file.exists():
            trace = self._traces.get(trace_id)
            if trace:
                return {
                    "trace_id": trace.trace_id,
                    "query": trace.query,
                    "query_type": trace.query_type,
                    "timestamp": trace.timestamp,
                    "state_history": trace.state_history,
                    "reflection_rounds": trace.reflection_rounds,
                    "retrieval_rounds": trace.retrieval_rounds,
                    "answer": trace.answer,
                    "total_latency_ms": trace.total_latency_ms,
                }
            return None

        try:
            with open(trace_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("trace_load_failed", error=str(e))
            return None

    def list_traces(
        self,
        skip: int = 0,
        limit: int = 50,
        query_type: Optional[str] = None,
    ) -> list[dict]:
        """List traces with pagination"""
        traces = []

        for trace_id in reversed(self._trace_ids):
            trace = self.get_trace(trace_id)
            if trace:
                if query_type and trace.get("query_type") != query_type:
                    continue
                traces.append(trace)

        return traces[skip : skip + limit]

    def get_metrics(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        aggregation: str = "hour",
    ) -> dict:
        """Get aggregated metrics"""
        avg_latency = (
            self._metrics["total_latency_ms"] / max(self._metrics["total_queries"], 1)
        )

        avg_reflection = (
            sum(self._metrics["reflection_rounds"]) /
            max(len(self._metrics["reflection_rounds"]), 1)
        )

        avg_chunks = (
            sum(self._metrics["chunks_retrieved"]) /
            max(len(self._metrics["chunks_retrieved"]), 1)
        )

        return {
            "total_queries": self._metrics["total_queries"],
            "successful_queries": self._metrics["success_count"],
            "success_rate": self._metrics["success_count"] / max(self._metrics["total_queries"], 1),
            "avg_latency_ms": avg_latency,
            "avg_reflection_rounds": avg_reflection,
            "avg_chunks_retrieved": avg_chunks,
            "query_type_distribution": self._metrics["query_types"],
        }

    def get_retrieval_quality(self, collection_name: str = "default") -> dict:
        """Get retrieval quality metrics"""
        recent_traces = self.list_traces(limit=100)

        retrieval_scores = []
        for trace in recent_traces:
            for round_info in trace.get("retrieval_rounds", []):
                if "chunks_count" in round_info:
                    retrieval_scores.append(round_info["chunks_count"])

        return {
            "avg_chunks_per_query": sum(retrieval_scores) / max(len(retrieval_scores), 1),
            "total_retrievals": len(retrieval_scores),
            "collection": collection_name,
        }

    def get_generation_quality(self) -> dict:
        """Get generation quality metrics"""
        recent_traces = self.list_traces(limit=100)

        answer_lengths = []
        for trace in recent_traces:
            answer = trace.get("answer", "")
            if answer:
                answer_lengths.append(len(answer))

        return {
            "avg_answer_length": sum(answer_lengths) / max(len(answer_lengths), 1),
            "total_generations": len(answer_lengths),
        }

    def get_dashboard(self) -> dict:
        """Get dashboard overview data"""
        return {
            "overview": {
                "total_queries": self._metrics["total_queries"],
                "avg_response_time_ms": self._metrics["total_latency_ms"] / max(self._metrics["total_queries"], 1),
                "avg_reflection_rounds": sum(self._metrics["reflection_rounds"]) / max(len(self._metrics["reflection_rounds"]), 1),
                "success_rate": self._metrics["success_count"] / max(self._metrics["total_queries"], 1),
            },
            "query_types": self._metrics["query_types"],
            "recent_traces": self.list_traces(limit=10),
        }

    def get_total_queries(self) -> int:
        return self._metrics["total_queries"]

    def get_avg_response_time(self) -> float:
        return self._metrics["total_latency_ms"] / max(self._metrics["total_queries"], 1)

    def get_avg_reflection_rounds(self) -> float:
        if not self._metrics["reflection_rounds"]:
            return 0.0
        return sum(self._metrics["reflection_rounds"]) / len(self._metrics["reflection_rounds"])

    def get_success_rate(self) -> float:
        return self._metrics["success_count"] / max(self._metrics["total_queries"], 1)

    def get_query_type_distribution(self) -> dict:
        return self._metrics["query_types"]

    def get_conversation_history(self, conversation_id: str) -> list[dict]:
        return []

    def export_traces(
        self,
        format: str = "json",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> list[dict]:
        """Export traces in specified format"""
        traces = []
        for trace_id in self._trace_ids:
            trace = self.get_trace(trace_id)
            if trace:
                traces.append(trace)
        return traces

    def get_logs(
        self,
        trace_id: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """Get logs with optional filtering"""
        return []
