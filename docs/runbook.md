# Runbook

## Local Setup
1. Copy `.env.example` to `.env`.
2. Start the stack:

```powershell
docker compose up -d --build
```

3. Run migrations:

```powershell
docker compose exec core_api python manage.py migrate
```

4. Seed the demo tenant:

```powershell
docker compose exec core_api python manage.py seed
```

5. Open the app at `http://localhost:3000`.

## Demo Accounts
- Student: `stanford_student` / `password123`
- Faculty: `stanford_faculty` / `password123`
- Admin: `stanford_admin` / `password123`

The Stanford demo is unaffiliated and for internal product demonstration only.

## Production Environment
Required variables:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `POSTGRES_*`
- `REDIS_URL`
- `QDRANT_HOST`
- `RAG_INTERNAL_INGEST_TOKEN`
- `SCHEDULER_TRIGGER_TOKEN`
- `KEYCLOAK_ISSUER`
- `KEYCLOAK_JWKS_URL`
- `KEYCLOAK_AUDIENCE`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `LLM_PROVIDER=vllm`
- `VLLM_BASE_URL`
- `VLLM_MODEL`
- `EMBEDDING_PROVIDER=bge-m3`
- `EMBEDDING_MODEL=BAAI/bge-m3`
- `EMBEDDING_DIMENSION=1024`

For BGE-M3 production workers, build the RAG image with `rag_backend/requirements-prod.txt` so `FlagEmbedding` is installed.

## Migrations
Run migrations before recreating workers:

```powershell
docker compose exec core_api python manage.py migrate --noinput
```

## Backups
- Cloud SQL: enable automated backups and point-in-time recovery.
- Qdrant: schedule snapshots and copy them to GCS.
- GCS: enable object versioning for upload buckets.
- Keycloak: back up realm export and database.

## Restore Drill
1. Restore Cloud SQL backup to a staging instance.
2. Restore Qdrant snapshot into staging.
3. Point staging services to restored dependencies.
4. Run a seeded tenant smoke test: login, source list, chat, citation open, billing summary.

## Monitoring
Track:

- Core API 5xx rate.
- RAG API 5xx rate.
- Chat latency p50/p95/p99.
- Retrieval empty-result rate.
- Insufficient-evidence rate.
- Celery queue depth.
- Ingestion failures.
- Stripe webhook failures.
- Keycloak login errors.
- Qdrant memory and disk pressure.

## Incident Response
1. Identify affected tenant and service.
2. Disable unsafe schedules if ingestion caused the issue.
3. Revoke compromised API keys or Keycloak sessions.
4. Snapshot databases before repair.
5. Apply fix in staging, then production.
6. Record incident timeline and customer impact.

## Demo Reset
```powershell
docker compose exec core_api python manage.py seed
```

This resets the Stanford demo relational records, subscriptions, entitlements, prompts, sources, schedules, and queues web ingestion.
