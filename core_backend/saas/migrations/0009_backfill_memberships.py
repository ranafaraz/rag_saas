# Backfill Membership rows from the legacy User.tenant FK so existing users keep
# access under the new membership-based tenancy model.
from django.db import migrations


def create_memberships(apps, schema_editor):
    User = apps.get_model('saas', 'User')
    Membership = apps.get_model('saas', 'Membership')

    for user in User.objects.filter(tenant__isnull=False).iterator():
        membership, created = Membership.objects.get_or_create(
            user=user,
            tenant_id=user.tenant_id,
            defaults={
                'role': 'owner' if user.is_tenant_admin else 'member',
                'status': 'active',
            },
        )
        if created:
            # Carry over the user's existing fine-grained roles into the membership.
            role_ids = list(user.roles.values_list('id', flat=True))
            if role_ids:
                membership.roles.add(*role_ids)
        # Existing seeded users are considered verified so they aren't locked out.
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])


def drop_memberships(apps, schema_editor):
    Membership = apps.get_model('saas', 'Membership')
    Membership.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('saas', '0008_aimodelconfig_api_key_ciphertext_and_more'),
    ]

    operations = [
        migrations.RunPython(create_memberships, drop_memberships),
    ]
