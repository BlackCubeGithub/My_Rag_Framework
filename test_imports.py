"""
Simple test script to verify the basic imports work
"""
import sys
sys.path.insert(0, '.')

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")

    modules = [
        ("backend.config", "settings"),
        ("backend.core.agent.query_analyzer", "QueryAnalyzer"),
        ("backend.core.agent.planner", "Planner"),
        ("backend.core.agent.reflector", "Reflector"),
        ("backend.core.agent.verifier", "Verifier"),
        ("backend.core.agent.orchestrator", "AgenticRAGOrchestrator"),
        ("backend.core.agent.prompts", "SYSTEM_PROMPTS"),
        ("backend.core.retrieval.base", "BaseRetriever"),
        ("backend.core.retrieval.vector_retriever", "VectorRetriever"),
        ("backend.core.retrieval.bm25_retriever", "BM25Retriever"),
        ("backend.core.retrieval.hybrid_retriever", "HybridRetriever"),
        ("backend.core.retrieval.reranker", "Reranker"),
        ("backend.core.retrieval.query_rewriter", "QueryRewriter"),
        ("backend.core.multimodal.document_parser", "DocumentParser"),
        ("backend.core.multimodal.text_chunker", "TextChunker"),
        ("backend.core.multimodal.image_processor", "ImageProcessor"),
        ("backend.core.multimodal.table_extractor", "TableExtractor"),
        ("backend.core.multimodal.layout_analyzer", "LayoutAnalyzer"),
        ("backend.core.multimodal.fusion", "MultimodalFusion"),
        ("backend.core.generation.generator", "Generator"),
        ("backend.core.generation.citation_engine", "CitationEngine"),
        ("backend.core.storage.vector_store", "VectorStoreManager"),
        ("backend.core.storage.document_store", "DocumentStore"),
        ("backend.observability.rag_trace", "RAGTracer"),
        ("backend.observability.evaluator", "RAGEvaluator"),
        ("backend.observability.metrics", "MetricsCollector"),
        ("backend.observability.tracer", "setup_tracing"),
        ("backend.observability.debug_panel", None),
        ("backend.api.deps", None),
        ("backend.api.v1.rag", None),
        ("backend.api.v1.ingest", None),
        ("backend.api.v1.query", None),
        ("backend.api.v1.eval", None),
        ("backend.api.v1.observability", None),
    ]

    passed = 0
    failed = 0

    for module_path, attr in modules:
        try:
            module = __import__(module_path, fromlist=[attr] if attr else [])
            if attr:
                getattr(module, attr)
            print(f"  {module_path}: OK")
            passed += 1
        except Exception as e:
            print(f"  {module_path}: FAIL - {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    print("Import test complete!")


if __name__ == "__main__":
    test_imports()
