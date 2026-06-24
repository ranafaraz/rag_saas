from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid

class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=120, unique=True, null=True, blank=True)
    website_url = models.URLField(blank=True, default='')
    stripe_customer_id = models.CharField(max_length=120, blank=True, default='')
    is_demo = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return self.name


class Plan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    monthly_price_cents = models.PositiveIntegerField(default=0)
    stripe_price_id = models.CharField(max_length=120, blank=True, default='')
    seat_limit = models.PositiveIntegerField(default=5)
    document_quota = models.PositiveIntegerField(default=250)
    source_quota = models.PositiveIntegerField(default=25)
    ingestion_runs_per_month = models.PositiveIntegerField(default=100)
    chat_messages_per_month = models.PositiveIntegerField(default=2000)
    features = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['monthly_price_cents', 'name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Subscription(models.Model):
    STATUS_CHOICES = (
        ('trialing', 'Trialing'),
        ('active', 'Active'),
        ('past_due', 'Past Due'),
        ('paused', 'Paused'),
        ('canceled', 'Canceled'),
        ('incomplete', 'Incomplete'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='subscription')
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name='subscriptions')
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='trialing')
    stripe_customer_id = models.CharField(max_length=120, blank=True, default='')
    stripe_subscription_id = models.CharField(max_length=120, blank=True, default='')
    seats = models.PositiveIntegerField(default=1)
    seat_limit = models.PositiveIntegerField(default=5)
    document_quota = models.PositiveIntegerField(default=250)
    source_quota = models.PositiveIntegerField(default=25)
    ingestion_runs_per_month = models.PositiveIntegerField(default=100)
    chat_messages_per_month = models.PositiveIntegerField(default=2000)
    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['stripe_subscription_id']),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.plan.code} - {self.status}"

    def apply_plan_defaults(self):
        self.seat_limit = self.plan.seat_limit
        self.document_quota = self.plan.document_quota
        self.source_quota = self.plan.source_quota
        self.ingestion_runs_per_month = self.plan.ingestion_runs_per_month
        self.chat_messages_per_month = self.plan.chat_messages_per_month


class Entitlement(models.Model):
    FEATURE_CHOICES = (
        ('seats', 'Seats'),
        ('documents', 'Documents'),
        ('sources', 'Sources'),
        ('ingestion_runs', 'Ingestion Runs'),
        ('chat_messages', 'Chat Messages'),
        ('sso', 'SSO'),
        ('audit_retention_days', 'Audit Retention Days'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='entitlements')
    feature = models.CharField(max_length=64, choices=FEATURE_CHOICES)
    limit = models.PositiveIntegerField(default=0)
    used = models.PositiveIntegerField(default=0)
    resets_monthly = models.BooleanField(default=True)
    source = models.CharField(max_length=40, default='plan')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'feature')
        ordering = ['feature']

    def __str__(self):
        return f"{self.tenant.name} - {self.feature}: {self.used}/{self.limit}"


class UsageEvent(models.Model):
    EVENT_CHOICES = (
        ('chat_message', 'Chat Message'),
        ('ingestion_run', 'Ingestion Run'),
        ('document_ingested', 'Document Ingested'),
        ('source_created', 'Source Created'),
        ('api_call', 'API Call'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='usage_events')
    user = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='usage_events')
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    quantity = models.PositiveIntegerField(default=1)
    metadata = models.JSONField(default=dict, blank=True)
    period_start = models.DateField(default=timezone.localdate)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'event_type', 'period_start']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.event_type} x{self.quantity}"


class InvoiceMirror(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invoices')
    stripe_invoice_id = models.CharField(max_length=120, unique=True)
    stripe_customer_id = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(max_length=40, blank=True, default='')
    currency = models.CharField(max_length=12, default='usd')
    amount_due_cents = models.PositiveIntegerField(default=0)
    amount_paid_cents = models.PositiveIntegerField(default=0)
    hosted_invoice_url = models.URLField(blank=True, default='')
    invoice_pdf = models.URLField(blank=True, default='')
    issued_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issued_at', '-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.stripe_invoice_id} - {self.status}"


class TenantInvitation(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('revoked', 'Revoked'),
        ('expired', 'Expired'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField()
    roles = models.ManyToManyField('Role', related_name='invitations', blank=True)
    invited_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_invitations')
    token_hash = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'email', 'status']),
        ]

    def __str__(self):
        return f"{self.email} invited to {self.tenant.name}"

class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='roles')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'name')

    def __str__(self):
        return f"{self.tenant.name} - {self.name}"

