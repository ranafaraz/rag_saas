from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('saas', '0002_baseprompt'),
    ]

    operations = [
        migrations.CreateModel(
            name='IngestionSource',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=255)),
                ('source_type', models.CharField(choices=[('url', 'URL'), ('api', 'API'), ('db', 'Database')], default='url', max_length=20)),
                ('config', models.JSONField(blank=True, default=dict)),
                ('last_fingerprint', models.CharField(default='', max_length=64)),
                ('last_fetched_at', models.DateTimeField(blank=True, null=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingestion_sources', to='saas.tenant')),
            ],
            options={
                'ordering': ['-updated_at'],
                'unique_together': {('tenant', 'name')},
            },
        ),
        migrations.CreateModel(
            name='IngestionSchedule',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=255)),
                ('frequency', models.CharField(choices=[('hourly', 'Hourly'), ('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ('cron', 'Custom Cron')], default='daily', max_length=20)),
                ('cron_expression', models.CharField(blank=True, default='', max_length=100)),
                ('next_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('last_status', models.CharField(blank=True, default='', max_length=20)),
                ('last_error', models.TextField(blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('api_key', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingestion_schedules', to='saas.apikey')),
                ('source', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='schedules', to='saas.ingestionsource')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingestion_schedules', to='saas.tenant')),
                ('roles', models.ManyToManyField(blank=True, related_name='ingestion_schedules', to='saas.role')),
            ],
            options={
                'ordering': ['next_run_at', '-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='IngestionRunLog',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('success', 'Success'), ('skipped', 'Skipped'), ('failed', 'Failed')], max_length=20)),
                ('details', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('schedule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='run_logs', to='saas.ingestionschedule')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='ingestion_run_logs', to='saas.tenant')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
