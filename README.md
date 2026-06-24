# Multi-Tenant Role-Aware RAG SaaS

An open-core, CPU-first Retrieval-Augmented Generation SaaS platform with tenant isolation, role-aware retrieval, public integration APIs, scheduled knowledge ingestion, usage metering, audit logging, and a Next.js admin portal.

The repository is structured as a full-stack reference implementation for teams embedding governed RAG into their own web apps, mobile apps, CRMs, internal tools, customer support copilots, or document-aware AI products where access control and source attribution matter.

## Features

- Multi-tenant SaaS domain model with tenants, users, roles, API keys, subscription plans, entitlements, and usage records.
- Role-aware RAG retrieval that filters indexed knowledge by tenant and user role metadata.
- FastAPI chat and ingestion service with Celery workers for asynchronous processing and scheduled jobs.
- Django REST Framework core API with JWT, Keycloak OIDC hooks, Stripe webhook mirrors, and OpenAPI documentation.
- Next.js portal for tenant administration, billing controls, prompt configuration, source management, and chat.
- Versioned `/v1` public RAG API for external app, CRM, and backend integrations.
- Self-serve tenant signup with trial provisioning, default roles, and first integration API key.
- API-key scopes, expiry, revocation, last-used tracking, and per-minute rate limits.
- RAG traces and integration job records for quality reporting and support.
- Qdrant vector storage, PostgreSQL operational storage, MongoDB audit logs, Redis task queues, and Ollama local model support.
- Local CPU-friendly defaults with a production path for vLLM-compatible OpenAI-style inference and BGE-M3 embeddings.

## Architecture

The active application roots are:

| Path | Purpose |
| --- | --- |
| `core_backend/` | Django REST API for tenants, users, roles, API keys, plans, billing mirrors, and ingestion schedules. |
| `rag_backend/` | FastAPI RAG/chat API, ingestion pipeline, embedding and LLM adapters, audit logging, and Celery tasks. |
| `frontend/` | Next.js tenant portal and admin UI. |
| `docs/` | Architecture notes, workflows, API contracts, runbook, roadmap, and security/compliance guidance. |

Local infrastructure is defined in `docker-compose.yml` and includes PostgreSQL, MongoDB, Redis, Qdrant, Ollama, both backend services, Celery worker/beat, and the frontend.

## Tech Stack

- Frontend: Next.js, React, Tailwind CSS
- Core API: Django, Django REST Framework, SimpleJWT, drf-spectacular
- RAG API: FastAPI, LangChain, Qdrant client, OpenAI-compatible client
- Workers: Celery, Redis
- Storage: PostgreSQL, MongoDB, Qdrant
- Local AI runtime: Ollama with `nomic-embed-text` and `llama3.2:3b`
- Production AI path: vLLM/OpenAI-compatible endpoint with configurable embedding and reranking models

## Prerequisites

- Docker and Docker Compose
- Python 3.11 or newer for local backend development
- Node.js 20 or newer for frontend development
- At least 16 GB of available RAM for the full local Docker stack with local models

## Quick Start

Create your local environment file:

```bash
make setup
```

Start the complete Docker stack:

```bash
make up
```

Pull the local Ollama models after the Ollama container is running:

```bash
make pull-models
```

Run database migrations and seed demo data:

```bash
make migrate
make seed
```

Open the services:

- Frontend: <http://localhost:3000>
- Core API: <http://localhost:8000>
- Core API schema/docs: <http://localhost:8000/api/docs>
- RAG API: <http://localhost:8001>
- RAG API docs: <http://localhost:8001/docs>

## Public Integration API

Use tenant API keys from trusted server-side code. For mobile and browser-only apps, proxy calls through your backend so full-scope keys are not exposed.

Core onboarding and integration helpers:

- `POST /api/signup/` provisions a tenant, admin user, trial subscription, roles, and first API key.
- `GET /api/integration/quickstart/` returns integration examples for the signed-in tenant.
- `POST /api/api-keys/{id}/rotate/` rotates a key and returns the new raw key once.
- `POST /api/api-keys/{id}/revoke/` revokes a key.

RAG public API:

- `POST /v1/query`
- `POST /v1/query/stream`
- `POST /v1/sources`
- `POST /v1/documents`
- `GET /v1/jobs/{id}`
- `GET /v1/usage`

Example:

```bash
curl -X POST http://localhost:8001/v1/query \
  -H "Authorization: Bearer sk_your_key" \
  -H "Content-Type: application/json" \
  -d '{"query":"What does our refund policy say?"}'
```

## Local Development

Install Python dependencies into the root virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r core_backend\requirements.txt -r rag_backend\requirements.txt
```

Run the Django API:

```powershell
cd core_backend
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py runserver 8000
```

Run the RAG API:

```powershell
cd rag_backend
..\.venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8001 --reload
```

Run the Celery worker:

```powershell
cd rag_backend
..\.venv\Scripts\celery.exe -A celery_app worker --loglevel=info -P solo
```

Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

## Configuration

Copy `.env.example` to `.env` for local development. The `.env` file is intentionally ignored and must not be committed.

Important production settings to rotate or replace before deployment:

- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `MONGO_PASSWORD`
- `RAG_INTERNAL_INGEST_TOKEN`
- `SCHEDULER_TRIGGER_TOKEN`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- Keycloak issuer, JWKS URL, and audience values
- vLLM/OpenAI-compatible endpoint credentials

## Demo Data

After running `make seed`, use this demo tenant ID in the portal:

```text
00000000-0000-0000-0000-000000000001
```

Demo users:

| Role | Username | Password |
| --- | --- | --- |
| Student | `stanford_student` | `password123` |
| Faculty | `stanford_faculty` | `password123` |
| Admin | `stanford_admin` | `password123` |

The demo tenant uses public Stanford web pages for sample content. This project is not affiliated with or endorsed by Stanford University.

## Tests

Run all backend tests:

```bash
make test
```

Run each backend test suite separately:

```bash
make test-core
make test-rag
```

Run frontend linting:

```bash
cd frontend
npm run lint
```

## Documentation

- [Architecture](docs/architecture.md)
- [API Contracts](docs/api-contracts.md)
- [Workflows](docs/workflows.md)
- [Security and Compliance](docs/security-compliance.md)
- [Runbook](docs/runbook.md)
- [Implementation Roadmap](docs/implementation-roadmap.md)
- [Repository Structure](docs/repo-structure.md)

## Open Core

The self-hostable core is released under the MIT License. The hosted SaaS and enterprise roadmap can add managed hosting, premium connectors, SSO, advanced analytics, support, and dedicated deployment options while keeping the core platform open.

For security-sensitive deployments, review `docs/security-compliance.md` and replace all development defaults before exposing the stack outside a trusted local network.
