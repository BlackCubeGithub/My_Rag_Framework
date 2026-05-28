"""
Migrate RAG traces from old JSON files to SQLite.
Safe to run multiple times — uses INSERT OR REPLACE.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.observability.rag_trace import RAGTracer, _init_db

def migrate():
    traces_dir = Path("data/traces")
    index_file = traces_dir / "index.json"

    if not index_file.exists() and not list(traces_dir.glob("*.json")):
        print("No JSON traces found, nothing to migrate.")
        return

    _init_db()

    trace_files = list(traces_dir.glob("*.json"))
    trace_files = [f for f in trace_files if f.name != "index.json"]

    if not trace_files:
        print("No trace .json files found.")
        return

    print(f"Found {len(trace_files)} JSON trace files. Migrating...")

    tracer = RAGTracer()
    migrated = 0
    failed = 0

    for tf in trace_files:
        try:
            with open(tf, "r", encoding="utf-8") as f:
                data = json.load(f)

            from backend.observability.rag_trace import RAGTrace
            trace = RAGTrace(
                trace_id=data["trace_id"],
                query=data.get("query", ""),
                query_type=data.get("query_type", "simple"),
                timestamp=data.get("timestamp", ""),
                state_history=data.get("state_history", []),
                planning_steps=data.get("planning_steps", []),
                reflection_rounds=data.get("reflection_rounds", 0),
                retrieval_rounds=data.get("retrieval_rounds", []),
                total_chunks_retrieved=data.get("total_chunks_retrieved", 0),
                generation=data.get("generation"),
                verification=data.get("verification"),
                answer=data.get("answer", ""),
                sources_count=data.get("sources_count", 0),
                total_latency_ms=data.get("total_latency_ms", 0),
                error=data.get("error"),
            )
            tracer._save_trace(trace)
            migrated += 1
        except Exception as e:
            failed += 1
            print(f"  FAIL {tf.name}: {e}")

    print(f"\nMigration done: {migrated} migrated, {failed} failed.")
    print("You can now safely delete data/traces/*.json (except index.json if needed)")

if __name__ == "__main__":
    migrate()
