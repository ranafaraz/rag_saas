.PHONY: up down reset logs setup seed test pull-models \
        run-core run-rag run-celery run-frontend \
        migrate test-core test-rag

PYTHON := .\.venv\Scripts\python.exe
PIP := .\.venv\Scripts\pip.exe
UVICORN := .\.venv\Scripts\uvicorn.exe
CELERY := .\.venv\Scripts\celery.exe

# ─── Docker ──────────────────────────────────────────────────────────────────
up:
	docker-compose up -d

down:
	docker-compose down

reset:
	docker-compose down -v

logs:
	docker-compose logs -f

ps:
	docker-compose ps

# ─── One-time setup ───────────────────────────────────────────────────────────
setup:
	@if not exist .env (copy .env.example .env && echo ".env created from .env.example") else (echo ".env already exists")
	@if not exist .venv (python -m venv .venv && echo ".venv created") else (echo ".venv already exists")
	$(PIP) install -r core_backend/requirements.txt -r rag_backend/requirements.txt

# Pull Ollama models (run once after `make up`)
pull-models:
	docker-compose exec ollama ollama pull nomic-embed-text
	docker-compose exec ollama ollama pull llama3.2:3b

# ─── DB / seed ────────────────────────────────────────────────────────────────
migrate:
	cd core_backend && ..\$(PYTHON) manage.py migrate --noinput

seed:
	cd core_backend && ..\$(PYTHON) manage.py seed

# ─── Local development runners ────────────────────────────────────────────────
run-core:
	cd core_backend && ..\$(PYTHON) manage.py runserver 0.0.0.0:8000

run-rag:
	cd rag_backend && ..\$(UVICORN) main:app --host 0.0.0.0 --port 8001 --reload

run-celery:
	cd rag_backend && ..\$(CELERY) -A celery_app worker --loglevel=info -P solo

run-frontend:
	cd frontend && npm run dev

# ─── Tests ───────────────────────────────────────────────────────────────────
test-core:
	cd core_backend && ..\$(PYTHON) manage.py test saas -v 2

test-rag:
	cd rag_backend && ..\$(PYTHON) -m pytest tests/ -v

test: test-core test-rag
	@echo "All tests completed."
