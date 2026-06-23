import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('saas', '0004_apikey_roles_and_schedule_source_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='is_demo',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='tenant',
            name='slug',
            field=models.SlugField(blank=True, max_length=120, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='tenant',
            name='stripe_customer_id',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
        migrations.AddField(
            model_name='tenant',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tenant',
            name='website_url',
            field=models.URLField(blank=True, default=''),
        ),
        migrations.CreateModel(
            name='Plan',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('code', models.SlugField(max_length=64, unique=True)),
                ('name', models.CharField(max_length=120)),
                ('description', models.TextField(blank=True, default='')),
                ('monthly_price_cents', models.PositiveIntegerField(default=0)),
                ('stripe_price_id', models.CharField(blank=True, default='', max_length=120)),
                ('seat_limit', models.PositiveIntegerField(default=5)),
                ('document_quota', models.PositiveIntegerField(default=250)),
                ('source_quota', models.PositiveIntegerField(default=25)),
                ('ingestion_runs_per_month', models.PositiveIntegerField(default=100)),
                ('chat_messages_per_month', models.PositiveIntegerField(default=2000)),
                ('features', models.JSONField(blank=True, default=dict)),
                ('is_public', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['monthly_price_cents', 'name'],
            },
        ),
        migrations.CreateModel(
            name='AIModelConfig',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('purpose', models.CharField(choices=[('generation', 'Generation'), ('embedding', 'Embedding'), ('reranking', 'Reranking')], max_length=40)),
                ('provider', models.CharField(choices=[('vllm', 'vLLM OpenAI-Compatible'), ('ollama', 'Ollama Development'), ('custom', 'Custom OpenAI-Compatible')], max_length=40)),
                ('model_name', models.CharField(max_length=160)),
                ('endpoint_url', models.URLField(blank=True, default='')),
                ('is_default', models.BooleanField(default=False)),
                ('config', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ai_model_configs', to='saas.tenant')),
            ],
            options={
                'ordering': ['purpose', '-is_default', 'model_name'],
                'indexes': [models.Index(fields=['tenant', 'purpose', 'is_default'], name='saas_aimode_tenant__10febf_idx')],
            },
        ),
        migrations.CreateModel(
            name='Entitlement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('feature', models.CharField(choices=[('seats', 'Seats'), ('documents', 'Documents'), ('sources', 'Sources'), ('ingestion_runs', 'Ingestion Runs'), ('chat_messages', 'Chat Messages'), ('sso', 'SSO'), ('audit_retention_days', 'Audit Retention Days')], max_length=64)),
                ('limit', models.PositiveIntegerField(default=0)),
                ('used', models.PositiveIntegerField(default=0)),
                ('resets_monthly', models.BooleanField(default=True)),
                ('source', models.CharField(default='plan', max_length=40)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='entitlements', to='saas.tenant')),
            ],
            options={
                'ordering': ['feature'],
                'unique_together': {('tenant', 'feature')},
            },
        ),
        migrations.CreateModel(
            name='EvaluationRun',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=160)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('passed', 'Passed'), ('failed', 'Failed')], default='queued', max_length=24)),
                ('dataset_ref', models.CharField(blank=True, default='', max_length=255)),
                ('metrics', models.JSONField(blank=True, default=dict)),
                ('failure_summary', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='evaluation_runs', to='saas.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='InvoiceMirror',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('stripe_invoice_id', models.CharField(max_length=120, unique=True)),
                ('stripe_customer_id', models.CharField(blank=True, default='', max_length=120)),
                ('status', models.CharField(blank=True, default='', max_length=40)),
                ('currency', models.CharField(default='usd', max_length=12)),
                ('amount_due_cents', models.PositiveIntegerField(default=0)),
                ('amount_paid_cents', models.PositiveIntegerField(default=0)),
                ('hosted_invoice_url', models.URLField(blank=True, default='')),
                ('invoice_pdf', models.URLField(blank=True, default='')),
                ('issued_at', models.DateTimeField(blank=True, null=True)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoices', to='saas.tenant')),
            ],
            options={
                'ordering': ['-issued_at', '-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('trialing', 'Trialing'), ('active', 'Active'), ('past_due', 'Past Due'), ('paused', 'Paused'), ('canceled', 'Canceled'), ('incomplete', 'Incomplete')], default='trialing', max_length=24)),
                ('stripe_customer_id', models.CharField(blank=True, default='', max_length=120)),
                ('stripe_subscription_id', models.CharField(blank=True, default='', max_length=120)),
                ('seats', models.PositiveIntegerField(default=1)),
                ('seat_limit', models.PositiveIntegerField(default=5)),
                ('document_quota', models.PositiveIntegerField(default=250)),
                ('source_quota', models.PositiveIntegerField(default=25)),
                ('ingestion_runs_per_month', models.PositiveIntegerField(default=100)),
                ('chat_messages_per_month', models.PositiveIntegerField(default=2000)),
                ('current_period_start', models.DateTimeField(default=django.utils.timezone.now)),
                ('current_period_end', models.DateTimeField(blank=True, null=True)),
                ('cancel_at_period_end', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='subscriptions', to='saas.plan')),
                ('tenant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subscription', to='saas.tenant')),
            ],
            options={
                'indexes': [models.Index(fields=['status'], name='saas_subscr_status_725815_idx'), models.Index(fields=['stripe_subscription_id'], name='saas_subscr_stripe__5cdb3f_idx')],
            },
        ),
        migrations.CreateModel(
            name='TenantInvitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('email', models.EmailField(max_length=254)),
                ('token_hash', models.CharField(max_length=128, unique=True)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('revoked', 'Revoked'), ('expired', 'Expired')], default='pending', max_length=24)),
                ('expires_at', models.DateTimeField()),
                ('accepted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('invited_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_invitations', to=settings.AUTH_USER_MODEL)),
                ('roles', models.ManyToManyField(blank=True, related_name='invitations', to='saas.role')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='saas.tenant')),
            ],
            options={
                'indexes': [models.Index(fields=['tenant', 'email', 'status'], name='saas_tenant_tenant__13f990_idx')],
            },
        ),
        migrations.CreateModel(
            name='UsageEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_type', models.CharField(choices=[('chat_message', 'Chat Message'), ('ingestion_run', 'Ingestion Run'), ('document_ingested', 'Document Ingested'), ('source_created', 'Source Created'), ('api_call', 'API Call')], max_length=40)),
                ('quantity', models.PositiveIntegerField(default=1)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('period_start', models.DateField(default=django.utils.timezone.localdate)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='usage_events', to='saas.tenant')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='usage_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['tenant', 'event_type', 'period_start'], name='saas_usagee_tenant__5af94e_idx'), models.Index(fields=['created_at'], name='saas_usagee_created_37cae0_idx')],
            },
        ),
        migrations.CreateModel(
            name='PromptVersion',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('prompt', models.TextField()),
                ('change_note', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('base_prompt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='versions', to='saas.baseprompt')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prompt_versions', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prompt_versions', to='saas.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('base_prompt', 'version')},
            },
        ),
    ]
