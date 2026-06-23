"""
MongoDB audit logger with async-safe motor client and log retrieval.
"""
import asyncio
import datetime
import os

MONGO_HOST = os.getenv("MONGO_HOST", "localhost")
MONGO_PORT = int(os.getenv("MONGO_PORT", 27017))
MONGO_USER = os.getenv("MONGO_USER", "admin")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "admin123")
MONGO_DB = os.getenv("MONGO_DB", "rag_audit_log")

_mongo_client = None


def _get_collection():
    global _mongo_client
    if _mongo_client is None:
        from pymongo import MongoClient
        _mongo_client = MongoClient(
            host=MONGO_HOST,
            port=MONGO_PORT,
            username=MONGO_USER,
            password=MONGO_PASSWORD,
            serverSelectionTimeoutMS=2000,
        )
    return _mongo_client[MONGO_DB]["logs"]


def log_request(
    tenant_id: str,
    roles: list,
    query: str,
    response_metadata: dict,
    latency: float,
    status: str,
):
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "tenant_id": tenant_id,
        "roles": roles,
        "query": query,
        "response_metadata": response_metadata,
        "latency_seconds": latency,
        "status": status,
    }
    try:
        _get_collection().insert_one(entry)
    except Exception as e:
        # Audit failures must NEVER crash the main request
        print(f"[AUDIT] Failed to write log: {e}")


async def log_request_async(
    tenant_id: str,
    roles: list,
    query: str,
    response_metadata: dict,
    latency: float,
    status: str,
) -> None:
    """Fire-and-forget audit log write — runs the sync log_request in a thread executor."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        log_request,
        tenant_id,
        roles,
        query,
        response_metadata,
        latency,
        status,
    )


def fetch_recent_logs(tenant_id: str, limit: int = 50) -> list:
    try:
        col = _get_collection()
        cursor = (
            col.find(
                {"tenant_id": tenant_id},
                {"_id": 0},  # exclude Mongo ObjectId
            )
            .sort("timestamp", -1)
            .limit(limit)
        )
        return list(cursor)
    except Exception as e:
        print(f"[AUDIT] Failed to fetch logs: {e}")
        return []
