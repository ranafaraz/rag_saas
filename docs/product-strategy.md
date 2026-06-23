# Product Strategy

## Positioning
This product is a subscription SaaS knowledge assistant for universities, schools, and training organizations. It gives each tenant a private, role-aware RAG workspace where admins manage sources, faculty and staff inspect operational knowledge, and students ask grounded questions with citations.

The product should sell on three values:

- Trusted answers from approved institutional sources.
- Role-aware access control for students, faculty, staff, and admins.
- Managed ingestion, refresh schedules, auditability, and usage controls.

## Ideal Customers
- Universities with fragmented admissions, financial aid, policy, registrar, and student-services content.
- Private schools and training organizations that need a secure internal knowledge assistant.
- Departments that need a pilot before institution-wide SSO and compliance rollout.

## Subscription Tiers
Use Stripe as the billing system of record and mirror subscription state into the core database.

| Tier | Target | Included |
| --- | --- | --- |
| Education Starter | Department pilots | 25 seats, 500 docs, 40 sources, 10k chats/month, 250 ingestion runs/month |
| Institution Growth | Multi-department rollout | 250 seats, 5k docs, 250 sources, 100k chats/month, SSO |
| Enterprise Campus | Full campus or network | Custom seats, dedicated support, longer audit retention, optional dedicated deployment |

## Demo Policy
Public demos must avoid implying endorsement from real universities. Keep the current Stanford demo clearly labeled as unaffiliated internal demo data, or replace external sales demos with a synthetic "Northstar University" tenant that uses generated content.

## Market Improvements
- Add self-serve signup, tenant provisioning, and Stripe checkout.
- Add onboarding checklists for sources, roles, prompts, and scheduler setup.
- Add compliance assets: data processing addendum, retention policy, incident response policy, subprocessors, and security overview.
- Add quality reporting: answered rate, citation coverage, top failed questions, stale sources, and retrieval confidence.
- Add connectors after the web crawler is stable: Google Drive, SharePoint, Confluence, Notion, Canvas, Moodle, and public sitemap import.

## Roadmap
- Phase 1: secure tenant APIs, billing foundation, usage metering, docs, and production configuration.
- Phase 2: Keycloak OIDC, invitation onboarding, Stripe checkout and webhooks, and billing UI.
- Phase 3: vLLM and BGE-M3 production AI gateway, quality evaluation, and prompt/version governance.
- Phase 4: GCP deployment automation, observability, backups, load testing, and compliance hardening.
