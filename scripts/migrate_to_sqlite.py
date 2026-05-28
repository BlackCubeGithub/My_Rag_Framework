"""
Migrate documents from old JSON index to SQLite.
Safe to run multiple times — uses INSERT OR REPLACE.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from backend.core.storage.document_store import DocumentStore, _init_db

def migrate():
    index_path = Path("data/documents/index.json")
    if not index_path.exists():
        print("No index.json found, nothing to migrate.")
        return

    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    docs = data.get("documents", {})
    if not docs:
        print("No documents in index.json to migrate.")
        return

    print(f"Found {len(docs)} documents in index.json. Migrating...")

    store = DocumentStore()
    migrated = 0
    skipped = 0

    for doc_id, doc_data in docs.items():
        try:
            chunks = doc_data.get("chunks", [])
            store.store_document(
                document_id=doc_data["document_id"],
                file_name=doc_data["file_name"],
                chunks=chunks,
                metadata=doc_data.get("metadata", {}),
            )
            migrated += 1
            print(f"  OK  {doc_data['file_name']} ({len(chunks)} chunks)")
        except Exception as e:
            skipped += 1
            print(f"  FAIL {doc_data.get('file_name', doc_id)}: {e}")

    print(f"\nMigration done: {migrated} migrated, {skipped} skipped.")
    print("You can now safely delete data/documents/index.json")

if __name__ == "__main__":
    migrate()
