from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.hashers import make_password
from .models import (
    Tenant,
    Plan,
    Subscription,
    Role,
    User,
    ApiKey,
    Document,
    IngestionSource,
    IngestionSchedule,
    IngestionRunLog,
    UsageEvent,
    Entitlement,
)
import secrets
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch


def _gen_key(prefix: str = "sk_test_") -> str:
    """Generate a random test API key — never hardcoded."""
    return prefix + secrets.token_urlsafe(16)


def _create_api_key(tenant, roles, raw_key: str, name: str = "Test key") -> ApiKey:
    key = ApiKey.objects.create(
        tenant=tenant,
        name=name,
        key_prefix=raw_key[:10],
        hashed_key=make_password(raw_key),
        scopes=["query", "stream", "ingest", "usage"],
        is_active=True,
    )
    key.roles.set(roles)
    return key


def _activate_subscription(tenant, code: str = "test-plan"):
    plan, _ = Plan.objects.update_or_create(
        code=code,
        defaults={
            "name": code.replace("-", " ").title(),
            "monthly_price_cents": 9900,
            "seat_limit": 10,
            "document_quota": 200,
            "source_quota": 20,
            "ingestion_runs_per_month": 100,
            "chat_messages_per_month": 1000,
        },
    )
    subscription, _ = Subscription.objects.update_or_create(
        tenant=tenant,
        defaults={
            "plan": plan,
            "status": "active",
            "current_period_start": timezone.now(),
            "current_period_end": timezone.now() + timedelta(days=30),
        },
    )
    subscription.apply_plan_defaults()
    subscription.save()
    for feature, limit in {
        "seats": subscription.seat_limit,
        "documents": subscription.document_quota,
        "sources": subscription.source_quota,
        "ingestion_runs": subscription.ingestion_runs_per_month,
        "chat_messages": subscription.chat_messages_per_month,
    }.items():
        Entitlement.objects.update_or_create(
            tenant=tenant,
            feature=feature,
            defaults={"limit": limit, "source": "test"},
        )
    return subscription


