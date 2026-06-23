from rest_framework import serializers
from .models import (
    Tenant,
    Plan,
    Subscription,
    Entitlement,
    UsageEvent,
    InvoiceMirror,
    TenantInvitation,
    Role,
    User,
    ApiKey,
    Document,
    BasePrompt,
    PromptVersion,
    AIModelConfig,
    EvaluationRun,
    IngestionSource,
    IngestionSchedule,
    IngestionRunLog,
)

class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = '__all__'


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    plan_code = serializers.CharField(source='plan.code', read_only=True)
    plan_name = serializers.CharField(source='plan.name', read_only=True)

    class Meta:
        model = Subscription
        fields = '__all__'
        read_only_fields = [
            'stripe_customer_id',
            'stripe_subscription_id',
            'created_at',
            'updated_at',
        ]


class EntitlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entitlement
        fields = '__all__'


class UsageEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = UsageEvent
        fields = '__all__'
        read_only_fields = ['created_at']


class InvoiceMirrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceMirror
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']


class TenantInvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantInvitation
        fields = '__all__'
        read_only_fields = ['token_hash', 'accepted_at', 'created_at', 'updated_at']


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = '__all__'

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'tenant', 'roles', 'is_tenant_admin']

class ApiKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = ApiKey
        fields = ['id', 'tenant', 'roles', 'name', 'key_prefix', 'created_at', 'is_active']
        read_only_fields = ['key_prefix']

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = '__all__'


class BasePromptSerializer(serializers.ModelSerializer):
    class Meta:
        model = BasePrompt
        fields = '__all__'


class PromptVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromptVersion
        fields = '__all__'


class AIModelConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIModelConfig
        fields = '__all__'


class EvaluationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvaluationRun
        fields = '__all__'


class IngestionSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionSource
        fields = '__all__'

    def validate_config(self, value):
        config = value or {}
        source_type = self.initial_data.get('source_type') or getattr(self.instance, 'source_type', 'url')
        if source_type != 'url':
            return config

        url = (config.get('url') or '').strip()
        urls = config.get('urls') or []
        if isinstance(urls, str):
            urls = [urls]
        if not isinstance(urls, list):
            raise serializers.ValidationError('config.urls must be a list of URLs.')

        normalized_urls = [u.strip() for u in urls if str(u).strip()]
        if url:
            normalized_urls.append(url)
        if not normalized_urls:
            raise serializers.ValidationError('config.url or config.urls is required for URL sources.')

        crawl_mode = (config.get('crawl_mode') or 'single_page').strip()
        if crawl_mode not in {'single_page', 'section_recursive', 'full_site'}:
            raise serializers.ValidationError('config.crawl_mode must be single_page, section_recursive, or full_site.')

        def _as_int(name, default):
            raw = config.get(name, default)
            try:
                value = int(raw)
            except (TypeError, ValueError):
                raise serializers.ValidationError(f'config.{name} must be an integer.')
            if value < 0:
                raise serializers.ValidationError(f'config.{name} must be >= 0.')
            return value

        validated = {
            **config,
            'urls': sorted(set(normalized_urls)),
            'crawl_mode': crawl_mode,
            'include_pdfs': bool(config.get('include_pdfs', True)),
            'obey_robots_txt': bool(config.get('obey_robots_txt', True)),
            'max_depth': _as_int('max_depth', 2),
            'max_pages': _as_int('max_pages', 200),
            'max_pdfs': _as_int('max_pdfs', 100),
            'max_pdf_size_mb': _as_int('max_pdf_size_mb', 20),
            'requests_per_second': _as_int('requests_per_second', 2),
        }
        validated.pop('url', None)
        return validated


class IngestionScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionSchedule
        fields = '__all__'

    def validate(self, attrs):
        tenant = attrs.get('tenant')
        source = attrs.get('source') or getattr(self.instance, 'source', None)
        api_key = attrs.get('api_key')
        roles = attrs.get('roles')

        if source and tenant and source.tenant_id != tenant.id:
            raise serializers.ValidationError('Source must belong to the same tenant.')
        if api_key and tenant and api_key.tenant_id != tenant.id:
            raise serializers.ValidationError('API key must belong to the same tenant.')
        if source and attrs.get('source_url'):
            source_urls = ((source.config or {}).get('urls') or [])
            if attrs['source_url'] not in source_urls:
                raise serializers.ValidationError('source_url must be one of source.config.urls.')
        if roles and tenant:
            wrong_tenant_roles = [r for r in roles if r.tenant_id != tenant.id]
            if wrong_tenant_roles:
                raise serializers.ValidationError('All roles must belong to the same tenant.')
        return attrs


class IngestionBulkSourceSerializer(serializers.Serializer):
    tenant = serializers.PrimaryKeyRelatedField(queryset=Tenant.objects.all())
    source_type = serializers.ChoiceField(choices=IngestionSource.SOURCE_TYPE_CHOICES, default='url')
    urls = serializers.ListField(
        child=serializers.URLField(),
        allow_empty=False,
    )
    name_prefix = serializers.CharField(max_length=255, required=False, allow_blank=True)
    config = serializers.DictField(required=False)

    def validate(self, attrs):
        if attrs['source_type'] != 'url':
            raise serializers.ValidationError('Bulk source creation currently supports URL source_type only.')
        return attrs


class IngestionRunLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionRunLog
        fields = '__all__'
