# Build State — World-Class RAG SaaS Upgrade

Tracks the multi-phase upgrade planned in
`~/.claude/plans/critically-audit-the-system-glittery-mccarthy.md`.
Goal: production multi-tenancy (kill demo `tenant_id` switching), free no-GPU LLM
tier + BYOK, beautiful UI, and an onboarding tour.

## ✅ Phase 1 — Production multi-tenancy & auth (DONE, tested)

Active tenant is now derived from a **verified `Membership`**, never from a
client-supplied `tenant_id`. 33 Django tests pass (`POSTGRES_DB="" python manage.py test saas`).

- **Model** `Membership(user, tenant, role[owner/admin/member], roles M2M, status, onboarding_state, invited_by)` — `core_backend/saas/models.py`. Source of truth for workspace access. `User.tenant` kept only as a "last active" pointer (`on_delete=SET_NULL`); added `User.is_email_verified`.
- **Auth class** `WorkspaceJWTAuthentication` (`core_backend/saas/authentication.py`) reads the JWT `tenant_id` claim, verifies an active Membership, and sets request-scoped active tenant + roles (`user._active_role_names`, `user._active_is_admin`). Registered in `settings.py` REST_FRAMEWORK (replaced plain SimpleJWT). Permissions/`_tenant_roles` prefer these.
- **Endpoints** (`core_backend/saas/views.py`, routes in `urls.py`):
  - `POST /api/auth/login/` → identity token + `workspaces[]` (NO tenant_id accepted; supports email login).
  - `POST /api/auth/workspace/` → exchanges identity token for a workspace-scoped token (membership verified).
  - `GET /api/auth/workspaces/`, `POST /api/auth/workspaces/create/`, `POST /api/auth/verify-email/`, `POST /api/auth/invitations/accept/`.
  - `VerifyUserTokenView` rewritten: tenant from claim + membership; rejects identity tokens.
  - `SignupView` now creates an owner Membership + sends verification email.
- **Migrations** `0008` (schema) + `0009` (data backfill of Membership from `User.tenant`). Apply with `POSTGRES_DB="" python manage.py migrate`.
- **Seed** (`management/commands/seed.py`) creates Memberships + marks demo users verified.
- **Tests** `WorkspaceAuthTests` in `saas/tests.py` (7): non-member can't enter a foreign workspace by slug or raw id; identity token can't read tenant data; cross-tenant object access blocked; verify endpoint rejects identity tokens.

## ✅ Phase 2 — Pluggable LLM + BYOK + savings (DONE, tested)

- **Provider registry** `rag_backend/providers/` — `base.py`, `registry.py` (`get_provider`/`resolve_config`), `openai_compatible.py` (Groq/OpenAI/DeepSeek/vLLM/custom), `anthropic_provider.py`, `ollama_provider.py`. Default = **Groq** free tier; **auto-falls back to Ollama** when no key. SDK imports are lazy (importing the package needs no extra deps).
- **llm.py** `generate_rag_answer`/`stream_rag_answer` take an optional `llm_config` and use the registry; prompt + citations + "insufficient evidence" logic unchanged. `main.py` passes `creds.get("generation_config")`.
- **BYOK**: `AIModelConfig` gained `api_key_ciphertext` (Fernet via `core_backend/saas/encryption.py`, key from `FIELD_ENCRYPTION_KEY`) + broader `PROVIDER_CHOICES`. Serializer is write-only `api_key` / read-only `api_key_hint` (`••••1234`); `exclude=['api_key_ciphertext']`. Core verify endpoints return a decrypted `generation_config` over the trusted internal channel.
- **Savings dashboard** `GET /api/usage/savings/` (`UsageSavingsView`) aggregates `RAGTrace`+`UsageEvent` → queries, grounded/refusal rate, latency, est. cost vs GPT-4-class, est. savings + energy (transparent assumptions).
- **Env** (`.env.example`): `LLM_PROVIDER=groq`, `GROQ_API_KEY/MODEL/BASE_URL`, OpenAI/Anthropic/DeepSeek vars, `FIELD_ENCRYPTION_KEY`, `FRONTEND_URL`. `rag_backend/requirements.txt` adds `anthropic`; `core_backend/requirements.txt` adds `cryptography`.
- **Tests** `Phase2LLMConfigTests` (3): key encrypted + never returned raw; generation_config reaches verify endpoint; savings aggregates.

## ✅ Phase 3 — UI rebuild (DONE)

