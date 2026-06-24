"""
RAG SaaS Engine — FastAPI application.

Endpoints:
  GET  /              Health check
  POST /chat          Role-aware RAG query (requires valid Bearer API key)
  POST /chat/stream   SSE streaming RAG query (requires valid Bearer API key)
  POST /ingest/url    Enqueue URL ingestion async via Celery
  POST /ingest/file   Enqueue file upload ingestion async via Celery
  GET  /logs          Return recent audit log entries (requires Bearer)
"""
import asyncio
import hashlib
import json
import os
import time
import tempfile
import re
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form, Query, Header
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Annotated
from starlette.concurrency import run_in_threadpool

from auth import verify_credentials
from models import (
    ChatRequest,
    ChatResponse,
    StreamChatChunk,
    IngestUrlsRequest,
    PublicQueryRequest,
    PublicSourceRequest,
    PublicDocumentRequest,
)
from services.audit import log_request, log_request_async, fetch_recent_logs
from celery_app import celery_app, ingest_document_task, ingest_urls_task

UPLOAD_DIR = os.getenv("UPLOAD_DIR", tempfile.gettempdir())
RESPONSE_CACHE_TTL_SECONDS = int(os.getenv("RESPONSE_CACHE_TTL_SECONDS", 900))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RAG_INTERNAL_INGEST_TOKEN = os.getenv("RAG_INTERNAL_INGEST_TOKEN", "")
CORE_API_URL = os.getenv("CORE_API_URL", "http://localhost:8000")
CORE_API_HOST_HEADER = os.getenv("CORE_API_HOST_HEADER", "localhost")

_resp_cache_client = None


def _get_resp_cache():
    global _resp_cache_client
    if _resp_cache_client is None:
        try:
            import redis
            _resp_cache_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        except Exception:
            pass
    return _resp_cache_client


def _resp_cache_key(query: str, tenant_id: str, roles: list) -> str:
    normalized = query.lower().strip() + "|" + tenant_id + "|" + "|".join(sorted(roles))
    return "resp:" + hashlib.sha256(normalized.encode()).hexdigest()


