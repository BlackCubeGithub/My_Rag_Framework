"""
Model Download Scripts
Download and cache required models from ModelScope (魔塔社区) for offline use.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def download_embedding_model():
    """Download BGE embedding model for vector retrieval."""
    print("Downloading BGE embedding model...")

    from sentence_transformers import SentenceTransformer

    model_name = "BAAI/bge-large-zh-v1.5"
    save_path = "./models/bge-large-zh-v1.5"

    if Path(save_path).exists():
        print(f"Embedding model already exists at: {save_path}")
        return save_path

    model = SentenceTransformer(model_name)
    os.makedirs(save_path, exist_ok=True)
    model.save(save_path)
    print(f"Embedding model saved to: {save_path}")
    return save_path


def download_reranker_model():
    """Download BGE reranker model for cross-encoder reranking."""
    print("Downloading BGE reranker model...")

    from sentence_transformers import CrossEncoder

    model_name = "BAAI/bge-reranker-large"
    save_path = "./models/bge-reranker-large"

    if Path(save_path).exists():
        print(f"Reranker model already exists at: {save_path}")
        return save_path

    model = CrossEncoder(model_name, max_length=512)
    os.makedirs(save_path, exist_ok=True)
    model.save(save_path)
    print(f"Reranker model saved to: {save_path}")
    return save_path


def download_all_models():
    """Download all required models."""
    print("=" * 50)
    print("Downloading all models for My RAG Framework")
    print("Source: HuggingFace Mirror (hf-mirror.com)")
    print("=" * 50)

    models_dir = Path("./models")
    models_dir.mkdir(exist_ok=True)

    try:
        download_embedding_model()
    except Exception as e:
        print(f"Failed to download embedding model: {e}")

    try:
        download_reranker_model()
    except Exception as e:
        print(f"Failed to download reranker model: {e}")
        print("Will use mock reranking if unavailable")

    print("=" * 50)
    print("Model download complete!")
    print("Models are cached in ./models/ directory")
    print("=" * 50)


if __name__ == "__main__":
    download_all_models()
