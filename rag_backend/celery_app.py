from celery import Celery
from config import settings
import uuid
import sys
import os
import requests

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

celery_app = Celery(
    "rag_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_default_queue='default',
    beat_schedule={
        'trigger-due-ingestions-every-minute': {
            'task': 'rag_backend.celery_app.trigger_due_ingestions_task',
            'schedule': 60.0,
        },
    },
)

@celery_app.task(bind=True)
def ingest_document_task(self, tenant_id: str, title: str, roles: list, source_type: str, source_uri: str):
    """
    Downloads/Reads from source_uri using Unstructured.
    Chunks the text.
    Embeds using sentence-transformers.
    Upserts into Qdrant with payload: {tenant_id, roles, doc_id, text}.
    """
    task_root = os.path.dirname(os.path.abspath(__file__))
    if task_root not in sys.path:
        sys.path.insert(0, task_root)
    from services.ingestion import run_ingestion_pipeline
    
    try:
        run_ingestion_pipeline(tenant_id, title, roles, source_type, source_uri)
        return {"status": "success"}
    except Exception as e:
        self.retry(exc=e, countdown=10, max_retries=3)


@celery_app.task(bind=True)
def ingest_urls_task(self, tenant_id: str, title: str, roles: list, source_uris: list, crawl_options: dict | None = None):
    task_root = os.path.dirname(os.path.abspath(__file__))
    if task_root not in sys.path:
        sys.path.insert(0, task_root)
    from services.ingestion import run_multi_url_ingestion

    try:
        result = run_multi_url_ingestion(tenant_id, title, roles, source_uris, crawl_options=crawl_options)
        return {"status": "success", **result}
    except Exception as e:
        self.retry(exc=e, countdown=10, max_retries=3)


@celery_app.task(name='rag_backend.celery_app.trigger_due_ingestions_task')
def trigger_due_ingestions_task():
    core_api_url = os.getenv("CORE_API_URL", "http://localhost:8000")
    scheduler_token = os.getenv("SCHEDULER_TRIGGER_TOKEN", "")
    core_api_host_header = os.getenv("CORE_API_HOST_HEADER", "localhost")
    if not scheduler_token:
        return {"status": "skipped", "reason": "SCHEDULER_TRIGGER_TOKEN not configured"}

    try:
        response = requests.post(
            f"{core_api_url}/api/ingestion-schedules/run_due/",
            headers={
                "X-Scheduler-Token": scheduler_token,
                "Host": core_api_host_header,
            },
            timeout=20,
        )
        if response.status_code != 200:
            return {"status": "failed", "code": response.status_code, "body": response.text[:200]}
        return {"status": "success", **response.json()}
    except Exception as exc:
        return {"status": "failed", "error": str(exc)}