class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # tenant is retained only as a "last active workspace" pointer for convenience.
    # It is NEVER the source of truth for access control — Membership is. The active
    # tenant for a request is derived from the verified workspace JWT claim.
    tenant = models.ForeignKey(Tenant, on_delete=models.SET_NULL, related_name='users', null=True, blank=True)
    roles = models.ManyToManyField(Role, related_name='users', blank=True)
    branches = models.ManyToManyField('Branch', related_name='users', blank=True)
    is_tenant_admin = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    mfa_enabled = models.BooleanField(default=False)
    auth_provider = models.CharField(max_length=50, default='local')

    def __str__(self):
        return self.username


class Membership(models.Model):
    """
    Source of truth for which tenants (workspaces) a user may access, and the
    role they hold within each. Replaces the demo's client-supplied tenant_id:
    the active tenant on every request is verified against an active Membership.
    """
    ROLE_CHOICES = (
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    )
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('invited', 'Invited'),
        ('suspended', 'Suspended'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='memberships')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='memberships')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default='member')
    # Fine-grained RAG roles (Faculty/Student/Developer/...) scoped to THIS workspace.
    roles = models.ManyToManyField(Role, related_name='memberships', blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='active')
    invited_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_memberships'
    )
    # Per-workspace onboarding progress (tour seen, checklist steps done) — see Phase 4.
    onboarding_state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'tenant')
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['tenant', 'status']),
        ]

    def __str__(self):
        return f"{self.user.username} @ {self.tenant.name} ({self.role})"

    @property
    def is_admin(self) -> bool:
        return self.role in {'owner', 'admin'}

class ApiKey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='api_keys')
    roles = models.ManyToManyField(Role, related_name='api_keys', blank=True)
    name = models.CharField(max_length=255)
    key_prefix = models.CharField(max_length=10, unique=True)
    hashed_key = models.CharField(max_length=128)
    scopes = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    rate_limit_per_minute = models.PositiveIntegerField(default=60)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.key_prefix}...)"

    @property
    def is_usable(self):
        if not self.is_active or self.revoked_at:
            return False
        if self.expires_at and self.expires_at <= timezone.now():
            return False
        return True

class Document(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255)
    source_type = models.CharField(max_length=50, choices=(('file', 'File'), ('url', 'URL'), ('text', 'Text')))
    source_uri = models.TextField()
    roles = models.ManyToManyField(Role, related_name='documents', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class BasePrompt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='base_prompts')
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='base_prompts', null=True, blank=True)
    name = models.CharField(max_length=255)
    prompt = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        role_name = self.role.name if self.role else 'Default'
        return f"{self.tenant.name} - {role_name} - {self.name}"


class PromptVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='prompt_versions')
    base_prompt = models.ForeignKey(BasePrompt, on_delete=models.CASCADE, related_name='versions')
    version = models.PositiveIntegerField(default=1)
    prompt = models.TextField()
    change_note = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='prompt_versions')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('base_prompt', 'version')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.base_prompt.name} v{self.version}"


class AIModelConfig(models.Model):
    # Free, no-GPU hosted default is 'groq'. Tenants may bring their own key for
    # any of the hosted providers; 'ollama'/'vllm'/'custom' remain for self-host.
    PROVIDER_CHOICES = (
        ('groq', 'Groq (free hosted)'),
        ('openai', 'OpenAI'),
        ('anthropic', 'Anthropic Claude'),
        ('deepseek', 'DeepSeek'),
        ('vllm', 'vLLM OpenAI-Compatible'),
        ('ollama', 'Ollama (self-host)'),
        ('custom', 'Custom OpenAI-Compatible'),
    )
    PURPOSE_CHOICES = (
        ('generation', 'Generation'),
        ('embedding', 'Embedding'),
        ('reranking', 'Reranking'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ai_model_configs', null=True, blank=True)
    purpose = models.CharField(max_length=40, choices=PURPOSE_CHOICES)
    provider = models.CharField(max_length=40, choices=PROVIDER_CHOICES)
    model_name = models.CharField(max_length=160)
    endpoint_url = models.URLField(blank=True, default='')
    # BYOK: the provider API key, encrypted at rest (Fernet). Never serialized raw —
    # see api_key_hint for the masked display value.
    api_key_ciphertext = models.TextField(blank=True, default='')
    is_default = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['purpose', '-is_default', 'model_name']
        indexes = [
            models.Index(fields=['tenant', 'purpose', 'is_default']),
        ]

    def __str__(self):
        scope = self.tenant.name if self.tenant else 'Global'
        return f"{scope} - {self.purpose} - {self.model_name}"

    @property
    def api_key(self) -> str:
        from .encryption import decrypt_secret
        return decrypt_secret(self.api_key_ciphertext)

    def set_api_key(self, raw: str) -> None:
        from .encryption import encrypt_secret
        self.api_key_ciphertext = encrypt_secret(raw or '')

    @property
    def api_key_hint(self) -> str:
        raw = self.api_key
        if not raw:
            return ''
        return f"••••{raw[-4:]}" if len(raw) >= 4 else '••••'


class EvaluationRun(models.Model):
    STATUS_CHOICES = (
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('passed', 'Passed'),
        ('failed', 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='evaluation_runs')
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='queued')
    dataset_ref = models.CharField(max_length=255, blank=True, default='')
    metrics = models.JSONField(default=dict, blank=True)
    failure_summary = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.name} - {self.status}"


class IntegrationJob(models.Model):
    STATUS_CHOICES = (
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )
    JOB_TYPE_CHOICES = (
        ('ingest_url', 'Ingest URL'),
        ('ingest_document', 'Ingest Document'),
        ('eval_run', 'Evaluation Run'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='integration_jobs')
    api_key = models.ForeignKey(ApiKey, on_delete=models.SET_NULL, null=True, blank=True, related_name='integration_jobs')
    job_type = models.CharField(max_length=40, choices=JOB_TYPE_CHOICES)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='queued')
    external_task_id = models.CharField(max_length=120, blank=True, default='')
    request = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['external_task_id']),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.job_type} - {self.status}"


