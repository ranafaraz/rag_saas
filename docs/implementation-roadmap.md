# Implementation Roadmap

## Phase 1 - Product Foundation
Status: implemented in this branch as the first market-ready slice.

- Add commercial models: plans, subscriptions, entitlements, usage events, invoices, invitations, AI model configs, prompt versions, and evaluation runs.
- Add tenant-scoped authenticated APIs and JWT support.
- Add Stripe checkout/webhook endpoints and billing summaries.
- Add usage recording from RAG chat and ingestion paths.
- Add vLLM/OpenAI-compatible generation path and BGE-M3 embedding gateway.
- Add Billing tab to the admin workspace.
- Add documentation set with architecture and workflow diagrams.

Acceptance:
- Core tests cover tenant auth, API key verification, inactive subscription blocking, scheduling, and usage recording.
- Frontend builds successfully.
- RAG tests pass with external services mocked.

## Phase 2 - Identity and Onboarding
- Deploy Keycloak with a `rag-saas` realm.
- Add OIDC login to the frontend.
- Add invitation acceptance and role assignment workflow.
- Add tenant provisioning after successful Stripe checkout.
- Add admin onboarding checklist.

Acceptance:
- A new tenant admin can subscribe, sign in through Keycloak, invite users, and see billing state.

## Phase 3 - Production AI and Quality
- Deploy vLLM Qwen3 on GKE GPU node pool.
- Enable BGE-M3 embeddings in workers and RAG API.
- Recreate Qdrant collection with the production embedding dimension.
- Add golden question datasets and scheduled evaluation runs.
- Add failed-answer analytics and stale-source warnings.

Acceptance:
- Evaluation suite tracks grounded answer rate, citation coverage, refusal correctness, and cross-tenant isolation.

## Phase 4 - GCP Release Readiness
- Move Postgres to Cloud SQL.
- Move Redis to Memorystore.
- Move uploads to GCS.
- Deploy frontend, Core API, and RAG API to Cloud Run.
- Deploy Qdrant, Keycloak, Celery workers, and vLLM to GKE.
- Add Cloud Monitoring alerts, dashboards, logs, and backup restore runbooks.

Acceptance:
- Production smoke test passes after clean deploy.
- Backup restore has been tested.
- Load test meets target latency and concurrency for the starter tier.

## Phase 5 - Sellable SaaS Polish
- Add plan upgrade/downgrade UI.
- Add usage warnings and upgrade prompts.
- Add connector marketplace.
- Add customer-facing security page.
- Add in-app quality reports for admins.

Acceptance:
- The product can support a paid pilot without manual database edits.
