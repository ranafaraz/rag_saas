# Product Strategy

## Positioning
This product is a horizontal open-core RAG SaaS for teams that need to embed governed knowledge answers into their own web apps, mobile apps, CRMs, support tooling, and internal workflows. Each tenant gets private role-aware retrieval, scoped API keys, managed ingestion, citations, usage controls, and quality reporting.

The product should sell on three values:

- Trusted answers from approved customer content.
- Developer-friendly APIs for external applications and workflow systems.
- Tenant, role, scope, and entitlement controls for safe multi-customer operation.
- Managed ingestion, refresh schedules, auditability, evals, and usage controls.

## Ideal Customers
- SaaS teams adding customer-specific AI answers to their apps without building a RAG platform from scratch.
- Agencies and integrators embedding RAG into client portals, mobile apps, CRMs, and support workflows.
- Operations teams that need secure internal knowledge APIs with citations and auditability.
- Education remains a strong demo vertical, but not the primary product boundary.

## Subscription Tiers
Use Stripe as the billing system of record and mirror subscription state into the core database.

| Tier | Target | Included |
| --- | --- | --- |
| Developer Starter | Product pilots | 5 seats, 250 docs, 25 sources, 2k chats/month, 100 ingestion runs/month |
| Growth API | Production SaaS teams | 50 seats, 5k docs, 250 sources, 100k chats/month, scoped API keys |
| Enterprise | Regulated or high-scale customers | SSO, advanced audit retention, premium connectors, dedicated support, optional dedicated deployment |

## Demo Policy
Public demos must avoid implying endorsement from real universities. Keep the current Stanford demo clearly labeled as unaffiliated internal demo data, or replace external sales demos with a synthetic "Northstar University" tenant that uses generated content.

## Market Improvements
- Add self-serve signup, tenant provisioning, and Stripe checkout.
- Add stable `/v1` public APIs, integration examples, scoped API keys, rotation, revocation, and rate limits.
- Add onboarding checklists for sources, roles, prompts, and scheduler setup.
- Add compliance assets: data processing addendum, retention policy, incident response policy, subprocessors, and security overview.
- Add quality reporting: answered rate, citation coverage, top failed questions, stale sources, latency, and retrieval confidence.
- Add connectors after the web crawler is stable: Google Drive, SharePoint, Confluence, Notion, Canvas, Moodle, and public sitemap import.

## Roadmap
- Phase 1: secure tenant APIs, billing foundation, usage metering, docs, and production configuration.
- Phase 2: Keycloak OIDC, invitation onboarding, Stripe checkout and webhooks, and billing UI.
- Phase 3: vLLM and BGE-M3 production AI gateway, quality evaluation, and prompt/version governance.
- Phase 4: GCP deployment automation, observability, backups, load testing, and compliance hardening.
