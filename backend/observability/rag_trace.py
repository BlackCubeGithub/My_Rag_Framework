"""
RAG Tracer
Comprehensive tracing for RAG pipeline — full chain metadata
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

# ── Per-stage detail dataclasses ────────────────────────────────────────────────


@dataclass
class QueryAnalysisDetail:
    """Full query analysis output"""
    query_type: str
    entities: list[str]
    key_concepts: list[str]
    requires_reasoning: bool
    suggested_approach: str
    reasoning: str = ""


@dataclass
class PlanningDetail:
    """Full planning output"""
    plan_type: str
    steps: list[dict]
    final_strategy: str
    reasoning: str


@dataclass
class RetrievalChunkDetail:
    """Single chunk with all scores"""
    chunk_id: str
    text: str
    source: str
    fused_score: float = 0.0
    vector_score: float = 0.0
    bm25_score: float = 0.0
    rerank_score: float = 0.0
    rank: int = 0
    retrieval_method: str = ""


@dataclass
class RetrievalRoundDetail:
    """Detailed info for one retrieval round"""
    round_id: int
    sub_query: str
    fusion_method: str
    alpha: float = 0.5
    vector_count: int = 0
    bm25_count: int = 0
    vector_scores: list[float] = field(default_factory=list)
    bm25_scores: list[float] = field(default_factory=list)
    reranked_chunks: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0


@dataclass
class ReflectionRoundDetail:
    """Detailed info for one reflection round"""
    round_id: int
    decision: str
    confidence_score: float
    missing_aspects: list[str]
    supplementary_queries: list[str]
    reasoning: str
    additional_chunks_count: int = 0


@dataclass
class GenerationDetail:
    """Full generation metadata"""
    prompt: str = ""
    raw_response: str = ""
    final_answer: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0


@dataclass
class VerificationDetail:
    """Full verification metadata"""
    decision: str
    faithfulness_score: float
    has_hallucination: bool
    citation_accuracy: float
    issues: list[str]
    revised_answer: Optional[str] = None


@dataclass
class StageLatencies:
    """Per-stage latency breakdown"""
    analyzing_ms: float = 0.0
    planning_ms: float = 0.0
    retrieval_ms: float = 0.0
    reflecting_ms: float = 0.0
    generating_ms: float = 0.0
    verifying_ms: float = 0.0


# ── Database schema ────────────────────────────────────────────────────────────


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _init_db():
    Path("./data/traces").mkdir(parents=True, exist_ok=True)
    conn = _get_connection()
    try:
        existing = conn.execute(
            "PRAGMA table_info(traces)"
        ).fetchall()
        existing_cols = {row[1] for row in existing}

        if not existing_cols:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS traces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trace_id TEXT UNIQUE NOT NULL,
                    query TEXT NOT NULL DEFAULT '',
                    query_type TEXT NOT NULL DEFAULT 'simple',
                    timestamp TEXT NOT NULL,
                    query_analysis TEXT NOT NULL DEFAULT '{}',
                    planning TEXT NOT NULL DEFAULT '{}',
                    rewritten_queries TEXT NOT NULL DEFAULT '[]',
                    state_history TEXT NOT NULL DEFAULT '[]',
                    retrieval_rounds TEXT NOT NULL DEFAULT '[]',
                    all_chunks TEXT NOT NULL DEFAULT '[]',
                    total_chunks_retrieved INTEGER NOT NULL DEFAULT 0,
                    reflection_rounds_detail TEXT NOT NULL DEFAULT '[]',
                    reflection_rounds INTEGER NOT NULL DEFAULT 0,
                    generation TEXT,
                    verification TEXT,
                    answer TEXT NOT NULL DEFAULT '',
                    sources_count INTEGER NOT NULL DEFAULT 0,
                    stage_latencies TEXT NOT NULL DEFAULT '{}',
                    total_latency_ms REAL NOT NULL DEFAULT 0,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON traces(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_traces_query_type ON traces(query_type);
            """)
        else:
            all_cols = {
                "query_analysis": "{}",
                "planning": "{}",
                "rewritten_queries": "[]",
                "state_history": "[]",
                "all_chunks": "[]",
                "reflection_rounds_detail": "[]",
                "stage_latencies": "{}",
            }
            for col, default in all_cols.items():
                if col not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE traces ADD COLUMN {col} TEXT NOT NULL DEFAULT '{default}'")
                    except Exception:
                        pass

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
class RAGTrace:
    trace_id: str
    query: str
    query_type: str
    timestamp: str

    # query analysis
    query_analysis: dict

    # planning
    planning: dict

    # rewritten queries
    rewritten_queries: list[str]

    # state transitions
    state_history: list[dict]

    # retrieval
    retrieval_rounds: list[dict]
    all_chunks: list[dict]
    total_chunks_retrieved: int

    # reflection
    reflection_rounds_detail: list[dict]
    reflection_rounds: int

    # generation
    generation: Optional[dict]

    # verification
    verification: Optional[dict]

    answer: str
    sources_count: int

    # per-stage latency
    stage_latencies: dict

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
            query_analysis={},
            planning={},
            rewritten_queries=[],
            state_history=[],
            retrieval_rounds=[],
            all_chunks=[],
            total_chunks_retrieved=0,
            reflection_rounds_detail=[],
            reflection_rounds=0,
            generation=None,
            verification=None,
            answer="",
            sources_count=0,
            stage_latencies={},
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

        # query type
        trace.query_type = self._extract_query_type(ctx)

        # query analysis
        trace.query_analysis = self._extract_query_analysis(ctx)

        # planning
        trace.planning = self._extract_planning(ctx)

        # state transitions
        trace.state_history = [
            {
                "from": t.from_state.value if hasattr(t.from_state, "value") else str(t.from_state),
                "to": t.to_state.value if hasattr(t.to_state, "value") else str(t.to_state),
                "timestamp": t.timestamp,
            }
            for t in ctx.state_history
        ]

        # rewritten queries
        trace.rewritten_queries = getattr(ctx, "rewritten_queries", [])

        # retrieval rounds (now with full detail)
        trace.retrieval_rounds = self._extract_retrieval_rounds(ctx)

        # all chunks with scores
        trace.all_chunks = self._extract_chunks(ctx)
        trace.total_chunks_retrieved = len(ctx.all_chunks)

        # reflection rounds
        trace.reflection_rounds = ctx.reflection_rounds
        trace.reflection_rounds_detail = self._extract_reflection_rounds(ctx)

        # generation
        trace.generation = getattr(ctx, "generation_detail", None)
        if trace.generation:
            trace.answer = trace.generation.get("final_answer", ctx.generation or "")
        elif ctx.generation:
            trace.answer = ctx.generation

        # verification
        trace.verification = self._extract_verification(ctx)

        trace.sources_count = len(ctx.all_chunks)

        # per-stage latencies
        trace.stage_latencies = self._extract_stage_latencies(ctx)
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

    # ── extraction helpers ──────────────────────────────────────────────────────

    def _extract_query_type(self, ctx) -> str:
        qa = getattr(ctx, "query_analysis", None)
        if qa and hasattr(qa, "query_type"):
            return qa.query_type.value
        if isinstance(qa, dict):
            return qa.get("query_type", "simple")
        return "simple"

    def _extract_query_analysis(self, ctx) -> dict:
        qa = getattr(ctx, "query_analysis", None)
        if qa is None:
            return {}
        if hasattr(qa, "query_type"):
            return {
                "query_type": qa.query_type.value,
                "entities": list(qa.entities) if hasattr(qa, "entities") else [],
                "key_concepts": list(qa.key_concepts) if hasattr(qa, "key_concepts") else [],
                "requires_reasoning": bool(getattr(qa, "requires_reasoning", False)),
                "suggested_approach": getattr(qa, "suggested_approach", ""),
                "reasoning": getattr(qa, "reasoning", ""),
            }
        if isinstance(qa, dict):
            return qa
        return {}

    def _extract_planning(self, ctx) -> dict:
        plan = getattr(ctx, "retrieval_plan", None)
        if plan is None:
            return {}
        from backend.core.agent.planner import RetrievalPlan, PlanType
        plan_type = ""
        if hasattr(plan, "plan_type"):
            pt = plan.plan_type
            plan_type = pt.value if hasattr(pt, "value") else str(pt)
        return {
            "plan_type": plan_type,
            "steps": [
                {
                    "step_id": s.step_id,
                    "action": s.action,
                    "sub_query": s.sub_query,
                    "dependencies": list(s.dependencies) if hasattr(s, "dependencies") else [],
                    "expected_output": getattr(s, "expected_output", ""),
                }
                for s in (plan.steps if hasattr(plan, "steps") else [])
            ],
            "final_strategy": getattr(plan, "final_strategy", ""),
            "reasoning": getattr(plan, "reasoning", ""),
        }

    def _extract_retrieval_rounds(self, ctx) -> list[dict]:
        raw = getattr(ctx, "retrieval_rounds_detail", None)
        if raw:
            return raw
        return [
            {"round_id": i, "chunks_count": len(ctx.all_chunks)}
            for i in range(getattr(ctx, "retrieval_rounds", 1))
        ]

    def _extract_chunks(self, ctx) -> list[dict]:
        chunks = []
        for c in ctx.all_chunks:
            if isinstance(c, dict):
                chunks.append({
                    "chunk_id": c.get("chunk_id", ""),
                    "text": c.get("text", ""),
                    "source": c.get("metadata", {}).get("source", "") if isinstance(c.get("metadata"), dict) else "",
                    "fused_score": float(c.get("fused_score", 0)),
                    "vector_score": float(c.get("vector_score", 0)),
                    "bm25_score": float(c.get("bm25_score", 0)),
                    "rerank_score": float(c.get("rerank_score", 0)),
                    "rank": int(c.get("rank", 0)),
                    "retrieval_method": c.get("retrieval_method", ""),
                })
            else:
                chunks.append({"chunk_id": str(getattr(c, "chunk_id", ""))})
        return chunks

    def _extract_reflection_rounds(self, ctx) -> list[dict]:
        results = []
        for r in getattr(ctx, "reflection_results", []):
            dec = r.decision.value if hasattr(r.decision, "value") else str(r.decision)
            results.append({
                "round_id": len(results),
                "decision": dec,
                "confidence_score": float(r.confidence_score),
                "missing_aspects": list(r.missing_aspects) if hasattr(r, "missing_aspects") else [],
                "supplementary_queries": list(r.supplementary_queries) if hasattr(r, "supplementary_queries") else [],
                "reasoning": getattr(r, "reasoning", ""),
            })
        return results

    def _extract_verification(self, ctx) -> Optional[dict]:
        v = getattr(ctx, "verification", None)
        if v is None:
            return None
        dec = v.decision.value if hasattr(v.decision, "value") else str(v.decision)
        return {
            "decision": dec,
            "faithfulness_score": float(getattr(v, "faithfulness_score", 0)),
            "has_hallucination": bool(getattr(v, "has_hallucination", False)),
            "citation_accuracy": float(getattr(v, "citation_accuracy", 0)),
            "issues": list(getattr(v, "issues", [])),
            "revised_answer": getattr(v, "revised_answer", None),
        }

    def _extract_stage_latencies(self, ctx) -> dict:
        return getattr(ctx, "stage_latencies", {})

    # ── persistence ───────────────────────────────────────────────────────────

    def _save_trace(self, trace: RAGTrace):
        conn = _get_connection()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO traces
                   (trace_id, query, query_type, timestamp, query_analysis, planning,
                    rewritten_queries, state_history, retrieval_rounds, all_chunks,
                    total_chunks_retrieved, reflection_rounds_detail, reflection_rounds,
                    generation, verification, answer, sources_count, stage_latencies,
                    total_latency_ms, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trace.trace_id,
                    trace.query,
                    trace.query_type,
                    trace.timestamp,
                    json.dumps(trace.query_analysis, ensure_ascii=False),
                    json.dumps(trace.planning, ensure_ascii=False),
                    json.dumps(trace.rewritten_queries, ensure_ascii=False),
                    json.dumps(trace.state_history, ensure_ascii=False),
                    json.dumps(trace.retrieval_rounds, ensure_ascii=False),
                    json.dumps(trace.all_chunks, ensure_ascii=False),
                    trace.total_chunks_retrieved,
                    json.dumps(trace.reflection_rounds_detail, ensure_ascii=False),
                    trace.reflection_rounds,
                    json.dumps(trace.generation, ensure_ascii=False) if trace.generation else None,
                    json.dumps(trace.verification, ensure_ascii=False) if trace.verification else None,
                    trace.answer,
                    trace.sources_count,
                    json.dumps(trace.stage_latencies, ensure_ascii=False),
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
                return self._row_to_trace(row)
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
            return [self._row_to_trace(r) for r in rows]
        finally:
            conn.close()

    def _row_to_trace(self, row: sqlite3.Row) -> dict:
        trace = dict(row)
        for key in (
            "query_analysis", "planning", "rewritten_queries",
            "state_history", "retrieval_rounds", "all_chunks",
            "reflection_rounds_detail", "generation", "verification",
            "stage_latencies",
        ):
            val = trace.get(key)
            if val and isinstance(val, str):
                trace[key] = json.loads(val)
        return trace

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
            return [self._row_to_trace(r) for r in rows]
        finally:
            conn.close()

    def get_logs(
        self,
        trace_id: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        return []
