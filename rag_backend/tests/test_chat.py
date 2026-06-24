"""
FastAPI test suite for the RAG engine.

External services (Ollama, Qdrant, MongoDB, Django auth) are mocked
so the tests can run without any infrastructure.
"""
import json
import sys
import os
import unittest
import tempfile
from unittest.mock import patch, MagicMock, AsyncMock

# ── Ensure the rag_backend package root is importable ────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Patch slow/external imports before FastAPI loads them ─────────────────────
FAKE_CREDS = {
    "tenant_id": "tenant-aaa",
    "api_key_id": "key-aaa",
    "api_key_prefix": "sk_test_aa",
    "roles": ["Student"],
    "scopes": ["query", "stream", "ingest", "usage"],
    "usage": {
        "entitlements": {
            "chat_messages": {"limit": 100, "used": 0},
            "ingestion_runs": {"limit": 100, "used": 0},
            "documents": {"limit": 100, "used": 0},
        }
    },
}


from fastapi.testclient import TestClient
import main
from main import app, UPLOAD_DIR
from auth import verify_credentials

app.dependency_overrides[verify_credentials] = lambda: FAKE_CREDS
main._resp_cache_client = False

client = TestClient(app)


class TestHealth(unittest.TestCase):
    def test_health_check(self):
        resp = client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "healthy")


class TestChatAuth(unittest.TestCase):
    def test_chat_requires_auth(self):
        """Without Authorization header, HTTPBearer returns 403."""
        app.dependency_overrides.pop(verify_credentials, None)
        try:
            resp = client.post("/chat", json={"query": "hello"})
            self.assertEqual(resp.status_code, 401)
        finally:
            app.dependency_overrides[verify_credentials] = lambda: FAKE_CREDS

    def test_chat_empty_query_rejected(self):
        """Pydantic rejects blank query before the handler runs."""
        resp = client.post(
            "/chat",
            json={"query": "   "},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )
        self.assertEqual(resp.status_code, 422)


