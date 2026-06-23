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