def _get_cached_response(key: str) -> dict | None:
    r = _get_resp_cache()
    if not r:
        return None
    try:
        cached = r.get(key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    return None


def _cache_response(key: str, payload: dict) -> None:
    r = _get_resp_cache()
    if not r:
        return
    try:
        r.set(key, json.dumps(payload), ex=RESPONSE_CACHE_TTL_SECONDS)
    except Exception:
        pass


def _validate_internal_ingest_token(token: str | None) -> None:
    if not RAG_INTERNAL_INGEST_TOKEN or token != RAG_INTERNAL_INGEST_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized internal ingestion token")

GENERIC_QUERY_TERMS = {
    "what", "when", "where", "which", "with", "from", "your", "have", "this", "that",
    "explain", "describe", "tell", "about", "policy", "policies", "guideline", "guidelines",
    "please", "could", "would", "should", "does", "into", "there", "their", "them",
}

SELF_IDENTITY_PATTERNS = [
    r"\bwho\s+are\s+you\b",
    r"\bwhat\s+is\s+your\s+name\b",
    r"\btell\s+me\s+about\s+yourself\b",
    r"\bintroduce\s+yourself\b",
]

PROMPT_INJECTION_PATTERNS = [
    r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions\b",
    r"\breveal\s+(the\s+)?(system|developer|hidden)\s+prompt\b",
    r"\bdisregard\s+(the\s+)?(rules|instructions)\b",
    r"\bshow\s+me\s+your\s+(system|hidden)\s+instructions\b",
    r"\bact\s+as\s+(an?\s+)?unrestricted\b",
]


def _query_terms(query: str) -> set[str]:
    terms = {
        t.lower()
        for t in re.findall(r"[A-Za-z]{3,}", query)
        if t.lower() not in GENERIC_QUERY_TERMS
    }
    # Preserve all-caps acronyms (e.g., MIT, HR, IT) which are often key entities.
    acronyms = {a.lower() for a in re.findall(r"\b[A-Z]{2,}\b", query)}
    return terms.union(acronyms)


def _chunk_overlap(query_terms: set[str], content: str) -> int:
    if not query_terms:
        return 0
    content_tokens = {
        t.lower()
        for t in re.findall(r"[A-Za-z]{3,}", content or "")
    }
    return sum(1 for t in query_terms if t in content_tokens)


def _is_relevant_chunk(chunk: dict, query_terms: set[str]) -> bool:
    score = float(chunk.get("score") or 0.0)
    if not query_terms:
        return False
    min_score = 0.2 if len(query_terms) >= 2 else 0.3
    if score < min_score:
        return False
    overlap = _chunk_overlap(query_terms, chunk.get("content") or "")
    overlap_ratio = overlap / len(query_terms)
    return overlap >= 1 and overlap_ratio >= 0.34


def _select_relevant_chunks(chunks: list[dict], query_terms: set[str]) -> list[dict]:
    lexical_hits = [c for c in chunks if _is_relevant_chunk(c, query_terms)]
    if lexical_hits:
        return lexical_hits

    # For short/acronym queries where lexical overlap can miss but vector similarity is strong,
    # accept top semantic matches with a conservative threshold.
    if chunks and len(query_terms) <= 2:
        top_score = float(chunks[0].get("score") or 0.0)
        if top_score >= 0.5:
            return chunks[:3]

    return []


def _build_retrieval_query(user_query: str, query_terms: set[str]) -> str:
    # Acronym-only queries like "what is MIT" often need extra context tokens
    # to retrieve identity/overview chunks.
    if len(query_terms) == 1:
        only = next(iter(query_terms))
        if len(only) <= 4:
            return f"{user_query} university name overview"
    return user_query


def _is_self_identity_query(query: str) -> bool:
    q = (query or "").strip().lower()
    return any(re.search(pattern, q) for pattern in SELF_IDENTITY_PATTERNS)


def _is_prompt_injection_query(query: str) -> bool:
    q = (query or "").strip().lower()
    return any(re.search(pattern, q) for pattern in PROMPT_INJECTION_PATTERNS)


def _assistant_identity_response(base_prompt: str) -> str:
    if base_prompt:
        first_sentence = re.split(r"(?<=[.!?])\s+", base_prompt.strip())[0].strip()
        if first_sentence:
            return f"{first_sentence}"
    return (
        "I am your tenant knowledge assistant. I answer questions using your scoped "
        "knowledge base and cite sources for grounded facts."
    )


def _schedule_log_success(bg: BackgroundTasks, tenant_id: str, roles: list, query: str, response: ChatResponse, latency: float) -> None:
    """Queue audit log write as a FastAPI BackgroundTask (runs after response is sent)."""
    bg.add_task(
        log_request,
        tenant_id=tenant_id,
        roles=roles,
        query=query,
        response_metadata={
            "answer_preview": response.answer[:200],
            "citation_count": len(response.citations),
            "insufficient_evidence": response.insufficient_evidence,
        },
        latency=latency,
        status="success",
    )


def record_usage_event(tenant_id: str, event_type: str, quantity: int = 1, metadata: dict | None = None) -> None:
    if not RAG_INTERNAL_INGEST_TOKEN:
        return
    try:
        import httpx
        httpx.post(
            f"{CORE_API_URL}/api/usage-events/record/",
            json={
                "tenant": tenant_id,
                "event_type": event_type,
                "quantity": quantity,
                "metadata": metadata or {},
            },
            headers={
                "X-Ingestion-Token": RAG_INTERNAL_INGEST_TOKEN,
                "Host": CORE_API_HOST_HEADER,
            },
            timeout=5.0,
        )
    except Exception as exc:
        print(f"[USAGE] Failed to record usage event: {exc}")


def record_rag_trace(
    creds: dict,
    query: str,
    response: ChatResponse,
    latency_ms: int,
    status_label: str = "success",
    refusal_reason: str = "",
) -> None:
    if not RAG_INTERNAL_INGEST_TOKEN:
        return
    try:
        import httpx
        httpx.post(
            f"{CORE_API_URL}/api/rag-traces/record/",
            json={
                "tenant": creds.get("tenant_id"),
                "api_key": creds.get("api_key_id"),
                "api_key_prefix": creds.get("api_key_prefix", ""),
                "query": query,
                "roles": creds.get("roles", []),
                "top_chunks": [
                    {"title": citation.title, "source": citation.source, "score": citation.score}
                    for citation in response.citations
                ],
                "citation_count": len(response.citations),
                "insufficient_evidence": response.insufficient_evidence,
                "refusal_reason": refusal_reason,
                "latency_ms": latency_ms,
                "cost_units": max(len(query), 1),
                "status": status_label,
            },
            headers={
                "X-Ingestion-Token": RAG_INTERNAL_INGEST_TOKEN,
                "Host": CORE_API_HOST_HEADER,
            },
            timeout=5.0,
        )
    except Exception as exc:
        print(f"[TRACE] Failed to record RAG trace: {exc}")


def record_integration_job(
    creds: dict,
    job_type: str,
    external_task_id: str,
    request_payload: dict,
    status_label: str = "queued",
    result: dict | None = None,
    error: str = "",
) -> None:
    if not RAG_INTERNAL_INGEST_TOKEN:
        return
    try:
        import httpx
        httpx.post(
            f"{CORE_API_URL}/api/integration-jobs/record/",
            json={
                "tenant": creds.get("tenant_id"),
                "api_key": creds.get("api_key_id"),
                "job_type": job_type,
                "status": status_label,
                "external_task_id": external_task_id,
                "request": request_payload,
                "result": result or {},
                "error": error,
            },
            headers={
                "X-Ingestion-Token": RAG_INTERNAL_INGEST_TOKEN,
                "Host": CORE_API_HOST_HEADER,
            },
            timeout=5.0,
        )
    except Exception as exc:
        print(f"[JOB] Failed to record integration job: {exc}")


def verify_integration_job_owner(creds: dict, job_id: str) -> dict:
    if not RAG_INTERNAL_INGEST_TOKEN:
        raise HTTPException(status_code=503, detail="Job lookup is not configured")
    try:
        import httpx
        response = httpx.post(
            f"{CORE_API_URL}/api/integration-jobs/lookup/",
            json={
                "tenant": creds.get("tenant_id"),
                "external_task_id": job_id,
            },
            headers={
                "X-Ingestion-Token": RAG_INTERNAL_INGEST_TOKEN,
                "Host": CORE_API_HOST_HEADER,
            },
            timeout=5.0,
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Job lookup unavailable: {exc}")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Unknown job for this tenant")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail=f"Job lookup failed ({response.status_code})")
    return response.json()


