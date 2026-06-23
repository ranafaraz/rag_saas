# Security and Compliance

## Tenant Isolation
- Core API viewsets are authenticated by default.
- Non-superusers can only list and mutate records belonging to their tenant.
- RAG retrieval enforces Qdrant filters for tenant ID and role intersection.
- Citation file access requires tenant-prefixed file ownership.

## Identity
- Production uses Keycloak OIDC with JWKS verification.
- Required token claims: `email` or `preferred_username`, plus `tenant_id`.
- Tenant admins should enable MFA.
- Enterprise SSO can be added through Keycloak SAML or OIDC identity brokering.

## Billing and Entitlements
- Stripe is the billing system of record.
- Core mirrors subscriptions, invoices, entitlements, and usage.
- Chat and ingestion usage is recorded through an internal token-protected endpoint.
- Inactive subscriptions return `402 Payment Required` from RAG token verification.

## LLM Security
Controls aligned to OWASP LLM guidance:

- Prompt-injection detection for common bypass patterns.
- System prompt requires answers only from retrieved context.
- Citation clearing when the model declares insufficient evidence.
- Tenant and role filters before LLM prompt construction.
- No hidden prompt or source credentials in retrieved context.
- Audit logs for query, roles, latency, answer preview, status, and citation count.

## Secrets
- Store production secrets in GCP Secret Manager.
- Do not commit `.env`.
- Rotate `DJANGO_SECRET_KEY`, `RAG_INTERNAL_INGEST_TOKEN`, `SCHEDULER_TRIGGER_TOKEN`, Stripe keys, and Keycloak client secrets before launch.

## Data Protection
- Use Cloud SQL automated backups and point-in-time recovery.
- Use Qdrant snapshots for vector recovery.
- Store uploads in GCS with tenant-scoped object prefixes.
- Encrypt all public traffic with HTTPS through Cloud Load Balancing.
- Set retention policies for audit logs and uploaded files per subscription tier.

## SOC2 Readiness Checklist
- Access reviews for production systems.
- MFA for admins.
- Change management through pull requests and CI checks.
- Incident response runbook.
- Backup restore tests.
- Centralized logs and alerting.
- Vendor/subprocessor list.
- Data deletion workflow per tenant.