class TestChatFlow(unittest.TestCase):
    @patch("services.retrieval.retrieve_chunks")
    @patch("services.llm.generate_rag_answer")
    @patch("main.log_request")
    def test_chat_returns_answer_with_citations(self, mock_log, mock_gen, mock_ret):
        mock_ret.return_value = [
            {"content": "Fall deadline is Nov 1.", "score": 0.9,
             "metadata": {"title": "Admissions Policy", "source": "file.txt"}}
        ]
        mock_gen.return_value = (
            "The fall deadline is November 1st. [Citation 1]",
            [{"id": 1, "title": "Admissions Policy", "source": "file.txt", "score": 0.9}],
        )

        resp = client.post(
            "/chat",
            json={"query": "When is the fall deadline?"},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["insufficient_evidence"])
        self.assertIn("November", body["answer"])
        self.assertEqual(len(body["citations"]), 1)
        self.assertEqual(body["citations"][0]["id"], 1)
        mock_log.assert_called_once()

    @patch("services.retrieval.retrieve_chunks")
    @patch("main.log_request")
    def test_chat_fallback_when_no_chunks(self, mock_log, mock_ret):
        mock_ret.return_value = []

        resp = client.post(
            "/chat",
            json={"query": "What is the airspeed velocity of a swallow?"},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["insufficient_evidence"])
        self.assertEqual(body["citations"], [])

    @patch("services.retrieval.retrieve_chunks")
    @patch("services.llm.generate_rag_answer")
    @patch("main.log_request")
    def test_chat_filters_irrelevant_policy_chunk(self, mock_log, mock_gen, mock_ret):
        mock_ret.return_value = [
            {
                "content": "Admissions Policy: Fall deadline is November 1st. Application fee is $50.",
                "score": 0.87,
                "metadata": {"title": "Admissions Policy", "source": "file.txt"},
            }
        ]

        resp = client.post(
            "/chat",
            json={"query": "Explain grading curve rubric"},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["insufficient_evidence"])
        self.assertEqual(body["citations"], [])
        mock_gen.assert_not_called()
        mock_log.assert_called_once()

    @patch("services.retrieval.retrieve_chunks")
    @patch("services.llm.generate_rag_answer")
    @patch("main.log_request")
    def test_chat_blocks_generic_identity_query(self, mock_log, mock_gen, mock_ret):
        mock_ret.return_value = [
            {
                "content": "Rana Faraz Ahmed is a software engineer.",
                "score": 0.92,
                "metadata": {"title": "LinkedIn Profile.pdf", "source": "http://localhost:8001/files/profile.pdf"},
            }
        ]

        resp = client.post(
            "/chat",
            json={"query": "who are you?"},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["insufficient_evidence"])
        self.assertEqual(body["citations"], [])
        self.assertIn("tenant knowledge assistant", body["answer"].lower())
        mock_ret.assert_not_called()
        mock_gen.assert_not_called()
        mock_log.assert_called_once()

    @patch("services.retrieval.retrieve_chunks")
    @patch("services.llm.generate_rag_answer")
    @patch("main.log_request")
    def test_chat_self_identity_uses_assistant_profile(self, mock_log, mock_gen, mock_ret):
        app.dependency_overrides[verify_credentials] = lambda: {
            "tenant_id": "tenant-aaa",
            "roles": ["Student"],
            "base_prompt": "You are the RAG SaaS assistant for Stanford University Demo. Keep answers concise.",
        }
        try:
            resp = client.post(
                "/chat",
                json={"query": "who are you?"},
                headers={"Authorization": "Bearer sk_su_stu_demo"},
            )
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertIn("RAG SaaS assistant", body["answer"])
            self.assertFalse(body["insufficient_evidence"])
            self.assertEqual(body["citations"], [])
            mock_ret.assert_not_called()
            mock_gen.assert_not_called()
            mock_log.assert_called_once()
        finally:
            app.dependency_overrides[verify_credentials] = lambda: FAKE_CREDS

    @patch("services.retrieval.retrieve_chunks")
    @patch("services.llm.generate_rag_answer")
    @patch("main.log_request")
    def test_chat_person_lookup_allows_relevant_named_query(self, mock_log, mock_gen, mock_ret):
        mock_ret.return_value = [
            {
                "content": "Rana Faraz Ahmed is a software engineer with experience in data systems.",
                "score": 0.27,
                "metadata": {
                    "title": "LinkedIn Profile.pdf",
                    "source": "http://localhost:8001/files/linkedin.pdf",
                },
            }
        ]
        mock_gen.return_value = (
            "Rana Faraz Ahmed is a software engineer with experience in data systems. [Citation 1]",
            [
                {
                    "id": 1,
                    "title": "LinkedIn Profile.pdf",
                    "source": "http://localhost:8001/files/linkedin.pdf",
                    "score": 0.27,
                }
            ],
        )

        resp = client.post(
            "/chat",
            json={"query": "Who is Rana Faraz Ahmed?"},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["insufficient_evidence"])
        self.assertIn("Rana Faraz Ahmed", body["answer"])
        self.assertEqual(len(body["citations"]), 1)
        mock_gen.assert_called_once()
        mock_log.assert_called_once()


