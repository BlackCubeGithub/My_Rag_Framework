"""
Agentic RAG Orchestrator
Main agent with state machine for RAG pipeline orchestration
"""
import time
import uuid
import structlog
from typing import Optional, Any
from enum import Enum
from dataclasses import dataclass, field
import asyncio

from backend.core.agent.query_analyzer import QueryAnalyzer, QueryType
from backend.core.agent.planner import Planner, RetrievalPlan, PlanType
from backend.core.agent.reflector import Reflector, ReflectionResult, ReflectionDecision
from backend.core.agent.verifier import Verifier, VerificationResult, VerificationDecision
from backend.core.agent.prompts import build_generation_prompt, build_citation_prompt
from backend.core.generation.generator import Generator
from backend.core.generation.citation_engine import CitationEngine
from backend.core.retrieval.hybrid_retriever import HybridRetriever
from backend.core.retrieval.reranker import Reranker
from backend.core.retrieval.query_rewriter import QueryRewriter
from backend.observability.rag_trace import RAGTracer

logger = structlog.get_logger()


class AgentState(str, Enum):
    """Agent state machine states"""
    IDLE = "idle"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    RETRIEVING = "retrieving"
    REFLECTING = "reflecting"
    GENERATING = "generating"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StateTransition:
    """Record of state transitions"""
    from_state: AgentState
    to_state: AgentState
    timestamp: float
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentContext:
    """Context maintained throughout agent execution"""
    trace_id: str
    query: str
    conversation_id: Optional[str] = None

    state: AgentState = AgentState.IDLE
    state_history: list[StateTransition] = field(default_factory=list)

    query_analysis: Optional[Any] = None
    retrieval_plan: Optional[RetrievalPlan] = None
    rewritten_queries: list[str] = field(default_factory=list)
    all_chunks: list[dict] = field(default_factory=list)
    reflection_results: list[ReflectionResult] = field(default_factory=list)
    generation: Optional[str] = None
    generation_detail: Optional[dict] = None
    verification: Optional[VerificationResult] = None

    reflection_rounds: int = 0
    retrieval_rounds: int = 0
    retrieval_rounds_detail: list[dict] = field(default_factory=list)

    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    stage_latencies: dict = field(default_factory=dict)

    error: Optional[str] = None


from typing import Any