async def record_usage_event_async(tenant_id: str, event_type: str, quantity: int = 1, metadata: dict | None = None) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, record_usage_event, tenant_id, event_type, quantity, metadata)


def _require_scope(creds: dict, scope: str) -> None:
    scopes = set(creds.get("scopes") or [])
    if scope not in scopes and "admin" not in scopes:
        raise HTTPException(status_code=403, detail=f"API credential is missing required scope: {scope}")


def _ensure_usage_available(creds: dict, feature: str) -> None:
    entitlement = ((creds.get("usage") or {}).get("entitlements") or {}).get(feature)
    if not entitlement:
        return
    limit = int(entitlement.get("limit") or 0)
    used = int(entitlement.get("used") or 0)
    if limit and used >= limit:
        raise HTTPException(status_code=402, detail=f"{feature} quota exceeded ({used}/{limit})")


def _effective_roles(creds: dict, requested_roles: list[str] | None = None) -> list[str]:
    allowed = {str(role) for role in creds.get("roles", [])}
    requested = {str(role) for role in (requested_roles or []) if str(role).strip()}
    if requested:
        selected = sorted(allowed & requested)
        if not selected:
            raise HTTPException(status_code=403, detail="Requested roles are not allowed for this credential")
        return selected
    return sorted(allowed)


