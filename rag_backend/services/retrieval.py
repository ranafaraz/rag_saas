"""
Qdrant vector retrieval with strict tenant_id + role-based metadata filtering.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import List

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
COLLECTION_NAME = "rag_chunks"
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
EMBEDDING_CACHE_TTL_SECONDS = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", 1800))

# Module-level singletons — created once, reused across requests
_qdrant_client = None
_embeddings = None
_redis_client = None


def _get_qdrant_client():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=10)
    return _qdrant_client


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        from services.embeddings import get_embeddings
        _embeddings = get_embeddings()
    return _embeddings


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            _redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        except Exception:
            pass
    return _redis_client


def _get_cached_embedding(query_normalized: str) -> list | None:
    r = _get_redis()
    if not r:
        return None
    try:
        key = f"emb:{hashlib.sha256(query_normalized.encode()).hexdigest()}"
        cached = r.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    return None


def _cache_embedding(query_normalized: str, vector: list) -> None:
    r = _get_redis()
    if not r:
        return
    try:
        key = f"emb:{hashlib.sha256(query_normalized.encode()).hexdigest()}"
        r.set(key, json.dumps(vector), ex=EMBEDDING_CACHE_TTL_SECONDS)
    except Exception:
        pass


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _recency_score(metadata: dict) -> float:
    now = datetime.now(timezone.utc)
    date_value = metadata.get("effective_at") or metadata.get("ingested_at")
    parsed = _parse_datetime(date_value)
    if not parsed:
        return 0.5
    age_days = max((now - parsed).days, 0)
    if age_days <= 30:
        return 1.0
    if age_days <= 180:
        return 0.8
    if age_days <= 365:
        return 0.6
    return 0.4


def _trust_score(metadata: dict) -> float:
    return float(metadata.get("source_trust") or 0.7)


def _rerank_chunks(chunks: list) -> list:
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        semantic = float(chunk.get("score") or 0.0)
        recency = _recency_score(metadata)
        trust = _trust_score(metadata)
        combined = (semantic * 0.65) + (recency * 0.25) + (trust * 0.10)
        chunk["score"] = combined
        chunk["semantic_score"] = semantic
        chunk["recency_score"] = recency
        chunk["trust_score"] = trust
    chunks.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
    return chunks


def retrieve_chunks(query: str, tenant_id: str, roles: List[str], top_k: int = 5) -> list:
    """
    Embeds the query using the configured embedding gateway and searches Qdrant,
    enforcing: tenant_id == tenant_id AND roles ∩ roles != ∅
    Returns list of dicts: {content, score, metadata}
    """
    try:
        from qdrant_client.http import models as qmodels

        query_normalized = query.lower().strip()
        query_vector = _get_cached_embedding(query_normalized)
        if query_vector is None:
            query_vector = _get_embeddings().embed_query(query)
            _cache_embedding(query_normalized, query_vector)

        client = _get_qdrant_client()

        # Strict multi-tenant + role filter
        search_filter = qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="metadata.tenant_id",
                    match=qmodels.MatchValue(value=tenant_id),
                ),
                qmodels.FieldCondition(
                    key="metadata.roles",
                    match=qmodels.MatchAny(any=roles),
                ),
            ]
        )

        if hasattr(client, "search"):
            results = client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=max(top_k * 3, top_k),
                with_payload=True,
            )
        else:
            response = client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=search_filter,
                limit=max(top_k * 3, top_k),
                with_payload=True,
            )
            results = getattr(response, "points", response)

        chunks = []
        for hit in results:
            payload = hit.payload or {}
            chunks.append({
                "content": payload.get("page_content", ""),
                "score": getattr(hit, "score", None),
                "metadata": payload.get("metadata", {}),
            })
        reranked = _rerank_chunks(chunks)
        return reranked[:top_k]

    except Exception as e:
        print(f"[RETRIEVAL] Error: {e}")
        return []
