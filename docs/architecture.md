# Architecture

## System Context
```mermaid
flowchart LR
    Users[Students, Faculty, Admins] --> Portal[Next.js Tenant Portal]
    Portal --> Core[Django Core API]
    Portal --> RAG[FastAPI RAG API]
    Core --> Postgres[(Cloud SQL Postgres)]
    Core --> Stripe[Stripe Billing]
    Core --> Keycloak[Keycloak OIDC]
    RAG --> Qdrant[(Qdrant Vector DB)]
    RAG --> Redis[(Redis Cache and Queue)]
    RAG --> Mongo[(Audit Log Store)]
    RAG --> LLM[vLLM Qwen3]
    RAG --> Embed[BGE-M3 Embeddings]
    Workers[Celery Workers] --> RAG
    Workers --> Qdrant
    Workers --> GCS[(GCS Uploads and Artifacts)]
```

## Container Architecture
```mermaid
flowchart TB
    subgraph Web
        FE[frontend: Next.js]
    end
    subgraph CoreBackend
        API[Django REST API]
        Auth[Keycloak JWT Verifier]
        Billing[Stripe Webhooks and Entitlements]
        Tenant[Tenants, Roles, Users, Plans]
    end
    subgraph RAGBackend
        Chat[Chat and Streaming API]
        Retrieval[Retriever and Reranker]
        Ingest[Ingestion API]
        Audit[Audit Writer]
    end
    subgraph Async
        Beat[Celery Beat]
        Worker[Celery Worker]
    end
    FE --> API
    FE --> Chat
    API --> Auth
    API --> Billing
    API --> Tenant
    Chat --> Retrieval
    Ingest --> Worker
    Beat --> API
    Worker --> Qdrant[(Qdrant)]
    Worker --> Redis[(Redis)]
    Retrieval --> Qdrant
```

## GCP Production Deployment
```mermaid
flowchart TB
    DNS[Cloud DNS] --> LB[HTTPS Load Balancer + Cloud Armor]
    LB --> FE[Cloud Run Frontend]
    LB --> Core[Cloud Run Core API]
    LB --> RAG[Cloud Run RAG API]
    Core --> SQL[(Cloud SQL Postgres)]
    Core --> SM[Secret Manager]
    Core --> KC[Keycloak on GKE]
    Core --> Stripe[Stripe]
    RAG --> Redis[Memorystore Redis]
    RAG --> QD[Qdrant on GKE]
    RAG --> VLLM[vLLM on GKE GPU Node Pool]
    RAG --> GCS[Cloud Storage]
    Worker[Celery Workers on GKE] --> Redis
    Worker --> QD
    Worker --> GCS
    Ops[Cloud Monitoring + Logging + Trace] --> FE
    Ops --> Core
    Ops --> RAG
    Ops --> Worker
```

## Core Data Boundaries
- Postgres is the source of truth for tenants, users, roles, plans, subscriptions, entitlements, usage, API keys, source definitions, schedules, prompt versions, and invoice mirrors.
- Qdrant stores chunks and embeddings with mandatory `metadata.tenant_id` and `metadata.roles` filters.
- Redis stores Celery queue state plus short-lived auth, embedding, and response caches.
- MongoDB currently stores audit logs; for GCP production, consider moving audit logs to Postgres partitions or BigQuery if analytics becomes important.
- GCS should replace local upload paths for production source artifacts and citation files.

## AI Gateway
- Local development defaults to Ollama for generation and embeddings.
- Production should set `LLM_PROVIDER=vllm`, `VLLM_MODEL=Qwen/Qwen3-8B`, `EMBEDDING_PROVIDER=bge-m3`, and `EMBEDDING_MODEL=BAAI/bge-m3`.
- The RAG API uses an OpenAI-compatible client for vLLM so provider changes do not touch chat business logic.
