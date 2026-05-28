"""
Evaluator
End-to-end evaluation for RAG pipeline
"""
import structlog
from typing import Optional
from dataclasses import dataclass

logger = structlog.get_logger()


@dataclass
class RetrievalMetrics:
    """Retrieval evaluation metrics"""
    recall: float
    precision: float
    f1: float
    hit_rate: float
    mrr: float


@dataclass
class GenerationMetrics:
    """Generation evaluation metrics"""
    faithfulness: float
    relevance: float
    coherence: float


@dataclass
class EvaluationResult:
    """Complete evaluation result"""
    retrieval: RetrievalMetrics
    generation: GenerationMetrics
    overall_score: float


class RAGEvaluator:
    """
    Evaluates RAG pipeline performance.

    Metrics:
    - Retrieval: Recall, Precision, F1, Hit Rate, MRR
    - Generation: Faithfulness, Relevance, Coherence
    """

    def __init__(self):
        self.logger = logger

    def evaluate_single(
        self,
        query: str,
        answer: str,
        ground_truth: str,
        retrieved_chunks: list[dict],
    ) -> dict:
        """
        Evaluate a single RAG query.

        Args:
            query: User query
            answer: Generated answer
            ground_truth: Expected answer
            retrieved_chunks: Retrieved chunks

        Returns:
            Dictionary with all metrics
        """
        logger.info("evaluating_single", query=query[:100])

        retrieval_metrics = self._evaluate_retrieval(retrieved_chunks, ground_truth)
        generation_metrics = self._evaluate_generation(
            query, answer, ground_truth, retrieved_chunks
        )

        overall = (
            retrieval_metrics["f1"] * 0.4 +
            generation_metrics["faithfulness"] * 0.6
        )

        return {
            "retrieval": retrieval_metrics,
            "generation": generation_metrics,
            "overall": overall,
        }

    def _evaluate_retrieval(
        self,
        chunks: list[dict],
        ground_truth: str,
    ) -> dict:
        """Evaluate retrieval quality"""
        if not chunks:
            return {
                "recall": 0.0,
                "precision": 0.0,
                "f1": 0.0,
                "hit_rate": 0.0,
                "mrr": 0.0,
            }

        gt_keywords = set(ground_truth.lower().split())
        retrieved_texts = " ".join([c.get("text", "").lower() for c in chunks])

        relevant = 0
        for keyword in gt_keywords:
            if len(keyword) > 2 and keyword in retrieved_texts:
                relevant += 1

        recall = relevant / max(len(gt_keywords), 1)
        precision = min(recall * 1.5, 1.0)
        f1 = 2 * precision * recall / max(precision + recall, 0.001)

        hit_rate = 1.0 if relevant > 0 else 0.0

        mrr = 0.0
        for i, chunk in enumerate(chunks, 1):
            chunk_text = chunk.get("text", "").lower()
            chunk_relevant = sum(1 for k in gt_keywords if len(k) > 2 and k in chunk_text)
            if chunk_relevant > 0:
                mrr = 1.0 / i
                break

        return {
            "recall": round(recall, 4),
            "precision": round(precision, 4),
            "f1": round(f1, 4),
            "hit_rate": round(hit_rate, 4),
            "mrr": round(mrr, 4),
        }

    def _evaluate_generation(
        self,
        query: str,
        answer: str,
        ground_truth: str,
        chunks: list[dict],
    ) -> dict:
        """Evaluate generation quality"""
        chunk_texts = " ".join([c.get("text", "").lower() for c in chunks])
        answer_lower = answer.lower()

        answer_words = set(answer_lower.split())
        chunk_words = set(chunk_texts.split())

        overlap = len(answer_words & chunk_words)
        faithfulness = overlap / max(len(answer_words), 1)

        query_words = set(query.lower().split())
        answer_query_overlap = len(answer_words & query_words)
        relevance = answer_query_overlap / max(len(answer_words), 1)

        coherence = 1.0 if len(answer) > 20 else 0.5

        return {
            "faithfulness": round(faithfulness, 4),
            "relevance": round(relevance, 4),
            "coherence": round(coherence, 4),
        }

    async def evaluate_batch(
        self,
        test_cases: list[dict],
    ) -> dict:
        """
        Evaluate multiple test cases.

        Args:
            test_cases: List of {query, answer, ground_truth, retrieved_chunks}

        Returns:
            Aggregated metrics
        """
        results = []

        for case in test_cases:
            result = self.evaluate_single(
                query=case["query"],
                answer=case.get("answer", ""),
                ground_truth=case["ground_truth"],
                retrieved_chunks=case.get("retrieved_chunks", []),
            )
            results.append(result)

        avg_retrieval = {
            "recall": sum(r["retrieval"]["recall"] for r in results) / len(results),
            "precision": sum(r["retrieval"]["precision"] for r in results) / len(results),
            "f1": sum(r["retrieval"]["f1"] for r in results) / len(results),
            "hit_rate": sum(r["retrieval"]["hit_rate"] for r in results) / len(results),
            "mrr": sum(r["retrieval"]["mrr"] for r in results) / len(results),
        }

        avg_generation = {
            "faithfulness": sum(r["generation"]["faithfulness"] for r in results) / len(results),
            "relevance": sum(r["generation"]["relevance"] for r in results) / len(results),
            "coherence": sum(r["generation"]["coherence"] for r in results) / len(results),
        }

        avg_overall = sum(r["overall"] for r in results) / len(results)

        return {
            "retrieval": {k: round(v, 4) for k, v in avg_retrieval.items()},
            "generation": {k: round(v, 4) for k, v in avg_generation.items()},
            "overall": round(avg_overall, 4),
            "test_count": len(results),
        }
