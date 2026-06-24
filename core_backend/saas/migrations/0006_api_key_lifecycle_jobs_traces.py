from django.db import migrations, models
import django.db.models.deletion
import uuid
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('saas', '0005_market_ready_saas_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='auth_provider',
            field=models.CharField(default='local', max_length=50),
        ),
        migrations.AddField(
            model_name='user',
            name='mfa_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='apikey',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='last_used_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='rate_limit_per_minute',
            field=models.PositiveIntegerField(default=60),
        ),
        migrations.AddField(
            model_name='apikey',
            name='revoked_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='apikey',
            name='scopes',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('location', models.CharField(blank=True, default='', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='branches', to='saas.tenant')),
            ],
            options={
                'ordering': ['name'],
                'unique_together': {('tenant', 'name')},
            },
        ),
        migrations.AddField(
            model_name='user',
            name='branches',
            field=models.ManyToManyField(blank=True, related_name='users', to='saas.branch'),
        ),
        migrations.CreateModel(
            name='AccessPolicy',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, default='')),
                ('policy_document', models.JSONField(default=dict)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('roles', models.ManyToManyField(blank=True, related_name='access_policies', to='saas.role')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='access_policies', to='saas.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='IPWhitelist',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('ip_address', models.GenericIPAddressField()),
                ('description', models.CharField(blank=True, default='', max_length=255)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('branch', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='ip_whitelists', to='saas.branch')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ip_whitelists', to='saas.tenant')),
            ],
            options={
                'unique_together': {('tenant', 'ip_address')},
            },
        ),
        migrations.CreateModel(
            name='ComplianceLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('log_type', models.CharField(choices=[('gdpr_export', 'GDPR Data Export'), ('gdpr_delete', 'GDPR Data Deletion'), ('terms_accept', 'Terms of Service Accepted'), ('privacy_accept', 'Privacy Policy Accepted')], max_length=50)),
                ('details', models.JSONField(blank=True, default=dict)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='compliance_logs', to='saas.tenant')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='compliance_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('action', models.CharField(max_length=50)),
                ('model_name', models.CharField(max_length=100)),
                ('object_id', models.CharField(blank=True, max_length=255, null=True)),
                ('previous_state', models.JSONField(blank=True, null=True)),
                ('new_state', models.JSONField(blank=True, null=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='audit_logs', to='saas.tenant')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='audit_logs', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='IntegrationJob',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('job_type', models.CharField(choices=[('ingest_url', 'Ingest URL'), ('ingest_document', 'Ingest Document'), ('eval_run', 'Evaluation Run')], max_length=40)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')], default='queued', max_length=24)),
                ('external_task_id', models.CharField(blank=True, default='', max_length=120)),
                ('request', models.JSONField(blank=True, default=dict)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('error', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('api_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='integration_jobs', to='saas.apikey')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='integration_jobs', to='saas.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='RAGTrace',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('api_key_prefix', models.CharField(blank=True, default='', max_length=10)),
                ('query', models.TextField()),
                ('roles', models.JSONField(blank=True, default=list)),
                ('top_chunks', models.JSONField(blank=True, default=list)),
                ('citation_count', models.PositiveIntegerField(default=0)),
                ('insufficient_evidence', models.BooleanField(default=False)),
                ('refusal_reason', models.CharField(blank=True, default='', max_length=80)),
                ('latency_ms', models.PositiveIntegerField(default=0)),
                ('cost_units', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(default='success', max_length=24)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('api_key', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rag_traces', to='saas.apikey')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rag_traces', to='saas.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['tenant', 'model_name'], name='saas_auditl_tenant__4cc8d7_idx'),
        ),
        migrations.AddIndex(
            model_name='auditlog',
            index=models.Index(fields=['timestamp'], name='saas_auditl_timesta_a3f015_idx'),
        ),
        migrations.AddIndex(
            model_name='integrationjob',
            index=models.Index(fields=['tenant', 'status'], name='saas_integr_tenant__77f5e7_idx'),
        ),
        migrations.AddIndex(
            model_name='integrationjob',
            index=models.Index(fields=['external_task_id'], name='saas_integr_externa_492b05_idx'),
        ),
        migrations.AddIndex(
            model_name='ragtrace',
            index=models.Index(fields=['tenant', 'created_at'], name='saas_ragtra_tenant__d4cf1d_idx'),
        ),
        migrations.AddIndex(
            model_name='ragtrace',
            index=models.Index(fields=['api_key_prefix'], name='saas_ragtra_api_key_5e5ffd_idx'),
        ),
        migrations.AddIndex(
            model_name='ragtrace',
            index=models.Index(fields=['status'], name='saas_ragtra_status_fbe642_idx'),
        ),
    ]