def _tenant_admin(tenant, role):
    user = User.objects.create_user(
        username=f"admin-{tenant.id}",
        email=f"admin-{tenant.id}@example.com",
        password="password123",
        tenant=tenant,
        is_tenant_admin=True,
    )
    user.roles.set([role])
    return user


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant_a = Tenant.objects.create(name="Tenant A")
        self.tenant_b = Tenant.objects.create(name="Tenant B")
        self.role_a = Role.objects.create(tenant=self.tenant_a, name="Admin")
        self.role_b = Role.objects.create(tenant=self.tenant_b, name="Student")
        self.user_a = _tenant_admin(self.tenant_a, self.role_a)
        self.client.force_authenticate(self.user_a)

    def test_tenants_are_created(self):
        self.assertEqual(Tenant.objects.count(), 2)

    def test_role_is_scoped_to_correct_tenant(self):
        self.assertEqual(self.role_a.tenant, self.tenant_a)
        self.assertNotEqual(self.role_a.tenant, self.tenant_b)

    def test_roles_filtered_by_tenant(self):
        """Role list filtered by tenant param must exclude the other tenant's roles."""
        resp = self.client.get(f"/api/roles/?tenant={self.tenant_a.id}")
        self.assertEqual(resp.status_code, 200)
        names = [r["name"] for r in resp.data["results"]]
        self.assertIn("Admin", names)
        self.assertNotIn("Student", names)

    def test_unauthenticated_role_list_is_rejected(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get(f"/api/roles/?tenant={self.tenant_a.id}")
        self.assertIn(resp.status_code, {401, 403})

    def test_api_key_scoped_to_tenant(self):
        raw = _gen_key()
        key = _create_api_key(self.tenant_a, [self.role_a], raw)
        self.assertEqual(key.tenant, self.tenant_a)

    def test_api_key_list_filtered(self):
        raw_a = _gen_key("sk_a_")
        raw_b = _gen_key("sk_b_")
        _create_api_key(self.tenant_a, [self.role_a], raw_a, "A key")
        _create_api_key(self.tenant_b, [self.role_b], raw_b, "B key")
        resp = self.client.get(f"/api/api-keys/?tenant={self.tenant_a.id}")
        self.assertEqual(resp.status_code, 200)
        for item in resp.data["results"]:
            self.assertEqual(str(item["tenant"]), str(self.tenant_a.id))


class ApiKeyVerifyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Verify Tenant")
        self.role = Role.objects.create(tenant=self.tenant, name="Faculty")
        self.raw_key = _gen_key("sk_fac_")  # random per test run
        _create_api_key(self.tenant, [self.role], self.raw_key, "Faculty demo key")
        _activate_subscription(self.tenant, "verify-plan")

    def test_valid_key_returns_tenant_and_role(self):
        resp = self.client.post("/api/auth/verify/", {"token": self.raw_key}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(str(resp.data["tenant_id"]), str(self.tenant.id))
        self.assertIn("Faculty", resp.data["roles"])

    def test_wrong_key_returns_401(self):
        resp = self.client.post("/api/auth/verify/", {"token": "sk_wrong_____XXXXX"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_inactive_key_returns_401(self):
        ApiKey.objects.filter(key_prefix=self.raw_key[:10]).update(is_active=False)
        resp = self.client.post("/api/auth/verify/", {"token": self.raw_key}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_inactive_subscription_blocks_api_key(self):
        Subscription.objects.filter(tenant=self.tenant).update(status="canceled")
        resp = self.client.post("/api/auth/verify/", {"token": self.raw_key}, format="json")
        self.assertEqual(resp.status_code, 402)

    def test_missing_scope_returns_403(self):
        ApiKey.objects.filter(key_prefix=self.raw_key[:10]).update(scopes=["query"])
        resp = self.client.post("/api/auth/verify/", {"token": self.raw_key, "scope": "ingest"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_revoked_key_returns_401(self):
        ApiKey.objects.filter(key_prefix=self.raw_key[:10]).update(is_active=False, revoked_at=timezone.now())
        resp = self.client.post("/api/auth/verify/", {"token": self.raw_key}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_expired_key_returns_401(self):
        ApiKey.objects.filter(key_prefix=self.raw_key[:10]).update(expires_at=timezone.now() - timedelta(minutes=1))
        resp = self.client.post("/api/auth/verify/", {"token": self.raw_key}, format="json")
        self.assertEqual(resp.status_code, 401)


class SignupAndKeyLifecycleTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.plan = Plan.objects.create(
            code="developer-starter",
            name="Developer Starter",
            monthly_price_cents=0,
            seat_limit=5,
            document_quota=10,
            source_quota=5,
            ingestion_runs_per_month=10,
            chat_messages_per_month=100,
            is_public=True,
        )

    def test_signup_provisions_tenant_admin_subscription_and_key(self):
        resp = self.client.post(
            "/api/signup/",
            {
                "organization_name": "Acme Apps",
                "workspace_slug": "acme-apps",
                "admin_username": "acme-admin",
                "admin_email": "admin@acme.example",
                "admin_password": "super-secret-123",
                "plan_code": self.plan.code,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["tenant"]["slug"], "acme-apps")
        self.assertIn("raw_key", resp.data["api_key"])
        tenant = Tenant.objects.get(slug="acme-apps")
        self.assertTrue(Subscription.objects.filter(tenant=tenant, status="trialing").exists())
        self.assertTrue(User.objects.filter(tenant=tenant, is_tenant_admin=True).exists())

    def test_rotate_and_revoke_api_key(self):
        tenant = Tenant.objects.create(name="Key Tenant")
        role = Role.objects.create(tenant=tenant, name="Admin")
        user = _tenant_admin(tenant, role)
        self.client.force_authenticate(user)
        raw = _gen_key("sk_key_")
        key = _create_api_key(tenant, [role], raw)

        rotate = self.client.post(f"/api/api-keys/{key.id}/rotate/")
        self.assertEqual(rotate.status_code, 200)
        self.assertIn("raw_key", rotate.data)
        key.refresh_from_db()
        self.assertNotEqual(key.key_prefix, raw[:10])

        revoke = self.client.post(f"/api/api-keys/{key.id}/revoke/")
        self.assertEqual(revoke.status_code, 200)
        key.refresh_from_db()
        self.assertFalse(key.is_active)
        self.assertIsNotNone(key.revoked_at)


class DocumentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Doc Tenant")
        self.role = Role.objects.create(tenant=self.tenant, name="Student")
        self.user = _tenant_admin(self.tenant, self.role)
        self.client.force_authenticate(self.user)

    def test_document_creation(self):
        resp = self.client.post("/api/documents/", {
            "tenant": str(self.tenant.id),
            "title": "Admissions Guide",
            "source_type": "file",
            "source_uri": "/tmp/admissions.pdf",
            "roles": [str(self.role.id)],
            "status": "pending",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], "pending")

    def test_document_filtered_by_tenant(self):
        other_tenant = Tenant.objects.create(name="Other Tenant")
        Document.objects.create(
            tenant=self.tenant, title="My doc", source_type="file",
            source_uri="/tmp/a.pdf", status="completed",
        )
        Document.objects.create(
            tenant=other_tenant, title="Other doc", source_type="url",
            source_uri="https://example.com", status="completed",
        )
        resp = self.client.get(f"/api/documents/?tenant={self.tenant.id}")
        self.assertEqual(resp.status_code, 200)
        for item in resp.data["results"]:
            self.assertEqual(str(item["tenant"]), str(self.tenant.id))


class IngestionSchedulerTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Scheduler Tenant")
        self.role = Role.objects.create(tenant=self.tenant, name="Admin")
        self.user = _tenant_admin(self.tenant, self.role)
        self.client.force_authenticate(self.user)
        _activate_subscription(self.tenant, "scheduler-plan")
        raw = _gen_key("sk_su_adm_")
        self.api_key = _create_api_key(self.tenant, [self.role], raw, "Demo Admin Key")
        self.source = IngestionSource.objects.create(
            tenant=self.tenant,
            name="Admissions Feed",
            source_type="url",
            config={"urls": ["https://example.edu/admissions"]},
        )

    def test_create_ingestion_schedule(self):
        resp = self.client.post(
            "/api/ingestion-schedules/",
            {
                "tenant": str(self.tenant.id),
                "source": str(self.source.id),
                "api_key": str(self.api_key.id),
                "title": "Admissions Sync",
                "roles": [str(self.role.id)],
                "frequency": "hourly",
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        schedule = IngestionSchedule.objects.get(id=resp.data["id"])
        self.assertIsNotNone(schedule.next_run_at)

    @patch("saas.views.requests.post")
    def test_run_now_action_creates_log(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"task_id": "task-1"}

        schedule = IngestionSchedule.objects.create(
            tenant=self.tenant,
            source=self.source,
            api_key=self.api_key,
            title="Admissions Sync",
            frequency="daily",
            next_run_at=timezone.now(),
            is_active=True,
        )
        schedule.roles.add(self.role)

        resp = self.client.post(f"/api/ingestion-schedules/{schedule.id}/run_now/")
        self.assertEqual(resp.status_code, 200)
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "success")
        self.assertTrue(IngestionRunLog.objects.filter(schedule=schedule, status="success").exists())

    @patch("saas.views._trigger_schedule_ingestion")
    def test_run_due_ingestions_command_updates_due_schedule(self, mock_trigger):
        mock_trigger.return_value = ("success", "Queued task task-123")
        schedule = IngestionSchedule.objects.create(
            tenant=self.tenant,
            source=self.source,
            api_key=self.api_key,
            title="Daily Sync",
            frequency="daily",
            next_run_at=timezone.now() - timedelta(minutes=1),
            is_active=True,
        )

        from django.core.management import call_command
        call_command("run_due_ingestions")

        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, "success")
        self.assertIsNotNone(schedule.last_run_at)
        self.assertGreater(schedule.next_run_at, schedule.last_run_at)


class UsageRecordingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Usage Tenant")
        self.role = Role.objects.create(tenant=self.tenant, name="Admin")
        self.user = _tenant_admin(self.tenant, self.role)
        _activate_subscription(self.tenant, "usage-plan")

    def test_internal_usage_record_requires_token(self):
        resp = self.client.post(
            "/api/usage-events/record/",
            {"tenant": str(self.tenant.id), "event_type": "chat_message", "quantity": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)

    @patch.dict("saas.views.os.environ", {"RAG_INTERNAL_INGEST_TOKEN": "unused"})
    def test_internal_usage_record_creates_event(self):
        from saas import views

        old_token = views.RAG_INTERNAL_INGEST_TOKEN
        views.RAG_INTERNAL_INGEST_TOKEN = "test-token"
        try:
            resp = self.client.post(
                "/api/usage-events/record/",
                {"tenant": str(self.tenant.id), "event_type": "chat_message", "quantity": 2},
                HTTP_X_INGESTION_TOKEN="test-token",
                format="json",
            )
        finally:
            views.RAG_INTERNAL_INGEST_TOKEN = old_token
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(UsageEvent.objects.filter(tenant=self.tenant, event_type="chat_message").count(), 1)

    def test_usage_record_blocks_exceeded_chat_quota(self):
        from saas import views

        entitlement = self.tenant.entitlements.get(feature="chat_messages")
        entitlement.limit = 1
        entitlement.used = 1
        entitlement.save()
        old_token = views.RAG_INTERNAL_INGEST_TOKEN
        views.RAG_INTERNAL_INGEST_TOKEN = "test-token"
        try:
            resp = self.client.post(
                "/api/usage-events/record/",
                {"tenant": str(self.tenant.id), "event_type": "chat_message", "quantity": 1},
                HTTP_X_INGESTION_TOKEN="test-token",
                format="json",
            )
        finally:
            views.RAG_INTERNAL_INGEST_TOKEN = old_token
        self.assertEqual(resp.status_code, 402)


class WorkspaceAuthTests(TestCase):
    """Production tenancy: active tenant is derived from a verified Membership,
    never from a client-supplied tenant_id."""

    def setUp(self):
        import os
        from .models import Membership

        # Disable optional Keycloak OIDC auth so the local SimpleJWT path is exercised.
        self._env = patch.dict(os.environ, {"KEYCLOAK_JWKS_URL": "", "KEYCLOAK_AUDIENCE": ""})
        self._env.start()
        self.addCleanup(self._env.stop)

        self.client = APIClient()
        self.tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        self.tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
        _activate_subscription(self.tenant_a, "plan-a")
        _activate_subscription(self.tenant_b, "plan-b")
        self.role_a = Role.objects.create(tenant=self.tenant_a, name="Admin")
        self.role_b = Role.objects.create(tenant=self.tenant_b, name="Admin")

        # user_a belongs ONLY to tenant A.
        self.user_a = User.objects.create_user(
            username="alice", email="alice@example.com", password="password123",
            is_email_verified=True,
        )
        m = Membership.objects.create(user=self.user_a, tenant=self.tenant_a, role="owner", status="active")
        m.roles.add(self.role_a)

        # user_b belongs ONLY to tenant B (owns a document in B).
        self.user_b = User.objects.create_user(
            username="bob", email="bob@example.com", password="password123",
            is_email_verified=True,
        )
        mb = Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role="owner", status="active")
        mb.roles.add(self.role_b)
        self.doc_b = Document.objects.create(
            tenant=self.tenant_b, title="B secret", source_type="text", source_uri="x"
        )

    def _login(self, username, password="password123"):
        resp = self.client.post("/api/auth/login/", {"username": username, "password": password}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        return resp.data

    def test_login_does_not_accept_tenant_id_and_returns_workspaces(self):
        data = self._login("alice")
        self.assertIn("identity_token", data)
        # Login response is purely identity — it carries no workspace-scoped token.
        self.assertNotIn("access_token", data)
        slugs = {w["tenant_slug"] for w in data["workspaces"]}
        self.assertEqual(slugs, {"tenant-a"})

    def test_select_own_workspace_succeeds(self):
        identity = self._login("alice")["identity_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {identity}")
        resp = self.client.post("/api/auth/workspace/", {"workspace_slug": "tenant-a"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["workspace"]["tenant_slug"], "tenant-a")
        self.assertTrue(resp.data["access_token"])

    def test_cannot_select_foreign_workspace_even_with_slug_or_id(self):
        identity = self._login("alice")["identity_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {identity}")
        # By slug
        resp = self.client.post("/api/auth/workspace/", {"workspace_slug": "tenant-b"}, format="json")
        self.assertEqual(resp.status_code, 403, resp.data)
        # By raw id (the old injection vector)
        resp = self.client.post("/api/auth/workspace/", {"tenant_id": str(self.tenant_b.id)}, format="json")
        self.assertEqual(resp.status_code, 403, resp.data)

    def test_identity_token_cannot_touch_tenant_scoped_data(self):
        identity = self._login("alice")["identity_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {identity}")
        # No workspace selected -> no tenant scope -> empty results.
        resp = self.client.get("/api/documents/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 0)

    def test_workspace_token_scopes_to_membership_and_blocks_cross_tenant(self):
        # Alice enters tenant A; she must never see tenant B's document.
        identity = self._login("alice")["identity_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {identity}")
        ws = self.client.post("/api/auth/workspace/", {"workspace_slug": "tenant-a"}, format="json").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {ws['access_token']}")

        listing = self.client.get("/api/documents/")
        self.assertEqual(listing.data["count"], 0)
        # Direct object access to B's document is denied.
        detail = self.client.get(f"/api/documents/{self.doc_b.id}/")
        self.assertIn(detail.status_code, (403, 404))

    def test_verify_user_token_rejects_identity_token(self):
        identity = self._login("alice")["identity_token"]
        resp = self.client.post("/api/auth/verify-user-token/", {"token": identity}, format="json")
        self.assertEqual(resp.status_code, 401, resp.data)

    def test_verify_user_token_accepts_workspace_token_with_correct_tenant(self):
        identity = self._login("alice")["identity_token"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {identity}")
        ws = self.client.post("/api/auth/workspace/", {"workspace_slug": "tenant-a"}, format="json").data
        self.client.credentials()
        resp = self.client.post("/api/auth/verify-user-token/", {"token": ws["access_token"]}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["tenant_id"], str(self.tenant_a.id))


class Phase2LLMConfigTests(TestCase):
    """BYOK + usage savings: keys are never returned raw; savings endpoint works."""

    def setUp(self):
        import os
        from .models import Membership, AIModelConfig
        self._env = patch.dict(os.environ, {"KEYCLOAK_JWKS_URL": "", "KEYCLOAK_AUDIENCE": ""})
        self._env.start()
        self.addCleanup(self._env.stop)
        self.AIModelConfig = AIModelConfig

        self.client = APIClient()
        self.tenant = Tenant.objects.create(name="Acme", slug="acme")
        _activate_subscription(self.tenant, "acme-plan")
        self.role = Role.objects.create(tenant=self.tenant, name="Admin")
        self.user = User.objects.create_user(
            username="ada", email="ada@example.com", password="password123", is_email_verified=True,
        )
        m = Membership.objects.create(user=self.user, tenant=self.tenant, role="owner", status="active")
        m.roles.add(self.role)

    def _ws_client(self):
        login = self.client.post("/api/auth/login/", {"username": "ada", "password": "password123"}, format="json").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['identity_token']}")
        ws = self.client.post("/api/auth/workspace/", {"workspace_slug": "acme"}, format="json").data
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Bearer {ws['access_token']}")
        return c

    def test_byok_key_is_encrypted_and_never_returned_raw(self):
        c = self._ws_client()
        resp = c.post("/api/ai-model-configs/", {
            "tenant": str(self.tenant.id),
            "purpose": "generation",
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "api_key": "sk-supersecret-1234",
            "is_default": True,
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertNotIn("api_key", resp.data)
        self.assertNotIn("api_key_ciphertext", resp.data)
        self.assertEqual(resp.data.get("api_key_hint"), "••••1234")
        # Stored ciphertext must not equal the plaintext, and must decrypt back.
        cfg = self.AIModelConfig.objects.get(id=resp.data["id"])
        self.assertNotIn("supersecret", cfg.api_key_ciphertext)
        self.assertEqual(cfg.api_key, "sk-supersecret-1234")

    def test_generation_config_flows_to_verify_endpoint(self):
        c = self._ws_client()
        c.post("/api/ai-model-configs/", {
            "tenant": str(self.tenant.id), "purpose": "generation", "provider": "deepseek",
            "model_name": "deepseek-chat", "api_key": "sk-deep", "is_default": True,
        }, format="json")
        # The internal verify endpoint (used by rag_backend) must carry the decrypted config.
        login = self.client.post("/api/auth/login/", {"username": "ada", "password": "password123"}, format="json").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login['identity_token']}")
        ws = self.client.post("/api/auth/workspace/", {"workspace_slug": "acme"}, format="json").data
        self.client.credentials()
        verify = self.client.post("/api/auth/verify-user-token/", {"token": ws["access_token"]}, format="json")
        self.assertEqual(verify.status_code, 200, verify.data)
        gen = verify.data["generation_config"]
        self.assertEqual(gen["provider"], "deepseek")
        self.assertEqual(gen["api_key"], "sk-deep")

    def test_savings_dashboard_returns_aggregates(self):
        from .models import RAGTrace
        RAGTrace.objects.create(tenant=self.tenant, query="q1", citation_count=2, latency_ms=300, cost_units=1)
        RAGTrace.objects.create(tenant=self.tenant, query="q2", citation_count=0, insufficient_evidence=True, latency_ms=100)
        c = self._ws_client()
        resp = c.get("/api/usage/savings/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["queries"], 2)
        self.assertEqual(resp.data["grounded_rate"], 0.5)
        self.assertIn("estimated_savings_usd", resp.data["cost"])
        self.assertIn("estimated_energy_wh", resp.data)