def _apply_strong_grounded_fallback(answer: str, relevant_chunks: list, query_terms: set[str]) -> tuple[str, list, bool]:
    citations = []
    insufficient = "insufficient evidence" in answer.lower()
    if not insufficient:
        return answer, citations, False

    top = relevant_chunks[0]
    top_score = float(top.get("score") or 0.0)
    top_content = (top.get("content") or "").strip()
    overlap = _chunk_overlap(query_terms, top_content)
    overlap_ratio = (overlap / len(query_terms)) if query_terms else 0.0

    if top_score >= 0.55 and overlap_ratio >= 0.6 and top_content:
        sentences = re.split(r"(?<=[.!?])\s+", top_content)
        extractive = " ".join(sentences[:2]).strip()
        answer = f"{extractive} [Citation 1]"
        metadata = top.get("metadata") or {}
        citations = [{
            "id": 1,
            "title": metadata.get("title", "Unknown Source"),
            "source": metadata.get("source", ""),
            "score": round(top_score, 4),
        }]
        insufficient = False

    return answer, citations, insufficient

app = FastAPI(
    title="RAG SaaS Engine",
    description="Multi-tenant, role-aware Retrieval-Augmented Generation API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": "rag-engine"}


@app.post("/v1/query", response_model=ChatResponse, tags=["Public API"])
async def public_query_endpoint(
    request: PublicQueryRequest,
    creds: Annotated[dict, Depends(verify_credentials)],
    background_tasks: BackgroundTasks,
):
    _require_scope(creds, "query")
    _ensure_usage_available(creds, "chat_messages")
    start = time.time()
    response = await chat_endpoint(ChatRequest(query=request.query), creds, background_tasks)
    background_tasks.add_task(
        record_rag_trace,
        creds,
        request.query,
        response,
        int((time.time() - start) * 1000),
        "success",
        "insufficient_evidence" if response.insufficient_evidence else "",
    )
    return response