class TestPublicV1Api(unittest.TestCase):
    @patch("services.retrieval.retrieve_chunks")
    @patch("services.llm.generate_rag_answer")
    @patch("main.record_rag_trace")
    @patch("main.log_request")
    def test_v1_query_returns_chat_response(self, mock_log, mock_trace, mock_gen, mock_ret):
        mock_ret.return_value = [
            {"content": "Refunds are available within 30 days.", "score": 0.91,
             "metadata": {"title": "Refund Policy", "source": "policy.txt"}}
        ]
        mock_gen.return_value = (
            "Refunds are available within 30 days. [Citation 1]",
            [{"id": 1, "title": "Refund Policy", "source": "policy.txt", "score": 0.91}],
        )
        resp = client.post("/v1/query", json={"query": "What is the refund policy?"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["citations"]), 1)

    def test_v1_query_requires_scope(self):
        app.dependency_overrides[verify_credentials] = lambda: {**FAKE_CREDS, "scopes": ["usage"]}
        try:
            resp = client.post("/v1/query", json={"query": "hello"})
            self.assertEqual(resp.status_code, 403)
        finally:
            app.dependency_overrides[verify_credentials] = lambda: FAKE_CREDS

    def test_v1_query_blocks_exceeded_quota(self):
        app.dependency_overrides[verify_credentials] = lambda: {
            **FAKE_CREDS,
            "usage": {"entitlements": {"chat_messages": {"limit": 1, "used": 1}}},
        }
        try:
            resp = client.post("/v1/query", json={"query": "hello"})
            self.assertEqual(resp.status_code, 402)
        finally:
            app.dependency_overrides[verify_credentials] = lambda: FAKE_CREDS

    @patch("main.record_integration_job")
    @patch("main.record_usage_event")
    @patch("main.ingest_urls_task")
    def test_v1_sources_queues_ingestion(self, mock_task, mock_usage, mock_job):
        mock_task.delay.return_value = MagicMock(id="task-url-1")
        resp = client.post(
            "/v1/sources",
            json={"title": "Docs", "url": "https://example.com/docs", "roles": ["Student"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["job_id"], "task-url-1")
        mock_task.delay.assert_called_once()

    @patch("main.record_integration_job")
    @patch("main.record_usage_event")
    @patch("main.ingest_document_task")
    def test_v1_documents_queues_inline_document(self, mock_task, mock_usage, mock_job):
        mock_task.delay.return_value = MagicMock(id="task-doc-1")
        resp = client.post(
            "/v1/documents",
            json={"title": "Inline", "content": "Knowledge base text", "roles": ["Student"]},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["job_id"], "task-doc-1")
        mock_task.delay.assert_called_once()

    def test_v1_usage_returns_claim_payload(self):
        resp = client.get("/v1/usage")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["tenant_id"], "tenant-aaa")


class TestIngestionFileEndpoint(unittest.TestCase):
    @patch("main.ingest_document_task")
    def test_file_upload_queued(self, mock_task):
        mock_task.delay.return_value = MagicMock(id="task-123")

        import io
        resp = client.post(
            "/ingest/file",
            data={"tenant_id": "tenant-aaa", "title": "Test doc", "roles": "Student"},
            files={"file": ("test.txt", io.BytesIO(b"Hello knowledge"), "text/plain")},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["filename"], "test.txt")
        mock_task.delay.assert_called_once()

    @patch("main.ingest_document_task")
    def test_file_wrong_extension_rejected(self, _mock):
        import io
        resp = client.post(
            "/ingest/file",
            data={"tenant_id": "tenant-aaa", "title": "bad", "roles": "Student"},
            files={"file": ("malware.exe", io.BytesIO(b"bad"), "application/octet-stream")},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )
        self.assertEqual(resp.status_code, 422)

    @patch("main.ingest_document_task")
    def test_cross_tenant_ingestion_forbidden(self, _mock):
        import io
        resp = client.post(
            "/ingest/file",
            data={"tenant_id": "tenant-BBB", "title": "evil doc", "roles": "Admin"},
            files={"file": ("doc.txt", io.BytesIO(b"data"), "text/plain")},
            headers={"Authorization": "Bearer sk_su_stu_demo"},
        )
        # tenant-aaa (from FAKE_CREDS) != tenant-BBB => 403
        self.assertEqual(resp.status_code, 403)


class TestCitationFileAccess(unittest.TestCase):
    def test_file_endpoint_requires_tenant_prefix(self):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="tenant-bbb_", suffix="_secret.txt", dir=UPLOAD_DIR, delete=False) as tmp:
            tmp.write(b"secret")
            file_name = os.path.basename(tmp.name)
        try:
            resp = client.get(f"/files/{file_name}", headers={"Authorization": "Bearer sk_su_stu_demo"})
            self.assertEqual(resp.status_code, 403)
        finally:
            os.unlink(tmp.name)

    def test_file_endpoint_allows_inline_open_for_owner(self):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="tenant-aaa_", suffix="_doc.txt", dir=UPLOAD_DIR, delete=False) as tmp:
            tmp.write(b"hello")
            file_name = os.path.basename(tmp.name)
        try:
            resp = client.get(f"/files/{file_name}", headers={"Authorization": "Bearer sk_su_stu_demo"})
            self.assertEqual(resp.status_code, 200)
            self.assertIn("inline", resp.headers.get("content-disposition", ""))
        finally:
            os.unlink(tmp.name)

    def test_file_endpoint_supports_download_mode(self):
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="tenant-aaa_", suffix="_dl.txt", dir=UPLOAD_DIR, delete=False) as tmp:
            tmp.write(b"download")
            file_name = os.path.basename(tmp.name)
        try:
            resp = client.get(f"/files/{file_name}?download=true", headers={"Authorization": "Bearer sk_su_stu_demo"})
            self.assertEqual(resp.status_code, 200)
            self.assertIn("attachment", resp.headers.get("content-disposition", ""))
        finally:
            os.unlink(tmp.name)


if __name__ == "__main__":
    unittest.main()
