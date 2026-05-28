"""
RAG Tracer
Comprehensive tracing for RAG pipeline
"""
import json
import time
import uuid
import sqlite3
import structlog
from typing import Optional
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from backend.core.agent.planner import RetrievalPlan

logger = structlog.get_logger()

_DB_PATH = "./data/traces/store.db"


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db():
    Path("./data/traces").mkdir(parents=True, exist_ok=True)
    conn = _get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT UNIQUE NOT NULL,
                query TEXT NOT NULL DEFAULT '',
                query_type TEXT NOT NULL DEFAULT 'simple',
                timestamp TEXT NOT NULL,
                state_history TEXT NOT NULL DEFAULT '[]',
                planning_steps TEXT NOT NULL DEFAULT '[]',
                reflection_rounds INTEGER NOT NULL DEFAULT 0,
                retrieval_rounds TEXT NOT NULL DEFAULT '[]',
                total_chunks_retrieved INTEGER NOT NULL DEFAULT 0,
                generation TEXT,
                verification TEXT,
                answer TEXT NOT NULL DEFAULT '',
                sources_count INTEGER NOT NULL DEFAULT 0,
                total_latency_ms REAL NOT NULL DEFAULT 0,
                error TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_traces_timestamp
                ON traces(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_traces_query_type
                ON traces(query_type);
        """)
        conn.commit()
    finally:
        conn.close()


class QueryType(str, Enum):
    SIMPLE = "simple"
    MULTI_HOP = "multi_hop"
    AMBIGUOUS = "ambiguous"


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    timestamp: float


@dataclass
class RetrievalRound:
    round_id: int
    sub_query: str
    retrieval_method: str
    top_k: int
    retrieved_chunks: list[dict]
    scores: dict
    latency_ms: float


@dataclass
class GenerationMetadata:
    prompt: str
    response: str
    token_count: int
    latency_ms: float
    model: str


@dataclass
class VerificationMetadata:
    faithfulness_score: float
    has_hallucination: bool
    citation_accuracy: float
    decision: str


@dataclass
class RAGTrace:
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
    _db_initialized = False

    def __init__(
        self,
        enable_tracing: bool = True,
        traces_dir: str = "./data/traces",
    ):
        self.enable_tracing = enable_tracing
        self.traces_dir = Path(traces_dir)
        self.traces_dir.mkdir(parents=True, exist_ok=True)

        if not RAGTracer._db_initialized:
            _init_db()
            RAGTracer._db_initialized = True

        self._traces: dict[str, RAGTrace] = {}
        self._metrics = {
            "total_queries": 0,
            "query_types": {"simple": 0, "multi_hop": 0, "ambiguous": 0},
            "total_latency_ms": 0,
            "reflection_rounds": deque(maxlen=1000),
            "chunks_retrieved": deque(maxlen=1000),
            "success_count": 0,
        }
        self._load_metrics()

    def _load_metrics(self):
        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT query_type, COUNT(*) as cnt,
                          SUM(total_latency_ms) as total_ms,
                          SUM(reflection_rounds) as total_ref,
                          SUM(total_chunks_retrieved) as total_chunks
                   FROM traces GROUP BY query_type"""
            ).fetchall()
            for r in row:
                qt = r["query_type"] or "simple"
                if qt in self._metrics["query_types"]:
                    self._metrics["query_types"][qt] = r["cnt"]
                self._metrics["total_queries"] += r["cnt"]
                self._metrics["total_latency_ms"] += r["total_ms"] or 0
            self._metrics["success_count"] = conn.execute(
                "SELECT COUNT(*) FROM traces WHERE error IS NULL"
            ).fetchone()[0]
        finally:
            conn.close()

    def create_trace(self, query: str, conversation_id: Optional[str] = None) -> str:
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
                "from": t.from_state.value if hasattr(t.from_state, "value") else str(t.from_state),
                "to": t.to_state.value if hasattr(t.to_state, "value") else str(t.to_state),
                "timestamp": t.timestamp,
            }
            for t in ctx.state_history
        ]

        trace.planning_steps = [
            {"step_id": s.step_id, "action": s.action, "sub_query": s.sub_query}
            for s in (getattr(ctx, "retrieval_plan", None) or RetrievalPlan(
                plan_type="direct", steps=[], final_strategy="", reasoning=""
            )).steps
            if hasattr(s, "step_id")
        ]

        trace.reflection_rounds = ctx.reflection_rounds
        trace.total_chunks_retrieved = len(ctx.all_chunks)

        trace.retrieval_rounds = [
            {"round_id": i, "chunks_count": len(ctx.all_chunks)}
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
        logger.info("trace_recorded", trace_id=trace_id, latency_ms=trace.total_latency_ms)

    def _save_trace(self, trace: RAGTrace):
        conn = _get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO traces
                   (trace_id, query, query_type, timestamp, state_history, planning_steps,
                    reflection_rounds, retrieval_rounds, total_chunks_retrieved, generation,
                    verification, answer, sources_count, total_latency_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace.trace_id,
                    trace.query,
                    trace.query_type,
                    trace.timestamp,
                    json.dumps(trace.state_history, ensure_ascii=False),
                    json.dumps(trace.planning_steps, ensure_ascii=False),
                    trace.reflection_rounds,
                    json.dumps(trace.retrieval_rounds, ensure_ascii=False),
                    trace.total_chunks_retrieved,
                    json.dumps(trace.generation, ensure_ascii=False) if trace.generation else None,
                    json.dumps(trace.verification, ensure_ascii=False) if trace.verification else None,
                    trace.answer,
                    trace.sources_count,
                    trace.total_latency_ms,
                    trace.error,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_trace(self, trace_id: str) -> Optional[dict]:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
            if row:
                result = dict(row)
                for key in ("state_history", "planning_steps", "retrieval_rounds",
                            "generation", "verification"):
                    if result.get(key) and isinstance(result[key], str):
                        result[key] = json.loads(result[key])
                return result
            return None
        finally:
            conn.close()

    def list_traces(
        self,
        skip: int = 0,
        limit: int = 50,
        query_type: Optional[str] = None,
    ) -> list[dict]:
        conn = _get_connection()
        try:
            sql = "SELECT * FROM traces"
            params = []
            if query_type:
                sql += " WHERE query_type = ?"
                params.append(query_type)
            sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, skip])

            rows = conn.execute(sql, params).fetchall()
            traces = []
            for r in rows:
                trace = dict(r)
                for key in ("state_history", "planning_steps", "retrieval_rounds",
                            "generation", "verification"):
                    if trace.get(key) and isinstance(trace[key], str):
                        trace[key] = json.loads(trace[key])
                traces.append(trace)
            return traces
        finally:
            conn.close()

    def get_metrics(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        aggregation: str = "hour",
    ) -> dict:
        conn = _get_connection()
        try:
            row = conn.execute(
                """SELECT COUNT(*) as total,
                          SUM(CASE WHEN error IS NULL THEN 1 ELSE 0 END) as success,
                          AVG(total_latency_ms) as avg_lat,
                          AVG(reflection_rounds) as avg_ref,
                          AVG(total_chunks_retrieved) as avg_chunks
                   FROM traces"""
            ).fetchone()

            rows = conn.execute(
                "SELECT query_type, COUNT(*) as cnt FROM traces GROUP BY query_type"
            ).fetchall()
            dist = {r["query_type"]: r["cnt"] for r in rows}

            return {
                "total_queries": row["total"] or 0,
                "successful_queries": row["success"] or 0,
                "success_rate": (row["success"] or 0) / max(row["total"] or 1, 1),
                "avg_latency_ms": row["avg_lat"] or 0,
                "avg_reflection_rounds": row["avg_ref"] or 0,
                "avg_chunks_retrieved": row["avg_chunks"] or 0,
                "query_type_distribution": dist,
            }
        finally:
            conn.close()

    def get_retrieval_quality(self, collection_name: str = "default") -> dict:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT AVG(total_chunks_retrieved) as avg, COUNT(*) as total FROM traces"
            ).fetchone()
            return {
                "avg_chunks_per_query": row["avg"] or 0,
                "total_retrievals": row["total"] or 0,
                "collection": collection_name,
            }
        finally:
            conn.close()

    def get_generation_quality(self) -> dict:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT AVG(LENGTH(answer)) as avg_len, COUNT(*) as total FROM traces WHERE answer != ''"
            ).fetchone()
            return {
                "avg_answer_length": row["avg_len"] or 0,
                "total_generations": row["total"] or 0,
            }
        finally:
            conn.close()

    def get_dashboard(self) -> dict:
        return {
            "overview": self.get_metrics(),
            "query_types": self._metrics["query_types"],
            "recent_traces": self.list_traces(limit=10),
        }

    def get_total_queries(self) -> int:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT COUNT(*) FROM traces").fetchone()
            return row[0]
        finally:
            conn.close()

    def get_avg_response_time(self) -> float:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT AVG(total_latency_ms) FROM traces").fetchone()
            return row[0] or 0.0
        finally:
            conn.close()

    def get_avg_reflection_rounds(self) -> float:
        conn = _get_connection()
        try:
            row = conn.execute("SELECT AVG(reflection_rounds) FROM traces").fetchone()
            return row[0] or 0.0
        finally:
            conn.close()

    def get_success_rate(self) -> float:
        conn = _get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*), SUM(CASE WHEN error IS NULL THEN 1 ELSE 0 END) FROM traces"
            ).fetchone()
            return (row[1] or 0) / max(row[0] or 1, 1)
        finally:
            conn.close()

    def get_query_type_distribution(self) -> dict:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT query_type, COUNT(*) FROM traces GROUP BY query_type"
            ).fetchall()
            return {r[0]: r[1] for r in rows}
        finally:
            conn.close()

    def get_conversation_history(self, conversation_id: str) -> list[dict]:
        return []

    def export_traces(
        self,
        format: str = "json",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> list[dict]:
        conn = _get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM traces ORDER BY id DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_logs(
        self,
        trace_id: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        return []
