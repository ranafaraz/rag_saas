import os
from typing import Iterable

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama").lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768" if EMBEDDING_PROVIDER == "ollama" else "1024"))

_embedding_client = None


class BGEEmbeddings:
    """LangChain-compatible wrapper around FlagEmbedding for open-source production embeddings."""

    def __init__(self, model_name: str):
        from FlagEmbedding import BGEM3FlagModel

        self.model = BGEM3FlagModel(model_name, use_fp16=os.getenv("BGE_USE_FP16", "true").lower() == "true")

    def _encode(self, values: Iterable[str]) -> list[list[float]]:
        encoded = self.model.encode(list(values), batch_size=int(os.getenv("BGE_BATCH_SIZE", "12")), max_length=8192)
        dense = encoded["dense_vecs"]
        if hasattr(dense, "tolist"):
            return dense.tolist()
        return [vector.tolist() if hasattr(vector, "tolist") else list(vector) for vector in dense]

    def embed_query(self, text: str) -> list[float]:
        return self._encode([text])[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode(texts)


def get_embedding_dimension() -> int:
    return EMBEDDING_DIMENSION


def get_embeddings():
    global _embedding_client
    if _embedding_client is not None:
        return _embedding_client

    if EMBEDDING_PROVIDER in {"bge-m3", "bge", "flagembedding"}:
        _embedding_client = BGEEmbeddings(EMBEDDING_MODEL)
        return _embedding_client

    from langchain_community.embeddings import OllamaEmbeddings

    _embedding_client = OllamaEmbeddings(
        model=OLLAMA_EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    return _embedding_client