class AgenticRAGOrchestrator:
    """
    Main orchestrator for Agentic RAG pipeline.

    Implements a state machine that coordinates:
    - Query Analysis
    - Retrieval Planning
    - Hybrid Retrieval
    - Reflection & Refinement
    - Generation
    - Verification
    """

    def __init__(
        self,
        generator: Generator,
        hybrid_retriever: HybridRetriever,
        reranker: Reranker,
        query_rewriter: QueryRewriter,
        tracer: RAGTracer,
        max_reflection_rounds: int = 3,
        reflection_threshold: float = 0.7,
        verification_threshold: float = 0.8,
    ):
        self.generator = generator
        self.hybrid_retriever = hybrid_retriever
        self.reranker = reranker
        self.query_rewriter = query_rewriter
        self.tracer = tracer
        self.max_reflection_rounds = max_reflection_rounds
        self.reflection_threshold = reflection_threshold
        self.verification_threshold = verification_threshold

        self.query_analyzer = QueryAnalyzer(generator)
        self.planner = Planner(generator)
        self.reflector = Reflector(generator)
        self.verifier = Verifier(generator)
        self.citation_engine = CitationEngine()

    async def query(
        self,
        query: str,
        trace_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        enable_reflection: bool = True,
        enable_verification: bool = True,
        top_k: int = 10,
    ) -> dict:
        """
        Main query interface for Agentic RAG.

        Args:
            query: User query
            trace_id: Optional trace ID for observability
            conversation_id: Conversation ID for context
            enable_reflection: Enable reflection/refinement
            enable_verification: Enable answer verification
            top_k: Number of chunks to retrieve

        Returns:
            Dictionary with answer, sources, and metadata
        """
        trace_id = trace_id or str(uuid.uuid4())
        start_time = time.time()

        logger.info("agentic_rag_started", trace_id=trace_id, query=query[:100])

        ctx = AgentContext(
            trace_id=trace_id,
            query=query,
            conversation_id=conversation_id,
            start_time=start_time,
        )

        try:
            self._transition_state(ctx, AgentState.ANALYZING)
            t0 = time.time()
            analysis = await self.query_analyzer.analyze(query)
            ctx.query_analysis = analysis
            ctx.stage_latencies["analyzing_ms"] = (time.time() - t0) * 1000

            self._transition_state(ctx, AgentState.PLANNING)
            t0 = time.time()
            plan = await self.planner.create_plan(
                query=query,
                query_type=analysis.query_type.value,
            )
            ctx.retrieval_plan = plan
            ctx.stage_latencies["planning_ms"] = (time.time() - t0) * 1000

            self._transition_state(ctx, AgentState.RETRIEVING)
            t0 = time.time()
            chunks = await self._execute_retrieval(ctx, query, top_k)
            ctx.all_chunks = chunks
            ctx.retrieval_rounds = 1
            ctx.stage_latencies["retrieval_ms"] = (time.time() - t0) * 1000

            if enable_reflection:
                t0 = time.time()
                await self._run_reflection_loop(ctx, top_k)
                ctx.stage_latencies["reflecting_ms"] = (time.time() - t0) * 1000

            self._transition_state(ctx, AgentState.GENERATING)
            t0 = time.time()
            answer = await self._generate_answer(ctx)
            ctx.stage_latencies["generating_ms"] = (time.time() - t0) * 1000

            if enable_verification:
                self._transition_state(ctx, AgentState.VERIFYING)
                t0 = time.time()
                verification = await self.verifier.verify(
                    query=query,
                    answer=answer,
                    retrieved_chunks=ctx.all_chunks,
                    threshold=self.verification_threshold,
                )
                ctx.verification = verification
                ctx.stage_latencies["verifying_ms"] = (time.time() - t0) * 1000

                if verification.decision == VerificationDecision.REGENERATE:
                    logger.info("verification_failed_regenerating")
                    t0 = time.time()
                    answer = await self._generate_answer(ctx, force_regenerate=True)
                    ctx.stage_latencies["generating_ms"] = (
                        ctx.stage_latencies.get("generating_ms", 0) + (time.time() - t0) * 1000
                    )

            ctx.generation = answer

            self._transition_state(ctx, AgentState.COMPLETED)
            ctx.end_time = time.time()

            result = self._build_response(ctx)

            self.tracer.record_trace(ctx)

            logger.info(
                "agentic_rag_completed",
                trace_id=trace_id,
                rounds=ctx.reflection_rounds,
                chunks=len(ctx.all_chunks),
                latency_ms=(ctx.end_time - start_time) * 1000,
            )

            return result

        except Exception as e:
            logger.error("agentic_rag_failed", error=str(e), trace_id=trace_id)
            self._transition_state(ctx, AgentState.FAILED)
            ctx.error = str(e)
            raise

    async def _execute_retrieval(
        self,
        ctx: AgentContext,
        query: str,
        top_k: int,
    ) -> list[dict]:
        """Execute retrieval based on plan"""
        plan = ctx.retrieval_plan

        if plan and plan.plan_type == PlanType.DECOMPOSE:
            return await self._multi_hop_retrieval(ctx, query, top_k)

        return await self._single_retrieval(ctx, query, top_k)

    async def _single_retrieval(
        self,
        ctx: AgentContext,
        query: str,
        top_k: int,
    ) -> list[dict]:
        """Single query retrieval with reranking"""
        import time

        t0 = time.time()
        rewritten_queries = await self.query_rewriter.rewrite_for_retrieval(query, top_k_expansions=2)
        rewrite_latency = (time.time() - t0) * 1000
        ctx.rewritten_queries = rewritten_queries

        all_chunks = []
        seen_ids = set()
        round_detail = {
            "round_id": 0,
            "sub_query": query,
            "rewritten_queries": rewritten_queries,
            "fusion_method": "hybrid_rrf",
            "alpha": self.hybrid_retriever.alpha,
            "rewrite_latency_ms": rewrite_latency,
            "chunks_before_rerank": 0,
            "vector_count": 0,
            "bm25_count": 0,
            "vector_scores": [],
            "bm25_scores": [],
            "reranked_chunks": [],
            "latency_ms": 0.0,
        }

        for q in rewritten_queries:
            chunks = await self.hybrid_retriever.search(q, top_k=top_k)
            round_detail["chunks_before_rerank"] += len(chunks)
            round_detail["vector_count"] += sum(1 for c in chunks if c.get("vector_score", 0) > 0)
            round_detail["bm25_count"] += sum(1 for c in chunks if c.get("bm25_score", 0) > 0)
            round_detail["vector_scores"].extend([float(c.get("vector_score", 0)) for c in chunks])
            round_detail["bm25_scores"].extend([float(c.get("bm25_score", 0)) for c in chunks])
            for chunk in chunks:
                if chunk.get("chunk_id") not in seen_ids:
                    all_chunks.append(chunk)
                    seen_ids.add(chunk.get("chunk_id"))

        if all_chunks:
            round_detail["latency_ms"] = (time.time() - t0) * 1000
            reranked = await self.reranker.rerank(query, all_chunks, top_k=top_k)
            round_detail["reranked_chunks"] = [
                {
                    "chunk_id": c.get("chunk_id", ""),
                    "rerank_score": float(c.get("rerank_score", 0)),
                    "rank": i + 1,
                }
                for i, c in enumerate(reranked[:top_k])
            ]
            ctx.retrieval_rounds_detail.append(round_detail)
            return reranked

        ctx.retrieval_rounds_detail.append(round_detail)
        return all_chunks[:top_k]

    async def _multi_hop_retrieval(
        self,
        ctx: AgentContext,
        query: str,
        top_k: int,
    ) -> list[dict]:
        """Multi-hop retrieval for complex queries"""
        import time

        plan = ctx.retrieval_plan
        all_chunks = []
        seen_ids = set()
        round_id = 0

        for step in plan.steps:
            sub_query = step.sub_query
            t0 = time.time()

            chunks = await self.hybrid_retriever.search(sub_query, top_k=top_k)
            reranked = await self.reranker.rerank(sub_query, chunks, top_k=5)

            round_detail = {
                "round_id": round_id,
                "sub_query": sub_query,
                "planning_step_id": step.step_id,
                "fusion_method": "hybrid_rrf",
                "alpha": self.hybrid_retriever.alpha,
                "chunks_before_rerank": len(chunks),
                "chunks_after_rerank": len(reranked),
                "vector_count": sum(1 for c in chunks if c.get("vector_score", 0) > 0),
                "bm25_count": sum(1 for c in chunks if c.get("bm25_score", 0) > 0),
                "vector_scores": [float(c.get("vector_score", 0)) for c in chunks],
                "bm25_scores": [float(c.get("bm25_score", 0)) for c in chunks],
                "reranked_chunks": [
                    {"chunk_id": c.get("chunk_id", ""), "rerank_score": float(c.get("rerank_score", 0)), "rank": i + 1}
                    for i, c in enumerate(reranked)
                ],
                "latency_ms": (time.time() - t0) * 1000,
            }
            ctx.retrieval_rounds_detail.append(round_detail)

            all_chunks.extend(reranked)
            ctx.retrieval_rounds += 1
            round_id += 1

        seen_ids = set()
        unique_chunks = []
        for chunk in all_chunks:
            if chunk.get("chunk_id") not in seen_ids:
                seen_ids.add(chunk.get("chunk_id"))
                unique_chunks.append(chunk)

        final_reranked = await self.reranker.rerank(query, unique_chunks, top_k=top_k)
        return final_reranked

    async def _run_reflection_loop(
        self,
        ctx: AgentContext,
        top_k: int,
    ) -> None:
        """Run reflection loop to refine retrieval"""
        while ctx.reflection_rounds < self.max_reflection_rounds:
            self._transition_state(ctx, AgentState.REFLECTING)

            reflection = await self.reflector.reflect(
                query=ctx.query,
                retrieved_chunks=ctx.all_chunks,
                query_type=ctx.query_analysis.query_type.value if ctx.query_analysis else "simple",
            )

            ctx.reflection_results.append(reflection)

            round_detail = {
                "round_id": ctx.reflection_rounds,
                "decision": reflection.decision.value,
                "confidence_score": reflection.confidence_score,
                "missing_aspects": list(reflection.missing_aspects),
                "supplementary_queries": list(reflection.supplementary_queries),
                "reasoning": reflection.reasoning,
                "additional_chunks_count": 0,
            }

            if reflection.decision == ReflectionDecision.PROCEED:
                if reflection.confidence_score >= self.reflection_threshold:
                    logger.info(
                        "reflection_proceed",
                        confidence=reflection.confidence_score,
                    )
                    break

            elif reflection.decision == ReflectionDecision.REFINE:
                ctx.reflection_rounds += 1

                supplementary_chunks = []
                for sq in reflection.supplementary_queries:
                    chunks = await self.hybrid_retriever.search(sq, top_k=top_k)
                    supplementary_chunks.extend(chunks)

                if supplementary_chunks:
                    ctx.all_chunks.extend(supplementary_chunks)
                    ctx.retrieval_rounds += 1
                    round_detail["additional_chunks_count"] = len(supplementary_chunks)

                    seen_ids = set()
                    unique_chunks = []
                    for chunk in ctx.all_chunks:
                        if chunk.get("chunk_id") not in seen_ids:
                            seen_ids.add(chunk.get("chunk_id"))
                            unique_chunks.append(chunk)

                    ctx.all_chunks = await self.reranker.rerank(
                        ctx.query, unique_chunks, top_k=top_k
                    )

            elif reflection.decision == ReflectionDecision.INSUFFICIENT:
                ctx.reflection_rounds += 1
                chunks = await self.hybrid_retriever.search(ctx.query, top_k=top_k * 2)
                ctx.all_chunks.extend(chunks)
                round_detail["additional_chunks_count"] = len(chunks)

            else:
                break

        logger.info(
            "reflection_loop_completed",
            rounds=ctx.reflection_rounds,
            total_chunks=len(ctx.all_chunks),
        )

    async def _generate_answer(
        self,
        ctx: AgentContext,
        force_regenerate: bool = False,
    ) -> str:
        """Generate final answer from retrieved chunks"""
        context = self._build_context(ctx.all_chunks)

        prompt = build_generation_prompt(
            query=ctx.query,
            context=context,
            conversation_history=None,
            include_citations=True,
        )

        import time
        start_time = time.time()
        raw_response = await self.generator.generate(prompt, system_prompt=None)
        gen_latency_ms = (time.time() - start_time) * 1000

        try:
            token_count = getattr(self.generator, "_last_usage", None)
            if token_count and hasattr(token_count, "total_tokens"):
                pt = token_count.prompt_tokens
                ct = token_count.completion_tokens
                tt = token_count.total_tokens
            else:
                pt = ct = tt = 0
        except Exception:
            pt = ct = tt = 0

        answer = raw_response

        if ctx.all_chunks:
            answer = self.citation_engine.add_inline_citations(answer, ctx.all_chunks)

        ctx.generation_detail = {
            "prompt": prompt,
            "raw_response": raw_response,
            "final_answer": answer,
            "model": self.generator.model,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": tt,
            "latency_ms": gen_latency_ms,
        }

        return answer

    def _build_context(self, chunks: list[dict], max_chars: int = 8000) -> str:
        """Build context string from chunks"""
        context_parts = []
        total_chars = 0

        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "")
            source = chunk.get("metadata", {}).get("source", "未知来源")

            chunk_text = f"[来源{i}]\n{text}\n(来源: {source})\n"
            if total_chars + len(chunk_text) <= max_chars:
                context_parts.append(chunk_text)
                total_chars += len(chunk_text)
            else:
                break

        return "\n".join(context_parts)

    def _transition_state(self, ctx: AgentContext, new_state: AgentState) -> None:
        """Record state transition"""
        transition = StateTransition(
            from_state=ctx.state,
            to_state=new_state,
            timestamp=time.time(),
        )

        ctx.state_history.append(transition)
        ctx.state = new_state

        logger.debug(
            "state_transition",
            trace_id=ctx.trace_id,
            from_state=transition.from_state.value,
            to_state=transition.to_state.value,
        )

    def _build_response(self, ctx: AgentContext) -> dict:
        """Build final response dictionary"""
        sources = self.citation_engine.format_source_list(ctx.all_chunks)

        return {
            "answer": ctx.generation or "",
            "sources": sources,
            "trace_id": ctx.trace_id,
            "query_type": ctx.query_analysis.query_type.value if ctx.query_analysis else "unknown",
            "retrieval_rounds": ctx.retrieval_rounds,
            "reflection_rounds": ctx.reflection_rounds,
            "generation_latency_ms": 0,
            "total_latency_ms": (ctx.end_time - ctx.start_time) * 1000 if ctx.end_time else 0,
        }
