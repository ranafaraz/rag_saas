"""
Authentication dependency for FastAPI.

Validates Bearer tokens (API keys) by calling the Django Core API's
/api/auth/verify/ endpoint. Results are cached in Redis for 5 minutes
to avoid hammering Django on every request.
"""
import os
import json
import hashlib
import httpx
import redis as redis_client
from fastapi import HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Security

security = HTTPBearer()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CORE_API_URL = os.getenv("CORE_API_URL", "http://localhost:8000")
CACHE_TTL = 300  # 5 minute cache
CORE_API_HOST_HEADER = os.getenv("CORE_API_HOST_HEADER", "localhost")

# Redis connection (fail-open: if Redis is down, skip caching)
try:
    _redis = redis_client.from_url(REDIS_URL, decode_responses=True)
    _redis.ping()
except Exception:
    _redis = None


def _cache_key(token: str) -> str:
    return "auth:" + hashlib.sha256(token.encode()).hexdigest()


async def verify_credentials(credentials: HTTPAuthorizationCredentials = Security(security)) -> dict:
    token = credentials.credentials
    is_api_key = token.startswith("sk_")

    # 1. Check Redis cache first
    # API keys are not cached so revocation, expiry, scope, and rate-limit
    # decisions from Core API apply on every public integration request.
    if _redis and not is_api_key:
        try:
            cached = _redis.get(_cache_key(token))
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # 2. Validate against Django Core API
    verify_path = "/api/auth/verify/" if is_api_key else "/api/auth/verify-user-token/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{CORE_API_URL}{verify_path}",
                json={"token": token},
                headers={"Host": CORE_API_HOST_HEADER},
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    payload = resp.json()
    subscription = payload.get("subscription") or {}
    if subscription and subscription.get("active") is False:
        raise HTTPException(status_code=402, detail="Tenant subscription is not active")

    # 3. Store in Redis cache (fire-and-forget)
    if _redis and not is_api_key:
        try:
            _redis.setex(_cache_key(token), CACHE_TTL, json.dumps(payload))
        except Exception:
            pass

    return payload
