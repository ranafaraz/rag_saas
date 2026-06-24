# API Contracts

## Authentication
- Local demo login: `POST /api/auth/login/` returns a SimpleJWT access token.
- Production login: Keycloak OIDC access tokens are accepted when `KEYCLOAK_JWKS_URL` and `KEYCLOAK_AUDIENCE` are configured.
- RAG API accepts either API keys beginning with `sk_` or user JWTs. It calls Core API verification endpoints before chat, ingestion, logs, and citation file access.
- Public `/v1` integrations should use scoped API keys from trusted server-side code. Do not expose full-scope keys in browser-only or mobile clients.

## Self-Serve Signup
`POST /api/signup/` provisions a tenant, admin user, default roles, trial subscription, entitlements, and first integration API key.

```json
{
  "organization_name": "Acme Apps",
  "workspace_slug": "acme-apps",
  "admin_username": "acme-admin",
  "admin_email": "admin@acme.example",
  "admin_password": "super-secret-123",
  "plan_code": "developer-starter"
}
```

The response includes `tenant`, `user`, `subscription`, `api_key.raw_key`, and a tenant admin `access_token`.

## Tenant-Scoped Core APIs
All tenant data endpoints require authentication and automatically scope non-superusers to `request.user.tenant_id`.

- `GET /api/auth/me/`
- `GET /api/roles/`
- `GET /api/users/`
- `GET /api/api-keys/`
- `GET /api/documents/`
- `GET /api/base-prompts/`
- `GET /api/prompt-versions/`
- `GET /api/ingestion-sources/`
- `GET /api/ingestion-schedules/`
- `GET /api/ingestion-run-logs/`
- `GET /api/usage/summary/`
- `GET /api/billing/summary/`
- `GET /api/integration/quickstart/`
- `GET /api/integration-jobs/`
- `GET /api/rag-traces/`

Unsafe methods require tenant admin unless the view is a content operation. Source, schedule, document, and prompt operations may also be performed by Faculty/Staff roles.

## Billing APIs
`POST /api/billing/checkout/`

```json
{
  "plan_code": "education-starter",
  "success_url": "https://app.example.com/billing/success",
  "cancel_url": "https://app.example.com/billing/cancel"
}
```

Response:

```json
{
  "checkout_url": "https://checkout.stripe.com/...",
  "session_id": "cs_test_..."
}
```

`POST /api/billing/stripe/webhook/`

Accepted events:
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.created`
- `invoice.finalized`
- `invoice.payment_succeeded`
- `invoice.payment_failed`

The webhook mirrors Stripe subscription and invoice state into Postgres. Configure `STRIPE_WEBHOOK_SECRET` in production.

## Internal Usage Recording
`POST /api/usage-events/record/`

Headers:

```http
X-Ingestion-Token: <RAG_INTERNAL_INGEST_TOKEN>
```

Body:

```json
{
  "tenant": "00000000-0000-0000-0000-000000000001",
  "event_type": "chat_message",
  "quantity": 1,
  "metadata": {
    "path": "chat_stream"
  }
}
```

## RAG APIs
Public stable endpoints:

`POST /v1/query`

```json
{
  "query": "What does our refund policy say?"
}
```

`POST /v1/query/stream` uses the same request body and returns SSE frames.

`POST /v1/sources`

```json
{
  "title": "Help Center",
  "url": "https://example.com/help",
  "roles": ["Member"]
}
```

`POST /v1/documents`

```json
{
  "title": "Internal Policy",
  "content": "Policy text...",
  "roles": ["Member"],
  "source_uri": "crm://article/123"
}
```

`GET /v1/jobs/{id}` returns Celery job state.

`GET /v1/usage` returns subscription, entitlements, usage, scopes, and API-key prefix.

Backward-compatible internal endpoints:

`POST /chat`

```json
{
  "query": "What financial aid is available?"
}
```

Response:

```json
{
  "answer": "Grounded answer with [Citation 1].",
  "citations": [
    {
      "id": 1,
      "title": "Financial Aid",
      "source": "https://example.edu/financial-aid",
      "score": 0.91
    }
  ],
  "insufficient_evidence": false
}
```

`POST /chat/stream` uses the same request body and returns SSE frames containing `StreamChatChunk` objects.

## Tenant-Scope Rules
- Never trust client-supplied tenant IDs for authorization.
- Core API filters all tenant models by authenticated user tenant.
- RAG API must use tenant and role claims returned by Core API.
- Qdrant queries must always include both `metadata.tenant_id` and `metadata.roles`.
