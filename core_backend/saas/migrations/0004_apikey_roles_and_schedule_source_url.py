from django.db import migrations, models
import django.db.models.deletion


def copy_apikey_role_to_roles(apps, schema_editor):
    ApiKey = apps.get_model('saas', 'ApiKey')
    for key in ApiKey.objects.all().iterator():
        role_id = getattr(key, 'role_id', None)
        if role_id:
            key.roles.add(role_id)


class Migration(migrations.Migration):

    dependencies = [
        ('saas', '0003_ingestion_scheduler_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='apikey',
            name='roles',
            field=models.ManyToManyField(blank=True, related_name='api_keys', to='saas.role'),
        ),
        migrations.RunPython(copy_apikey_role_to_roles, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='apikey',
            name='role',
        ),
        migrations.AddField(
            model_name='ingestionschedule',
            name='source_url',
            field=models.TextField(blank=True, default=''),
        ),
    ]