class RAGTrace(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='rag_traces')
    api_key = models.ForeignKey(ApiKey, on_delete=models.SET_NULL, null=True, blank=True, related_name='rag_traces')
    api_key_prefix = models.CharField(max_length=10, blank=True, default='')
    query = models.TextField()
    roles = models.JSONField(default=list, blank=True)
    top_chunks = models.JSONField(default=list, blank=True)
    citation_count = models.PositiveIntegerField(default=0)
    insufficient_evidence = models.BooleanField(default=False)
    refusal_reason = models.CharField(max_length=80, blank=True, default='')
    latency_ms = models.PositiveIntegerField(default=0)
    cost_units = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=24, default='success')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['api_key_prefix']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.tenant.name} - {self.status} - {self.created_at}"


class IngestionSource(models.Model):
    SOURCE_TYPE_CHOICES = (
        ('url', 'URL'),
        ('api', 'API'),
        ('db', 'Database'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_sources')
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES, default='url')
    config = models.JSONField(default=dict, blank=True)
    last_fingerprint = models.CharField(max_length=64, default='')
    last_fetched_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'name')
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.name}"


class IngestionSchedule(models.Model):
    FREQUENCY_CHOICES = (
        ('hourly', 'Hourly'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('cron', 'Custom Cron'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_schedules')
    source = models.ForeignKey(IngestionSource, on_delete=models.CASCADE, related_name='schedules')
    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name='ingestion_schedules')
    title = models.CharField(max_length=255)
    source_url = models.TextField(blank=True, default='')
    roles = models.ManyToManyField(Role, related_name='ingestion_schedules', blank=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily')
    cron_expression = models.CharField(max_length=100, blank=True, default='')
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=20, blank=True, default='')
    last_error = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_run_at', '-updated_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.title} ({self.frequency})"


class IngestionRunLog(models.Model):
    STATUS_CHOICES = (
        ('success', 'Success'),
        ('skipped', 'Skipped'),
        ('failed', 'Failed'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ingestion_run_logs')
    schedule = models.ForeignKey(IngestionSchedule, on_delete=models.CASCADE, related_name='run_logs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    details = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.schedule.title} - {self.status}"


class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('tenant', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.tenant.name} - {self.name}"


class AccessPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='access_policies')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default='')
    policy_document = models.JSONField(default=dict)
    roles = models.ManyToManyField(Role, related_name='access_policies', blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tenant.name} - {self.name}"


class IPWhitelist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='ip_whitelists')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='ip_whitelists', null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    description = models.CharField(max_length=255, blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'ip_address')

    def __str__(self):
        return f"{self.tenant.name} - {self.ip_address}"


class ComplianceLog(models.Model):
    LOG_TYPES = (
        ('gdpr_export', 'GDPR Data Export'),
        ('gdpr_delete', 'GDPR Data Deletion'),
        ('terms_accept', 'Terms of Service Accepted'),
        ('privacy_accept', 'Privacy Policy Accepted'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='compliance_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='compliance_logs')
    log_type = models.CharField(max_length=50, choices=LOG_TYPES)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.log_type} by {self.user.username if self.user else 'Unknown'} at {self.created_at}"


class AuditLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='audit_logs', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action = models.CharField(max_length=50) # CREATE, UPDATE, DELETE
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=255, null=True, blank=True)
    previous_state = models.JSONField(null=True, blank=True)
    new_state = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['tenant', 'model_name']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.action} on {self.model_name} by {self.user.username if self.user else 'System'}"
