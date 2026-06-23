# Repository Structure

This workspace has three active application roots:

- `core_backend/` - Django REST API for tenants, users, roles, API keys, ingestion schedules, and auth.
- `rag_backend/` - FastAPI RAG/chat API plus Celery tasks for ingestion and scheduled jobs.
- `frontend/` - Next.js tenant portal.

Supporting files live at the repository root:

- `docker-compose.yml` - full local stack, including Postgres, MongoDB, Redis, Qdrant, Ollama, both backends, Celery, and the frontend.
- `.env.example` - complete development environment template.
- `.env` - local development values. This file is ignored and should not be committed.
- `Makefile` - common Docker, setup, migration, seed, run, and test commands.
- `docs/` - product strategy, architecture diagrams, workflow diagrams, API contracts, security/compliance notes, roadmap, runbook, and maintenance notes.

Legacy cleanup candidates still present for manual confirmation:

- `core/` and root `manage.py` appear to be an older Django scaffold. The active Django app is `core_backend/`.
- `frontend/.git/` is a nested Git repository. Remove it only if you want this whole workspace managed as one repository.

Local/generated folders are intentionally ignored:

- `.venv/` and `**/venv/`
- `frontend/node_modules/`
- `frontend/.next/`
- `__pycache__/`, `.pytest_cache/`, `*.pyc`
- `db.sqlite3`, `*.sqlite3`, `celerybeat-schedule`

Use one root Python virtual environment for local development:

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r core_backend\requirements.txt -r rag_backend\requirements.txt
```

The Docker workflow does not require a local Python virtual environment.