**Next.js 16.2.1 App Router** + Tailwind v4 + custom design system (no shadcn/ui CLI needed).
All files under `frontend/src/`.

**Key files created/replaced:**
- `lib/types.ts` — all shared types (PortalSession, SessionUser, Workspace, WorkspaceData, AIModelConfig, SavingsData, Message, Citation, ScheduleRow, RAGTraceRow, …)
- `lib/api.ts` — `CORE_API`, `RAG_API`, `makeAuthHeaders`, `apiGet/Post/Patch/Delete`, `formatDate`, `buildCitationUrl`, `setWsCookie`, `clearWsCookie`, `SESSION_KEY`, `IDENTITY_KEY`
- `lib/auth-store.tsx` — `AuthProvider` + `useAuth()` + `useRequireAuth()`. Bootstrap validates stored token via `POST /api/auth/verify-user-token/`. `persistSession` sets localStorage + `ws_slug` cookie. `onSessionExpired` clears both.
- `lib/workspace-context.tsx` — `WorkspaceProvider` + `useWorkspace()`. Loads all workspace data in parallel (roles, users, apiKeys, documents, sources, schedules, prompts, runLogs, jobs, traces, members, aiModels, billing, savings).
- `app/globals.css` — Tailwind v4 (`@import 'tailwindcss'`) + comprehensive design system (tokens, layout, auth shell, ws switcher, badges, buttons, fields, chat, tables, metrics, savings, model cards, log list, empty states, checklist, responsive).
- `app/layout.tsx` — wraps in `<AuthProvider>`.
- `app/page.tsx` — client redirect to `/w/{slug}/chat` or `/login`.
- `proxy.ts` — Next.js 16 proxy (NOT `middleware.ts`); protects `/w/[slug]/**` with `ws_slug` cookie; redirects logged-in users away from auth pages.
- `(auth)/layout.tsx`, `(auth)/login/page.tsx` — two-step login (identity token → workspace selection → access_token).
- `(auth)/signup/page.tsx` — registration → "check email" state.
- `(auth)/verify/page.tsx` — reads `?token=`, POSTs to `/api/auth/verify-email/`, redirects.
- `(auth)/select-workspace/page.tsx` — workspace picker after multi-workspace login.
- `(app)/w/[slug]/layout.tsx` — client layout; loads workspace switcher from `GET /api/auth/workspaces/`; wraps in `WorkspaceProvider`; sidebar with profile, nav (Chat/Sources/Schedules/AI Models/Usage/Members), roles, onboarding checklist.
- `(app)/w/[slug]/page.tsx` — server component; `await params`; redirects to `/w/{slug}/chat`.
- `(app)/w/[slug]/chat/page.tsx` — SSE streaming chat; citation open/download; prompt chips; empty state.
- `(app)/w/[slug]/sources/page.tsx` — knowledge sources list + URL source + schedule create form.
- `(app)/w/[slug]/schedules/page.tsx` — schedule table with pause/resume/run-now; run log.
- `(app)/w/[slug]/models/page.tsx` — AIModelConfig cards + BYOK add form (write-only key); free-tier callout.
- `(app)/w/[slug]/usage/page.tsx` — savings callout, quality metrics, cost comparison table, RAG traces.
- `(app)/w/[slug]/members/page.tsx` — member table + invite form.

**Breaking-change notes applied:**
- `proxy.ts` (not `middleware.ts`) with `export function proxy(...)` per Next.js 16 docs.
- Dynamic route params: `await params` in server components.
- Tailwind v4: `@import 'tailwindcss'` in globals.css.

## ✅ Phase 4 — Onboarding (DONE)

- `components/onboarding-tour.tsx` — driver.js tour; lazy-imports driver.js; runs once per workspace (keyed by slug in localStorage `rag_tour_done_v2_{slug}`); tours chat → sources → models → usage; marks done on close.
- `components/onboarding-checklist.tsx` — data-driven checklist (create workspace / add source / ask first question / invite member); derived from WorkspaceProvider data (no backend needed); disappears when all 4 steps done.
- Both mounted in the workspace layout sidebar. Empty states on all 6 panels.

## How to run / verify
- Core tests: `cd core_backend && POSTGRES_DB="" python manage.py test saas` (sqlite; `POSTGRES_DB=""` neutralizes the root `.env` which points at the `postgres` docker host). Keycloak env is disabled inside the new tests.
- Full stack: `docker-compose up` + `npm run dev` in `frontend`. Set `GROQ_API_KEY` for the real free tier (else Ollama fallback).