@app.post(
    "/v1/query/stream",
    tags=["Public API"],
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def public_query_stream_endpoint(
    request: PublicQueryRequest,
    creds: Annotated[dict, Depends(verify_credentials)],
):
    _require_scope(creds, "stream")
    _ensure_usage_available(creds, "chat_messages")
    return await chat_stream_endpoint(ChatRequest(query=request.query), creds)


@app.post("/v1/sources", tags=["Public API"])
async def public_source_endpoint(
    request: PublicSourceRequest,
    creds: Annotated[dict, Depends(verify_credentials)],
    background_tasks: BackgroundTasks,
):
    _require_scope(creds, "ingest")
    _ensure_usage_available(creds, "ingestion_runs")
    roles = _effective_roles(creds, request.roles)
    task = ingest_urls_task.delay(
        creds["tenant_id"],
        request.title,
        roles,
        [request.url],
        request.crawl_options.model_dump(),
    )
    payload = {
        "title": request.title,
        "url": request.url,
        "roles": roles,
        "crawl_options": request.crawl_options.model_dump(),
    }
    background_tasks.add_task(record_integration_job, creds, "ingest_url", task.id, payload)
    background_tasks.add_task(record_usage_event, creds["tenant_id"], "ingestion_run", 1, {"source": "v1_sources"})
    return {"job_id": task.id, "status": "queued", "source": request.url}


@app.post("/v1/documents", tags=["Public API"])
async def public_document_endpoint(
    request: PublicDocumentRequest,
    creds: Annotated[dict, Depends(verify_credentials)],
    background_tasks: BackgroundTasks,
):
    _require_scope(creds, "ingest")
    _ensure_usage_available(creds, "ingestion_runs")
    _ensure_usage_available(creds, "documents")
    roles = _effective_roles(creds, request.roles)
    safe_name = hashlib.sha256(f"{creds['tenant_id']}:{request.title}:{time.time()}".encode()).hexdigest()[:24]
    dest = Path(UPLOAD_DIR) / f"{creds['tenant_id']}_{safe_name}.txt"
    await run_in_threadpool(dest.write_text, request.content, "utf-8")
    task = ingest_document_task.delay(creds["tenant_id"], request.title, roles, "file", str(dest))
    payload = {
        "title": request.title,
        "source_uri": request.source_uri,
        "roles": roles,
        "content_length": len(request.content),
    }
    background_tasks.add_task(record_integration_job, creds, "ingest_document", task.id, payload)
    background_tasks.add_task(record_usage_event, creds["tenant_id"], "ingestion_run", 1, {"source": "v1_documents"})
    background_tasks.add_task(record_usage_event, creds["tenant_id"], "document_ingested", 1, {"source": "v1_documents"})
    return {"job_id": task.id, "status": "queued", "filename": dest.name}


@app.get("/v1/jobs/{job_id}", tags=["Public API"])
async def public_job_status_endpoint(
    job_id: str,
    creds: Annotated[dict, Depends(verify_credentials)],
):
    _require_scope(creds, "usage")
    job_record = await run_in_threadpool(verify_integration_job_owner, creds, job_id)
    try:
        from celery.result import AsyncResult
        result = AsyncResult(job_id, app=celery_app)
        payload = result.result if result.ready() and isinstance(result.result, dict) else {}
        return {
            "job_id": job_id,
            "status": result.status.lower(),
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else False,
            "record": job_record,
            "result": payload,
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Job backend unavailable: {exc}")


@app.get("/v1/usage", tags=["Public API"])
async def public_usage_endpoint(
    creds: Annotated[dict, Depends(verify_credentials)],
):
    _require_scope(creds, "usage")
    return {
        "tenant_id": creds.get("tenant_id"),
        "subscription": creds.get("subscription"),
        "usage": creds.get("usage"),
        "api_key_prefix": creds.get("api_key_prefix", ""),
        "scopes": creds.get("scopes", []),
        "rate_limit_per_minute": creds.get("rate_limit_per_minute"),
    }


@app.get(
    "/files/{file_name}",
    tags=["Ingestion"],
    responses={
        401: {"description": "Unauthorized"},
        403: {"description": "Forbidden"},
        400: {"description": "Invalid file path"},
        404: {"description": "File not found"},
    },
)
def get_ingested_file(
    file_name: str,
    creds: Annotated[dict, Depends(verify_credentials)],
    download: Annotated[bool, Query()] = False,
):
    """Serve tenant-scoped uploaded files for citation links with path traversal protection."""
    safe_name = os.path.basename(file_name)
    tenant_id = str(creds.get("tenant_id") or "")

    # Uploaded files are tenant-prefixed; enforce tenant ownership before read.
    if not safe_name.startswith(f"{tenant_id}_"):
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = Path(UPLOAD_DIR) / safe_name
    try:
        file_path.resolve().relative_to(Path(UPLOAD_DIR).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    disposition = "attachment" if download else "inline"
    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        headers={"Content-Disposition": f'{disposition}; filename="{safe_name}"'},
    )


@app.post(
    "/chat",
    response_model=ChatResponse,
    tags=["RAG"],
    responses={500: {"description": "Internal server error"}},
)
async def chat_endpoint(
    request: ChatRequest,
    creds: Annotated[dict, Depends(verify_credentials)],
    background_tasks: BackgroundTasks,
):
    start = time.time()
    tenant_id = creds["tenant_id"]
    roles = creds["roles"]
    base_prompt = (creds.get("base_prompt") or "").strip()

    try:
        from services.retrieval import retrieve_chunks
        from services.llm import generate_rag_answer

        if _is_prompt_injection_query(request.query):
            response = ChatResponse(
                answer=(
                    "I cannot follow instructions that try to bypass tenant, role, "
                    "or grounding controls. Ask a question about the approved knowledge base."
                ),
                citations=[],
                insufficient_evidence=True,
            )
            latency = round(time.time() - start, 3)
            _schedule_log_success(background_tasks, tenant_id, roles, request.query, response, latency)
            background_tasks.add_task(
                record_usage_event,
                tenant_id,
                "chat_message",
                1,
                {"guardrail": "prompt_injection"},
            )
            return response

        if _is_self_identity_query(request.query):
            response = ChatResponse(
                answer=_assistant_identity_response(base_prompt),
                citations=[],
                insufficient_evidence=False,
            )
            latency = round(time.time() - start, 3)
            _schedule_log_success(background_tasks, tenant_id, roles, request.query, response, latency)
            background_tasks.add_task(record_usage_event, tenant_id, "chat_message", 1, {"path": "chat"})
            return response

        # Check response cache before doing any retrieval or LLM work
        cache_key = _resp_cache_key(request.query, tenant_id, roles)
        cached = _get_cached_response(cache_key)
        if cached:
            response = ChatResponse(**cached)
            latency = round(time.time() - start, 3)
            _schedule_log_success(background_tasks, tenant_id, roles, request.query, response, latency)
            background_tasks.add_task(record_usage_event, tenant_id, "chat_message", 1, {"path": "chat", "cache_hit": True})
            return response

        query_terms = _query_terms(request.query)
        retrieval_query = _build_retrieval_query(request.query, query_terms)
        chunks = retrieve_chunks(retrieval_query, tenant_id, roles)
        relevant_chunks = _select_relevant_chunks(chunks, query_terms)

        if not relevant_chunks:
            response = ChatResponse(
                answer=(
                    "I don't have enough information in your knowledge base to "
                    "answer this question. Please contact your administrator to "
                    "ingest relevant documents."
                ),
                citations=[],
                insufficient_evidence=True,
            )
        else:
            answer, citations = generate_rag_answer(
                request.query, relevant_chunks, base_prompt=base_prompt,
                llm_config=creds.get("generation_config"),
            )
            answer, fallback_citations, insufficient = _apply_strong_grounded_fallback(
                answer,
                relevant_chunks,
                query_terms,
            )
            if fallback_citations:
                citations = fallback_citations

            response = ChatResponse(
                answer=answer,
                citations=citations,
                insufficient_evidence=insufficient,
            )
            # Only cache grounded, successful responses
            if not response.insufficient_evidence:
                _cache_response(cache_key, response.model_dump())

        latency = round(time.time() - start, 3)
        _schedule_log_success(background_tasks, tenant_id, roles, request.query, response, latency)
        background_tasks.add_task(record_usage_event, tenant_id, "chat_message", 1, {"path": "chat"})
        return response

    except Exception as e:
        latency = round(time.time() - start, 3)
        background_tasks.add_task(log_request, tenant_id, roles, request.query, {"error": str(e)}, latency, "error")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post(
    "/chat/stream",
    tags=["RAG"],
    responses={
        200: {"content": {"text/event-stream": {}}},
        500: {"description": "Internal server error"},
    },
    summary="Streaming SSE chat — same auth/retrieval as /chat, yields tokens progressively",
)
async def chat_stream_endpoint(
    request: ChatRequest,
    creds: Annotated[dict, Depends(verify_credentials)],
):
    start = time.time()
    tenant_id = creds["tenant_id"]
    roles = creds["roles"]
    base_prompt = (creds.get("base_prompt") or "").strip()

    from services.retrieval import retrieve_chunks
    from services.llm import stream_rag_answer

    def _sse(chunk: StreamChatChunk) -> str:
        return f"data: {chunk.model_dump_json()}\n\n"

    async def event_generator():
        try:
            if _is_prompt_injection_query(request.query):
                msg = (
                    "I cannot follow instructions that try to bypass tenant, role, "
                    "or grounding controls. Ask a question about the approved knowledge base."
                )
                yield _sse(StreamChatChunk(chunk=msg, done=False))
                yield _sse(StreamChatChunk(chunk="", done=True, citations=[], insufficient_evidence=True))
                latency = round(time.time() - start, 3)
                asyncio.create_task(log_request_async(
                    tenant_id, roles, request.query,
                    {"answer_preview": msg[:200], "citation_count": 0, "insufficient_evidence": True, "guardrail": "prompt_injection"},
                    latency, "success",
                ))
                asyncio.create_task(record_usage_event_async(tenant_id, "chat_message", 1, {"path": "chat_stream", "guardrail": "prompt_injection"}))
                return

            if _is_self_identity_query(request.query):
                answer = _assistant_identity_response(base_prompt)
                yield _sse(StreamChatChunk(chunk=answer, done=False))
                yield _sse(StreamChatChunk(chunk="", done=True, citations=[], insufficient_evidence=False))
                latency = round(time.time() - start, 3)
                asyncio.create_task(log_request_async(
                    tenant_id, roles, request.query,
                    {"answer_preview": answer[:200], "citation_count": 0, "insufficient_evidence": False},
                    latency, "success",
                ))
                asyncio.create_task(record_usage_event_async(tenant_id, "chat_message", 1, {"path": "chat_stream"}))
                return

            # Cache hit: emit full answer as a single chunk then done
            cache_key = _resp_cache_key(request.query, tenant_id, roles)
            cached = _get_cached_response(cache_key)
            if cached:
                yield _sse(StreamChatChunk(chunk=cached["answer"], done=False))
                yield _sse(StreamChatChunk(
                    chunk="",
                    done=True,
                    citations=cached.get("citations", []),
                    insufficient_evidence=cached.get("insufficient_evidence", False),
                ))
                latency = round(time.time() - start, 3)
                asyncio.create_task(log_request_async(
                    tenant_id, roles, request.query,
                    {"answer_preview": cached["answer"][:200], "citation_count": len(cached.get("citations", [])), "insufficient_evidence": cached.get("insufficient_evidence", False)},
                    latency, "success",
                ))
                asyncio.create_task(record_usage_event_async(tenant_id, "chat_message", 1, {"path": "chat_stream", "cache_hit": True}))
                return

            query_terms = _query_terms(request.query)
            retrieval_query = _build_retrieval_query(request.query, query_terms)
            chunks = await run_in_threadpool(retrieve_chunks, retrieval_query, tenant_id, roles)
            relevant_chunks = _select_relevant_chunks(chunks, query_terms)

            if not relevant_chunks:
                msg = (
                    "I don't have enough information in your knowledge base to "
                    "answer this question. Please contact your administrator to "
                    "ingest relevant documents."
                )
                yield _sse(StreamChatChunk(chunk=msg, done=False))
                yield _sse(StreamChatChunk(chunk="", done=True, citations=[], insufficient_evidence=True))
                latency = round(time.time() - start, 3)
                asyncio.create_task(log_request_async(
                    tenant_id, roles, request.query,
                    {"answer_preview": msg[:200], "citation_count": 0, "insufficient_evidence": True},
                    latency, "success",
                ))
                asyncio.create_task(record_usage_event_async(tenant_id, "chat_message", 1, {"path": "chat_stream"}))
                return

            # Build citations up-front (same dedup logic as non-streaming path)
            from services.llm import _build_context_and_citations
            _, citations = _build_context_and_citations(relevant_chunks)

            # Stream tokens from Ollama
            full_answer = ""
            _llm_config = creds.get("generation_config")
            gen = await run_in_threadpool(lambda: stream_rag_answer(request.query, relevant_chunks, base_prompt, _llm_config))
            for token in gen:
                full_answer += token
                yield _sse(StreamChatChunk(chunk=token, done=False))

            # Apply fallback + determine insufficiency on completed answer
            _, fallback_citations, insufficient = _apply_strong_grounded_fallback(
                full_answer, relevant_chunks, query_terms,
            )
            final_citations = fallback_citations if fallback_citations else citations
            if "insufficient evidence" in full_answer.lower():
                insufficient = True
                final_citations = []

            yield _sse(StreamChatChunk(
                chunk="",
                done=True,
                citations=final_citations,
                insufficient_evidence=insufficient,
            ))

            latency = round(time.time() - start, 3)
            asyncio.create_task(log_request_async(
                tenant_id, roles, request.query,
                {"answer_preview": full_answer[:200], "citation_count": len(final_citations), "insufficient_evidence": insufficient},
                latency, "success",
            ))
            asyncio.create_task(record_usage_event_async(tenant_id, "chat_message", 1, {"path": "chat_stream"}))

        except Exception as e:
            latency = round(time.time() - start, 3)
            asyncio.create_task(log_request_async(
                tenant_id, roles, request.query, {"error": str(e)}, latency, "error",
            ))
            yield _sse(StreamChatChunk(
                chunk=f"Internal error: {str(e)[:120]}",
                done=True,
                citations=[],
                insufficient_evidence=True,
            ))

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post(
    "/ingest/url",
    tags=["Ingestion"],
    responses={403: {"description": "Cross-tenant ingestion forbidden"}},
)
async def ingest_url(
    tenant_id: str,
    title: str,
    roles: List[str],
    source_uri: str,
    creds: Annotated[dict, Depends(verify_credentials)],
):
    if creds["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant ingestion forbidden")

    task = ingest_urls_task.delay(
        tenant_id,
        title,
        roles,
        [source_uri],
        {
            "crawl_mode": "single_page",
            "include_pdfs": True,
            "obey_robots_txt": True,
            "max_depth": 2,
            "max_pages": 200,
            "max_pdfs": 100,
            "max_pdf_size_mb": 20,
            "requests_per_second": 2,
        },
    )
    asyncio.create_task(record_usage_event_async(tenant_id, "ingestion_run", 1, {"source": "ingest_url"}))
    return {"task_id": task.id, "status": "queued", "source": source_uri}


@app.post(
    "/ingest/urls",
    tags=["Ingestion"],
    responses={403: {"description": "Cross-tenant ingestion forbidden"}},
)
async def ingest_urls(
    request: IngestUrlsRequest,
    creds: Annotated[dict, Depends(verify_credentials)],
):
    if creds["tenant_id"] != request.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant ingestion forbidden")

    task = ingest_urls_task.delay(
        request.tenant_id,
        request.title,
        request.roles,
        request.source_uris,
        request.crawl_options.model_dump(),
    )
    asyncio.create_task(record_usage_event_async(request.tenant_id, "ingestion_run", 1, {"source": "ingest_urls", "count": len(request.source_uris)}))
    return {"task_id": task.id, "status": "queued", "sources": request.source_uris}


@app.post(
    "/internal/ingest/urls",
    tags=["Ingestion"],
    responses={401: {"description": "Unauthorized internal token"}},
)
async def internal_ingest_urls(
    request: IngestUrlsRequest,
    x_ingestion_token: Annotated[str | None, Header(alias="X-Ingestion-Token")] = None,
):
    _validate_internal_ingest_token(x_ingestion_token)
    task = ingest_urls_task.delay(
        request.tenant_id,
        request.title,
        request.roles,
        request.source_uris,
        request.crawl_options.model_dump(),
    )
    asyncio.create_task(record_usage_event_async(request.tenant_id, "ingestion_run", 1, {"source": "internal_ingest_urls", "count": len(request.source_uris)}))
    return {"status": "queued", "task_ids": [task.id]}


ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".csv"}

@app.post(
    "/ingest/file",
    tags=["Ingestion"],
    responses={
        403: {"description": "Cross-tenant ingestion forbidden"},
        422: {"description": "Unsupported file type"},
    },
)
async def ingest_file(
    tenant_id: Annotated[str, Form(...)],
    title: Annotated[str, Form(...)],
    roles: Annotated[str, Form(...)],
    file: Annotated[UploadFile, File(...)],
    creds: Annotated[dict, Depends(verify_credentials)],
):
    if creds["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant ingestion forbidden")

    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Save to a temp file the worker can read
    dest = os.path.join(UPLOAD_DIR, f"{tenant_id}_{int(time.time())}_{file.filename}")
    content = await file.read()
    await run_in_threadpool(Path(dest).write_bytes, content)

    role_list = [r.strip() for r in roles.split(",") if r.strip()]
    task = ingest_document_task.delay(tenant_id, title, role_list, "file", dest)
    asyncio.create_task(record_usage_event_async(tenant_id, "ingestion_run", 1, {"source": "ingest_file"}))
    return {"task_id": task.id, "status": "queued", "filename": file.filename}


@app.get("/logs", tags=["Audit"])
async def get_logs(
    creds: Annotated[dict, Depends(verify_credentials)],
    limit: int = 50,
):
    logs = fetch_recent_logs(tenant_id=creds["tenant_id"], limit=limit)
    return {"logs": logs}
