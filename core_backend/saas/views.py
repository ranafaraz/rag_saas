from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db import transaction
from django.core.cache import cache
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
    Membership,
    ApiKey,
    Document,
    BasePrompt,
    PromptVersion,
    AIModelConfig,
    EvaluationRun,
    IntegrationJob,
    RAGTrace,
    IngestionSource,
    IngestionSchedule,
    IngestionRunLog,
)
from .serializers import (
    TenantSerializer,
    PlanSerializer,
    SubscriptionSerializer,
    EntitlementSerializer,
    UsageEventSerializer,
    InvoiceMirrorSerializer,
    TenantInvitationSerializer,
    RoleSerializer,
    UserSerializer,
    ApiKeySerializer,
    DocumentSerializer,
    BasePromptSerializer,
    PromptVersionSerializer,
    AIModelConfigSerializer,
    EvaluationRunSerializer,
    IntegrationJobSerializer,
    RAGTraceSerializer,
    SignupSerializer,
    IngestionSourceSerializer,
    IngestionBulkSourceSerializer,
    IngestionScheduleSerializer,
    IngestionRunLogSerializer,
)
from .permissions import TenantScopedPermission, can_manage_tenant
from django.contrib.auth.hashers import make_password
import secrets
import string
import os
import hashlib
from datetime import timedelta
from django.utils import timezone
import requests
from django.contrib.auth.hashers import check_password
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import F, Q, Sum, Count, Avg
from django.utils.text import slugify
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.core.mail import send_mail
from django.conf import settings

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:3000')
EMAIL_VERIFY_SALT = 'saas.email.verify'
EMAIL_VERIFY_MAX_AGE = 60 * 60 * 48  # 48h

RAG_API_URL = os.getenv('RAG_API_URL', 'http://rag_api:8001')
RAG_INTERNAL_INGEST_TOKEN = os.getenv('RAG_INTERNAL_INGEST_TOKEN', '')
SCHEDULER_TRIGGER_TOKEN = os.getenv('SCHEDULER_TRIGGER_TOKEN', '')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET', '')


def _compute_next_run(schedule: IngestionSchedule, current_time=None):
    now = current_time or timezone.now()
    if schedule.frequency == 'hourly':
        return now + timedelta(hours=1)
    if schedule.frequency == 'daily':
        return now + timedelta(days=1)
    if schedule.frequency == 'weekly':
        return now + timedelta(weeks=1)
    if schedule.frequency == 'monthly':
        return now + timedelta(days=30)
    if schedule.frequency == 'cron':
        expr = (schedule.cron_expression or '').strip()
        # Supported lightweight cron form: */N * * * *
        if expr.startswith('*/') and expr.endswith(' * * * *'):
            step = expr.split('*/', 1)[1].split(' ', 1)[0]
            if step.isdigit() and int(step) > 0:
                return now + timedelta(minutes=int(step))
        # Fallback for invalid custom expressions
        return now + timedelta(hours=1)
    return now + timedelta(days=1)


def _trigger_schedule_ingestion(schedule: IngestionSchedule) -> tuple[str, str]:
    source_config = schedule.source.config or {}
    source_urls = source_config.get('urls') or []
    if schedule.source.source_type != 'url' or not source_urls:
        return 'failed', 'Unsupported source type or missing URL config'

    if schedule.source_url:
        if schedule.source_url not in source_urls:
            return 'failed', 'Scheduled source_url is not in source config.urls'
        selected_urls = [schedule.source_url]
    else:
        selected_urls = source_urls

    tenant_id = str(schedule.tenant_id)
    role_names = list(schedule.roles.values_list('name', flat=True))
    if not role_names:
        role_names = list(schedule.api_key.roles.values_list('name', flat=True))
    payload = {
        'tenant_id': tenant_id,
        'title': schedule.title,
        'source_uris': selected_urls,
        'crawl_options': {
            'crawl_mode': source_config.get('crawl_mode', 'single_page'),
            'include_pdfs': bool(source_config.get('include_pdfs', True)),
            'obey_robots_txt': bool(source_config.get('obey_robots_txt', True)),
            'max_depth': int(source_config.get('max_depth', 2)),
            'max_pages': int(source_config.get('max_pages', 200)),
            'max_pdfs': int(source_config.get('max_pdfs', 100)),
            'max_pdf_size_mb': int(source_config.get('max_pdf_size_mb', 20)),
            'requests_per_second': int(source_config.get('requests_per_second', 2)),
        },
        'roles': role_names,
    }

    if not RAG_INTERNAL_INGEST_TOKEN:
        return 'failed', 'RAG_INTERNAL_INGEST_TOKEN is not configured'

    try:
        response = requests.post(
            f"{RAG_API_URL}/internal/ingest/urls",
            json=payload,
            headers={'X-Ingestion-Token': RAG_INTERNAL_INGEST_TOKEN},
            timeout=20,
        )
        if response.status_code == 200:
            data = response.json()
            return 'success', f"Queued {len(data.get('task_ids', []))} task(s)"
        return 'failed', f"RAG API error ({response.status_code}): {response.text[:200]}"
    except Exception as exc:
        return 'failed', f"RAG API unreachable: {exc}"


def _run_due_schedules(now=None) -> int:
    current = now or timezone.now()
    due_schedules = IngestionSchedule.objects.filter(
        is_active=True,
        next_run_at__isnull=False,
        next_run_at__lte=current,
    ).select_related('tenant', 'source', 'api_key').prefetch_related('roles')

    processed = 0
    for schedule in due_schedules:
        status_label, details = _trigger_schedule_ingestion(schedule)
        schedule.last_status = status_label
        schedule.last_error = '' if status_label == 'success' else details
        schedule.last_run_at = current
        schedule.next_run_at = _compute_next_run(schedule, current)
        schedule.save(update_fields=['last_status', 'last_error', 'last_run_at', 'next_run_at'])

        IngestionRunLog.objects.create(
            tenant=schedule.tenant,
            schedule=schedule,
            status='success' if status_label == 'success' else 'failed',
            details=details,
        )
        processed += 1

    return processed

def generate_api_key():
    alphabet = string.ascii_letters + string.digits
    raw_key = "sk_" + ''.join(secrets.choice(alphabet) for _ in range(32))
    return raw_key


def _tenant_roles(user) -> list[str]:
    # Prefer roles from the active workspace Membership (set during auth).
    active_roles = getattr(user, '_active_role_names', None)
    if active_roles is not None:
        return list(active_roles)
    try:
        return list(user.roles.values_list('name', flat=True))
    except Exception:
        return []


def _mint_workspace_token(user, membership):
    """Issue a workspace-scoped access token from a verified Membership."""
    role_names = list(membership.roles.values_list('name', flat=True))
    base_prompt = _resolve_base_prompt_for_tenant_roles(membership.tenant, role_names)
    access = AccessToken.for_user(user)
    access['tenant_id'] = str(membership.tenant_id)
    access['roles'] = role_names
    access['username'] = user.username
    access['is_tenant_admin'] = membership.is_admin
    access['base_prompt'] = base_prompt
    return access, role_names, base_prompt


def _send_email_verification(user) -> str:
    """Email a signed verification link. Uses Django's email backend (console in dev)."""
    token = TimestampSigner(salt=EMAIL_VERIFY_SALT).sign(str(user.id))
    link = f"{FRONTEND_URL}/verify?token={token}"
    try:
        send_mail(
            subject='Verify your email',
            message=f'Welcome! Confirm your email to finish setting up your account:\n\n{link}',
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@ragsaas.local'),
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception:
        pass
    return token


def _verify_email_token(token: str):
    try:
        user_id = TimestampSigner(salt=EMAIL_VERIFY_SALT).unsign(token, max_age=EMAIL_VERIFY_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return User.objects.filter(id=user_id).first()


def _membership_payload(membership) -> dict:
    return {
        'tenant_id': str(membership.tenant_id),
        'tenant_name': membership.tenant.name,
        'tenant_slug': membership.tenant.slug or '',
        'role': membership.role,
        'is_admin': membership.is_admin,
        'roles': list(membership.roles.values_list('name', flat=True)),
        'status': membership.status,
        'onboarding_state': membership.onboarding_state or {},
    }


def _ensure_entitlements(subscription: Subscription) -> None:
    limits = {
        'seats': subscription.seat_limit,
        'documents': subscription.document_quota,
        'sources': subscription.source_quota,
        'ingestion_runs': subscription.ingestion_runs_per_month,
        'chat_messages': subscription.chat_messages_per_month,
    }
    for feature, limit in limits.items():
        Entitlement.objects.update_or_create(
            tenant=subscription.tenant,
            feature=feature,
            defaults={'limit': limit, 'source': 'subscription'},
        )


def _default_scopes() -> list[str]:
    return ['query', 'stream', 'ingest', 'usage']


def _get_default_plan(plan_code: str = '') -> Plan:
    if plan_code:
        plan = Plan.objects.filter(code=plan_code, is_public=True).first()
        if plan:
            return plan
    plan = Plan.objects.filter(is_public=True).order_by('monthly_price_cents', 'name').first()
    if plan:
        return plan
    return Plan.objects.create(
        code='developer-starter',
        name='Developer Starter',
        description='Open-core starter plan for API integration pilots.',
        monthly_price_cents=0,
        seat_limit=5,
        document_quota=250,
        source_quota=25,
        ingestion_runs_per_month=100,
        chat_messages_per_month=2000,
        features={'self_serve_signup': True, 'api_access': True},
        is_public=True,
    )


def _consume_entitlement(tenant: Tenant, feature: str, quantity: int = 1) -> tuple[bool, str]:
    quantity = max(int(quantity or 1), 1)
    entitlement = Entitlement.objects.filter(tenant=tenant, feature=feature).first()
    if not entitlement:
        return True, ''
    if entitlement.limit and entitlement.used + quantity > entitlement.limit:
        return False, f'{feature} quota exceeded ({entitlement.used}/{entitlement.limit}).'
    Entitlement.objects.filter(id=entitlement.id).update(used=F('used') + quantity)
    return True, ''


def _record_usage_and_entitlement(tenant: Tenant, event_type: str, quantity: int = 1, metadata=None, user=None) -> UsageEvent:
    feature = {
        'chat_message': 'chat_messages',
        'ingestion_run': 'ingestion_runs',
        'document_ingested': 'documents',
        'source_created': 'sources',
    }.get(event_type)
    if feature:
        allowed, message = _consume_entitlement(tenant, feature, quantity)
        if not allowed:
            raise ValidationError(message)
    return UsageEvent.objects.create(
        tenant=tenant,
        user=user,
        event_type=event_type,
        quantity=max(int(quantity or 1), 1),
        metadata=metadata or {},
        period_start=timezone.localdate().replace(day=1),
    )


def _usage_summary(tenant: Tenant) -> dict:
    period_start = timezone.localdate().replace(day=1)
    usage = {
        row['event_type']: row['total'] or 0
        for row in UsageEvent.objects.filter(
            tenant=tenant,
            period_start=period_start,
        ).values('event_type').annotate(total=Sum('quantity'))
    }
    entitlements = {
        entitlement.feature: {
            'limit': entitlement.limit,
            'used': entitlement.used,
        }
        for entitlement in Entitlement.objects.filter(tenant=tenant)
    }
    return {
        'period_start': str(period_start),
        'usage': usage,
        'entitlements': entitlements,
    }


def _subscription_payload(tenant: Tenant) -> dict:
    subscription = getattr(tenant, 'subscription', None)
    if not subscription:
        return {'status': 'missing', 'active': False}
    return {
        'status': subscription.status,
        'active': subscription.status in {'trialing', 'active'},
        'plan': subscription.plan.code,
        'current_period_end': subscription.current_period_end,
        'cancel_at_period_end': subscription.cancel_at_period_end,
    }


class TenantScopedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [TenantScopedPermission]
    tenant_filter_field = 'tenant'
    allow_content_manager_writes = False

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_field = getattr(self, 'tenant_filter_field', 'tenant')
        if not tenant_field:
            return queryset

        user = self.request.user
        requested_tenant = self.request.query_params.get('tenant')
        if getattr(user, 'is_superuser', False):
            if requested_tenant:
                return queryset.filter(**{f'{tenant_field}_id': requested_tenant})
            return queryset

        tenant_id = getattr(user, 'tenant_id', None)
        if tenant_id:
            return queryset.filter(**{f'{tenant_field}_id': tenant_id})
        return queryset.none()

    def _request_tenant(self):
        user = self.request.user
        if not getattr(user, 'is_authenticated', False) or not getattr(user, 'tenant_id', None):
            raise PermissionDenied('User is not assigned to a tenant.')
        return user.tenant

    def _validate_tenant(self, serializer):
        if getattr(self.request.user, 'is_superuser', False):
            return {}

        tenant = serializer.validated_data.get('tenant')
        request_tenant = self._request_tenant()
        if tenant and tenant.id != request_tenant.id:
            raise PermissionDenied('Cross-tenant writes are not allowed.')
        if 'tenant' in serializer.fields and not tenant:
            return {'tenant': request_tenant}
        return {}

    def perform_create(self, serializer):
        serializer.save(**self._validate_tenant(serializer))

    def perform_update(self, serializer):
        self._validate_tenant(serializer)
        serializer.save()


class TenantViewSet(TenantScopedModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    tenant_filter_field = None

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            return queryset
        if getattr(user, 'tenant_id', None):
            return queryset.filter(id=user.tenant_id)
        return queryset.none()

    def perform_create(self, serializer):
        if not getattr(self.request.user, 'is_superuser', False):
            raise PermissionDenied('Only platform admins can create tenants through this endpoint.')
        if not serializer.validated_data.get('slug'):
            serializer.validated_data['slug'] = slugify(serializer.validated_data['name'])[:120]
        serializer.save()


class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        if getattr(self.request.user, 'is_superuser', False):
            return queryset
        return queryset.filter(is_public=True)

    def _require_platform_admin(self):
        if not getattr(self.request.user, 'is_superuser', False):
            raise PermissionDenied('Only platform admins can manage plans.')

    def perform_create(self, serializer):
        self._require_platform_admin()
        serializer.save()

    def perform_update(self, serializer):
        self._require_platform_admin()
        serializer.save()

    def perform_destroy(self, instance):
        self._require_platform_admin()
        instance.delete()


class SubscriptionViewSet(TenantScopedModelViewSet):
    queryset = Subscription.objects.select_related('tenant', 'plan').all()
    serializer_class = SubscriptionSerializer

    def perform_create(self, serializer):
        subscription = serializer.save(**self._validate_tenant(serializer))
        subscription.apply_plan_defaults()
        subscription.save(update_fields=[
            'seat_limit',
            'document_quota',
            'source_quota',
            'ingestion_runs_per_month',
            'chat_messages_per_month',
        ])
        _ensure_entitlements(subscription)

    def perform_update(self, serializer):
        self._validate_tenant(serializer)
        subscription = serializer.save()
        _ensure_entitlements(subscription)


class EntitlementViewSet(TenantScopedModelViewSet):
    queryset = Entitlement.objects.all()
    serializer_class = EntitlementSerializer


class UsageEventViewSet(TenantScopedModelViewSet):
    queryset = UsageEvent.objects.select_related('tenant', 'user').all()
    serializer_class = UsageEventSerializer

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def record(self, request):
        token = request.headers.get('X-Ingestion-Token', '')
        if not RAG_INTERNAL_INGEST_TOKEN or token != RAG_INTERNAL_INGEST_TOKEN:
            return Response({'error': 'Unauthorized usage recorder'}, status=status.HTTP_401_UNAUTHORIZED)

        tenant_id = request.data.get('tenant')
        event_type = request.data.get('event_type')
        try:
            quantity = int(request.data.get('quantity') or 1)
        except (TypeError, ValueError):
            return Response({'error': 'quantity must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        tenant = Tenant.objects.filter(id=tenant_id).first()
        if not tenant:
            return Response({'error': 'Unknown tenant'}, status=status.HTTP_404_NOT_FOUND)
        if event_type not in dict(UsageEvent.EVENT_CHOICES):
            return Response({'error': 'Invalid event_type'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            event = _record_usage_and_entitlement(
                tenant=tenant,
                event_type=event_type,
                quantity=quantity,
                metadata=request.data.get('metadata') or {},
            )
        except ValidationError as exc:
            return Response({'error': str(exc.detail[0] if isinstance(exc.detail, list) else exc.detail)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        return Response(UsageEventSerializer(event).data, status=status.HTTP_201_CREATED)


class InvoiceMirrorViewSet(TenantScopedModelViewSet):
    queryset = InvoiceMirror.objects.all()
    serializer_class = InvoiceMirrorSerializer


class TenantInvitationViewSet(TenantScopedModelViewSet):
    queryset = TenantInvitation.objects.prefetch_related('roles').all()
    serializer_class = TenantInvitationSerializer

    def perform_create(self, serializer):
        if not can_manage_tenant(self.request.user):
            raise PermissionDenied('Only tenant admins can invite users.')
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        invitation = serializer.save(
            **self._validate_tenant(serializer),
            invited_by=self.request.user,
            token_hash=token_hash,
        )
        invitation.raw_token = token


class RoleViewSet(TenantScopedModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    filterset_fields = ['tenant']

class UserViewSet(TenantScopedModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filterset_fields = ['tenant']

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get('tenant') or self._request_tenant()
        allowed, message = _consume_entitlement(tenant, 'seats', 1)
        if not allowed:
            raise ValidationError(message)
        serializer.save(**self._validate_tenant(serializer))

class ApiKeyViewSet(TenantScopedModelViewSet):
    queryset = ApiKey.objects.all()
    serializer_class = ApiKeySerializer
    filterset_fields = ['tenant', 'roles']

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        save_kwargs = self._validate_tenant(serializer)
        tenant = serializer.validated_data.get('tenant') or save_kwargs.get('tenant')
        if not tenant:
            raise ValidationError('tenant is required')
        raw_key = generate_api_key()
        
        # Save key_prefix and hashed_key
        api_key = ApiKey(
            tenant=tenant,
            name=serializer.validated_data['name'],
            key_prefix=raw_key[:10],
            hashed_key=make_password(raw_key),
            scopes=serializer.validated_data.get('scopes') or _default_scopes(),
            expires_at=serializer.validated_data.get('expires_at'),
            rate_limit_per_minute=serializer.validated_data.get('rate_limit_per_minute') or 60,
            is_active=True
        )
        api_key.save()
        roles = serializer.validated_data.get('roles') or []
        if roles:
            api_key.roles.set(roles)
        
        # We need to return the raw key only once
        data = ApiKeySerializer(api_key).data
        data['raw_key'] = raw_key
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def rotate(self, request, pk=None):
        api_key = self.get_object()
        raw_key = generate_api_key()
        api_key.key_prefix = raw_key[:10]
        api_key.hashed_key = make_password(raw_key)
        api_key.revoked_at = None
        api_key.last_used_at = None
        api_key.is_active = True
        api_key.save(update_fields=['key_prefix', 'hashed_key', 'revoked_at', 'last_used_at', 'is_active'])
        data = ApiKeySerializer(api_key).data
        data['raw_key'] = raw_key
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        api_key = self.get_object()
        api_key.is_active = False
        api_key.revoked_at = timezone.now()
        api_key.save(update_fields=['is_active', 'revoked_at'])
        return Response(ApiKeySerializer(api_key).data, status=status.HTTP_200_OK)

class DocumentViewSet(TenantScopedModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    filterset_fields = ['tenant', 'status']
    allow_content_manager_writes = True

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get('tenant') or self._request_tenant()
        allowed, message = _consume_entitlement(tenant, 'documents', 1)
        if not allowed:
            raise ValidationError(message)
        serializer.save(**self._validate_tenant(serializer))


class BasePromptViewSet(TenantScopedModelViewSet):
    queryset = BasePrompt.objects.all()
    serializer_class = BasePromptSerializer
    filterset_fields = ['tenant', 'role', 'is_active']
    allow_content_manager_writes = True


class PromptVersionViewSet(TenantScopedModelViewSet):
    queryset = PromptVersion.objects.select_related('tenant', 'base_prompt').all()
    serializer_class = PromptVersionSerializer
    filterset_fields = ['tenant', 'base_prompt']
    allow_content_manager_writes = True


class AIModelConfigViewSet(TenantScopedModelViewSet):
    queryset = AIModelConfig.objects.select_related('tenant').all()
    serializer_class = AIModelConfigSerializer
    filterset_fields = ['tenant', 'purpose', 'provider', 'is_default']

    def get_queryset(self):
        queryset = self.queryset.all()
        if getattr(self.request.user, 'is_superuser', False):
            return queryset
        tenant_id = getattr(self.request.user, 'tenant_id', None)
        return queryset.filter(Q(tenant_id=tenant_id) | Q(tenant__isnull=True))

    def perform_update(self, serializer):
        if serializer.instance and serializer.instance.tenant_id is None and not getattr(self.request.user, 'is_superuser', False):
            raise PermissionDenied('Only platform admins can update global model configs.')
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        if instance.tenant_id is None and not getattr(self.request.user, 'is_superuser', False):
            raise PermissionDenied('Only platform admins can delete global model configs.')
        instance.delete()


class EvaluationRunViewSet(TenantScopedModelViewSet):
    queryset = EvaluationRun.objects.select_related('tenant').all()
    serializer_class = EvaluationRunSerializer
    filterset_fields = ['tenant', 'status']

    @action(detail=True, methods=['post'])
    def run_smoke(self, request, pk=None):
        evaluation = self.get_object()
        dataset = request.data.get('questions') or []
        metrics = {
            'question_count': len(dataset) if isinstance(dataset, list) else 0,
            'status': 'queued_for_external_runner',
        }
        evaluation.status = 'passed' if metrics['question_count'] else 'failed'
        evaluation.metrics = metrics
        evaluation.failure_summary = '' if metrics['question_count'] else 'No questions supplied.'
        evaluation.save(update_fields=['status', 'metrics', 'failure_summary', 'updated_at'])
        return Response(EvaluationRunSerializer(evaluation).data)


class IntegrationJobViewSet(TenantScopedModelViewSet):
    queryset = IntegrationJob.objects.select_related('tenant', 'api_key').all()
    serializer_class = IntegrationJobSerializer
    filterset_fields = ['tenant', 'status', 'job_type', 'external_task_id']

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def record(self, request):
        token = request.headers.get('X-Ingestion-Token', '')
        if not RAG_INTERNAL_INGEST_TOKEN or token != RAG_INTERNAL_INGEST_TOKEN:
            return Response({'error': 'Unauthorized integration job recorder'}, status=status.HTTP_401_UNAUTHORIZED)
        tenant = Tenant.objects.filter(id=request.data.get('tenant')).first()
        if not tenant:
            return Response({'error': 'Unknown tenant'}, status=status.HTTP_404_NOT_FOUND)
        api_key = ApiKey.objects.filter(id=request.data.get('api_key'), tenant=tenant).first() if request.data.get('api_key') else None
        job, _ = IntegrationJob.objects.update_or_create(
            external_task_id=request.data.get('external_task_id') or '',
            tenant=tenant,
            defaults={
                'api_key': api_key,
                'job_type': request.data.get('job_type') or 'ingest_url',
                'status': request.data.get('status') or 'queued',
                'request': request.data.get('request') or {},
                'result': request.data.get('result') or {},
                'error': request.data.get('error') or '',
            },
        )
        return Response(IntegrationJobSerializer(job).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def lookup(self, request):
        token = request.headers.get('X-Ingestion-Token', '')
        if not RAG_INTERNAL_INGEST_TOKEN or token != RAG_INTERNAL_INGEST_TOKEN:
            return Response({'error': 'Unauthorized integration job lookup'}, status=status.HTTP_401_UNAUTHORIZED)
        tenant = Tenant.objects.filter(id=request.data.get('tenant')).first()
        if not tenant:
            return Response({'error': 'Unknown tenant'}, status=status.HTTP_404_NOT_FOUND)
        job = IntegrationJob.objects.filter(
            tenant=tenant,
            external_task_id=request.data.get('external_task_id') or '',
        ).first()
        if not job:
            return Response({'error': 'Unknown job'}, status=status.HTTP_404_NOT_FOUND)
        return Response(IntegrationJobSerializer(job).data)


class RAGTraceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RAGTrace.objects.select_related('tenant', 'api_key').all()
    serializer_class = RAGTraceSerializer
    permission_classes = [TenantScopedPermission]
    filterset_fields = ['tenant', 'api_key_prefix', 'status', 'insufficient_evidence']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            tenant_id = self.request.query_params.get('tenant')
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        if getattr(user, 'tenant_id', None):
            return queryset.filter(tenant_id=user.tenant_id)
        return queryset.none()

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def record(self, request):
        token = request.headers.get('X-Ingestion-Token', '')
        if not RAG_INTERNAL_INGEST_TOKEN or token != RAG_INTERNAL_INGEST_TOKEN:
            return Response({'error': 'Unauthorized trace recorder'}, status=status.HTTP_401_UNAUTHORIZED)
        tenant = Tenant.objects.filter(id=request.data.get('tenant')).first()
        if not tenant:
            return Response({'error': 'Unknown tenant'}, status=status.HTTP_404_NOT_FOUND)
        api_key = ApiKey.objects.filter(id=request.data.get('api_key'), tenant=tenant).first() if request.data.get('api_key') else None
        trace = RAGTrace.objects.create(
            tenant=tenant,
            api_key=api_key,
            api_key_prefix=request.data.get('api_key_prefix') or '',
            query=request.data.get('query') or '',
            roles=request.data.get('roles') or [],
            top_chunks=request.data.get('top_chunks') or [],
            citation_count=int(request.data.get('citation_count') or 0),
            insufficient_evidence=bool(request.data.get('insufficient_evidence', False)),
            refusal_reason=request.data.get('refusal_reason') or '',
            latency_ms=int(request.data.get('latency_ms') or 0),
            cost_units=int(request.data.get('cost_units') or 0),
            status=request.data.get('status') or 'success',
        )
        return Response(RAGTraceSerializer(trace).data, status=status.HTTP_201_CREATED)


class IngestionSourceViewSet(TenantScopedModelViewSet):
    queryset = IngestionSource.objects.all()
    serializer_class = IngestionSourceSerializer
    filterset_fields = ['tenant', 'source_type', 'is_active']
    allow_content_manager_writes = True

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant')
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        return queryset

    def perform_create(self, serializer):
        tenant = serializer.validated_data.get('tenant') or self._request_tenant()
        allowed, message = _consume_entitlement(tenant, 'sources', 1)
        if not allowed:
            raise ValidationError(message)
        serializer.save(**self._validate_tenant(serializer))

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        serializer = IngestionBulkSourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant = serializer.validated_data['tenant']
        if not getattr(request.user, 'is_superuser', False) and tenant.id != request.user.tenant_id:
            raise PermissionDenied('Cross-tenant source creation is not allowed.')
        urls = serializer.validated_data['urls']
        name_prefix = serializer.validated_data.get('name_prefix') or 'URL Source'
        base_config = serializer.validated_data.get('config') or {}

        created = []
        for idx, url in enumerate(urls, start=1):
            suffix = hashlib.sha1(url.encode('utf-8')).hexdigest()[:8]
            source, _ = IngestionSource.objects.get_or_create(
                tenant=tenant,
                name=f"{name_prefix} {idx} {suffix}",
                defaults={
                    'source_type': 'url',
                    'config': {**base_config, 'urls': [url]},
                },
            )
            created.append(IngestionSourceSerializer(source).data)

        _record_usage_and_entitlement(
            tenant=tenant,
            user=request.user if request.user.is_authenticated else None,
            event_type='source_created',
            quantity=len(created),
            metadata={'source': 'bulk_create'},
        )
        return Response({'count': len(created), 'sources': created}, status=status.HTTP_201_CREATED)


class IngestionScheduleViewSet(TenantScopedModelViewSet):
    queryset = IngestionSchedule.objects.all()
    serializer_class = IngestionScheduleSerializer
    filterset_fields = ['tenant', 'source', 'frequency', 'is_active']
    allow_content_manager_writes = True

    def get_permissions(self):
        if self.action == 'run_due':
            return [AllowAny()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        tenant_id = self.request.query_params.get('tenant')
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)
        return queryset

    def perform_create(self, serializer):
        schedule = serializer.save(**self._validate_tenant(serializer))
        if schedule.next_run_at is None:
            schedule.next_run_at = _compute_next_run(schedule)
            schedule.save(update_fields=['next_run_at'])

    @action(detail=True, methods=['post'])
    def run_now(self, request, pk=None):
        schedule = self.get_object()
        status_label, details = _trigger_schedule_ingestion(schedule)
        schedule.last_status = status_label
        schedule.last_error = '' if status_label == 'success' else details
        schedule.last_run_at = timezone.now()
        schedule.next_run_at = _compute_next_run(schedule, schedule.last_run_at)
        schedule.save(update_fields=['last_status', 'last_error', 'last_run_at', 'next_run_at'])

        IngestionRunLog.objects.create(
            tenant=schedule.tenant,
            schedule=schedule,
            status='success' if status_label == 'success' else 'failed',
            details=details,
        )
        code = status.HTTP_200_OK if status_label == 'success' else status.HTTP_400_BAD_REQUEST
        return Response({'status': status_label, 'details': details}, status=code)

    @action(detail=False, methods=['post'])
    def run_due(self, request):
        token = request.headers.get('X-Scheduler-Token', '')
        if not SCHEDULER_TRIGGER_TOKEN or token != SCHEDULER_TRIGGER_TOKEN:
            return Response({'error': 'Unauthorized scheduler trigger'}, status=status.HTTP_401_UNAUTHORIZED)

        processed = _run_due_schedules(timezone.now())
        return Response({'processed': processed}, status=status.HTTP_200_OK)


class IngestionRunLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = IngestionRunLog.objects.all()
    serializer_class = IngestionRunLogSerializer
    permission_classes = [TenantScopedPermission]
    filterset_fields = ['tenant', 'schedule', 'status']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if getattr(user, 'is_superuser', False):
            tenant_id = self.request.query_params.get('tenant')
            return queryset.filter(tenant_id=tenant_id) if tenant_id else queryset
        if getattr(user, 'tenant_id', None):
            return queryset.filter(tenant_id=user.tenant_id)
        return queryset.none()


# Transparent estimation constants for the savings/energy dashboard. These are
# deliberately conservative, documented assumptions — surfaced in the response so
# the numbers are honest rather than marketing fiction.
_EST_TOKENS_PER_QUERY = 600          # avg prompt + completion tokens for a grounded answer
_EST_GPT4_USD_PER_1K = 0.01          # blended $/1k tokens for a GPT-4-class hosted model
_EST_ENERGY_WH_PER_QUERY = 0.4       # rough Wh per hosted small-model query


class UsageSavingsView(APIView):
    """
    Per-workspace cost / energy / savings dashboard. Aggregates RAGTrace + UsageEvent
    to show what running on the free/efficient tier saves vs a GPT-4-class model.
    A competitive differentiator: most RAG SaaS hide cost; we make it transparent.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = getattr(request.user, 'tenant', None)
        if not getattr(request.user, 'tenant_id', None) or not tenant:
            raise PermissionDenied('User is not assigned to a workspace.')

        period_start = timezone.localdate().replace(day=1)
        traces = RAGTrace.objects.filter(tenant=tenant, created_at__date__gte=period_start)
        agg = traces.aggregate(
            total=Count('id'),
            grounded=Count('id', filter=Q(citation_count__gt=0)),
            refused=Count('id', filter=Q(insufficient_evidence=True)),
            avg_latency=Avg('latency_ms'),
            cost_units=Sum('cost_units'),
        )
        total = agg['total'] or 0
        tokens_estimate = total * _EST_TOKENS_PER_QUERY
        comparable_cost = round(tokens_estimate / 1000 * _EST_GPT4_USD_PER_1K, 2)
        generation = _resolve_generation_config(tenant)
        # Free tier (Groq/Ollama) and self-host carry no per-query API cost to the tenant.
        free_providers = {'groq', 'ollama', 'vllm', ''}
        on_free_tier = (generation.get('provider') or '') in free_providers
        free_tier_cost = 0.0 if on_free_tier else comparable_cost
        savings = round(max(comparable_cost - free_tier_cost, 0.0), 2)

        return Response({
            'period_start': str(period_start),
            'model': {
                'provider': generation.get('provider') or 'groq',
                'model': generation.get('model') or '',
                'on_free_tier': on_free_tier,
            },
            'queries': total,
            'grounded_rate': round((agg['grounded'] or 0) / total, 3) if total else None,
            'refusal_rate': round((agg['refused'] or 0) / total, 3) if total else None,
            'avg_latency_ms': int(agg['avg_latency'] or 0),
            'tokens_estimate': tokens_estimate,
            'cost': {
                'free_tier_usd': free_tier_cost,
                'comparable_gpt4_usd': comparable_cost,
                'estimated_savings_usd': savings,
                'currency': 'usd',
            },
            'estimated_energy_wh': round(total * _EST_ENERGY_WH_PER_QUERY, 1),
            'assumptions': {
                'tokens_per_query': _EST_TOKENS_PER_QUERY,
                'gpt4_usd_per_1k_tokens': _EST_GPT4_USD_PER_1K,
                'energy_wh_per_query': _EST_ENERGY_WH_PER_QUERY,
                'note': 'Conservative estimates for directional comparison, not billing.',
            },
        })


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        memberships = (
            Membership.objects.filter(user=user, status='active')
            .select_related('tenant')
            .prefetch_related('roles')
        )
        return Response({
            'id': str(user.id),
            'username': user.username,
            'email': user.email,
            'is_email_verified': bool(user.is_email_verified),
            'tenant_id': str(user.tenant_id) if user.tenant_id else None,
            'tenant_name': user.tenant.name if user.tenant_id else '',
            'roles': _tenant_roles(user),
            'is_tenant_admin': bool(user.is_tenant_admin),
            'subscription': _subscription_payload(user.tenant) if user.tenant_id else None,
            'usage': _usage_summary(user.tenant) if user.tenant_id else None,
            'workspaces': [_membership_payload(m) for m in memberships],
        })


class UsageSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.tenant_id:
            raise PermissionDenied('User is not assigned to a tenant.')
        return Response(_usage_summary(request.user.tenant))


class BillingSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.tenant_id:
            raise PermissionDenied('User is not assigned to a tenant.')
        tenant = request.user.tenant
        return Response({
            'tenant': TenantSerializer(tenant).data,
            'subscription': SubscriptionSerializer(getattr(tenant, 'subscription', None)).data if hasattr(tenant, 'subscription') else None,
            'entitlements': EntitlementSerializer(tenant.entitlements.all(), many=True).data,
            'invoices': InvoiceMirrorSerializer(tenant.invoices.all()[:12], many=True).data,
            'usage': _usage_summary(tenant),
        })


class BillingCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not request.user.tenant_id:
            raise PermissionDenied('User is not assigned to a tenant.')
        if not can_manage_tenant(request.user):
            raise PermissionDenied('Only tenant admins can manage billing.')

        plan_code = request.data.get('plan_code')
        success_url = request.data.get('success_url')
        cancel_url = request.data.get('cancel_url')
        plan = Plan.objects.filter(code=plan_code, is_public=True).first()
        if not plan or not plan.stripe_price_id:
            return Response({'error': 'Plan is not configured for Stripe checkout.'}, status=status.HTTP_400_BAD_REQUEST)
        if not success_url or not cancel_url:
            return Response({'error': 'success_url and cancel_url are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            import stripe
        except Exception:
            return Response({'error': 'stripe package is not installed.'}, status=status.HTTP_501_NOT_IMPLEMENTED)

        stripe.api_key = os.getenv('STRIPE_SECRET_KEY', '')
        if not stripe.api_key:
            return Response({'error': 'STRIPE_SECRET_KEY is not configured.'}, status=status.HTTP_501_NOT_IMPLEMENTED)

        tenant = request.user.tenant
        session = stripe.checkout.Session.create(
            mode='subscription',
            customer=tenant.stripe_customer_id or None,
            client_reference_id=str(tenant.id),
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[{'price': plan.stripe_price_id, 'quantity': 1}],
            metadata={'tenant_id': str(tenant.id), 'plan_code': plan.code},
            subscription_data={'metadata': {'tenant_id': str(tenant.id), 'plan_code': plan.code}},
        )
        return Response({'checkout_url': session.url, 'session_id': session.id})


class SignupView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        slug_base = data.get('workspace_slug') or slugify(data['organization_name'])[:100]
        slug = slug_base
        suffix = 1
        while Tenant.objects.filter(slug=slug).exists():
            suffix += 1
            slug = f"{slug_base[:110]}-{suffix}"

        tenant = Tenant.objects.create(
            name=data['organization_name'],
            slug=slug,
            website_url=data.get('website_url') or '',
        )
        role_names = ['Admin', 'Member', 'Developer']
        roles = {name: Role.objects.create(tenant=tenant, name=name) for name in role_names}
        admin = User.objects.create_user(
            username=data['admin_username'],
            email=data['admin_email'],
            password=data['admin_password'],
            tenant=tenant,
            is_tenant_admin=True,
        )
        admin.roles.add(roles['Admin'], roles['Developer'])

        # Membership is the source of truth for access. The signup creator is owner.
        membership = Membership.objects.create(
            user=admin, tenant=tenant, role='owner', status='active'
        )
        membership.roles.add(roles['Admin'], roles['Developer'])

        _send_email_verification(admin)

        plan = _get_default_plan(data.get('plan_code') or '')
        subscription = Subscription.objects.create(
            tenant=tenant,
            plan=plan,
            status='trialing',
            seats=1,
            current_period_end=timezone.now() + timedelta(days=14),
        )
        subscription.apply_plan_defaults()
        subscription.save(update_fields=[
            'seat_limit',
            'document_quota',
            'source_quota',
            'ingestion_runs_per_month',
            'chat_messages_per_month',
        ])
        _ensure_entitlements(subscription)
        Entitlement.objects.filter(tenant=tenant, feature='seats').update(used=1)

        raw_key = generate_api_key()
        api_key = ApiKey.objects.create(
            tenant=tenant,
            name='Default integration key',
            key_prefix=raw_key[:10],
            hashed_key=make_password(raw_key),
            scopes=_default_scopes(),
            rate_limit_per_minute=60,
        )
        api_key.roles.add(roles['Developer'])

        access = AccessToken.for_user(admin)
        access['tenant_id'] = str(tenant.id)
        access['roles'] = list(admin.roles.values_list('name', flat=True))
        access['username'] = admin.username
        access['is_tenant_admin'] = True

        return Response(
            {
                'tenant': TenantSerializer(tenant).data,
                'user': {
                    'id': str(admin.id),
                    'username': admin.username,
                    'email': admin.email,
                    'roles': list(admin.roles.values_list('name', flat=True)),
                    'is_tenant_admin': True,
                },
                'subscription': SubscriptionSerializer(subscription).data,
                'api_key': {
                    **ApiKeySerializer(api_key).data,
                    'raw_key': raw_key,
                },
                'access_token': str(access),
                'token_type': 'Bearer',
            },
            status=status.HTTP_201_CREATED,
        )


class IntegrationQuickstartView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.tenant_id:
            raise PermissionDenied('User is not assigned to a tenant.')
        return Response({
            'product': 'RAG SaaS API',
            'base_urls': {
                'core_api': request.build_absolute_uri('/api/'),
                'rag_api': os.getenv('PUBLIC_RAG_API_URL', 'http://localhost:8001'),
            },
            'authentication': {
                'type': 'Bearer API key',
                'header': 'Authorization: Bearer <sk_...>',
                'scopes': _default_scopes(),
            },
            'examples': {
                'query': {
                    'method': 'POST',
                    'url': '/v1/query',
                    'body': {'query': 'Summarize the latest account policy.'},
                },
                'stream': {
                    'method': 'POST',
                    'url': '/v1/query/stream',
                    'body': {'query': 'What should a customer do next?'},
                },
                'source': {
                    'method': 'POST',
                    'url': '/v1/sources',
                    'body': {'title': 'Help Center', 'url': 'https://example.com/help', 'roles': ['Developer']},
                },
            },
            'sdks': {
                'javascript_fetch': "await fetch(`${RAG_API}/v1/query`, {method:'POST', headers:{Authorization:`Bearer ${apiKey}`,'Content-Type':'application/json'}, body: JSON.stringify({query})})",
                'mobile': 'Use the same HTTPS JSON API from iOS, Android, React Native, or Flutter. Keep API keys on your backend for untrusted clients.',
                'crm': 'Call /v1/query from CRM server-side actions or middleware; do not expose full-scope API keys in browser extensions.',
            },
        })


def _stripe_dt(value):
    if not value:
        return None
    return timezone.datetime.fromtimestamp(value, tz=timezone.get_current_timezone())


def _handle_stripe_subscription(subscription_object: dict) -> None:
    tenant_id = (subscription_object.get('metadata') or {}).get('tenant_id')
    plan_code = (subscription_object.get('metadata') or {}).get('plan_code')
    customer_id = subscription_object.get('customer') or ''
    stripe_subscription_id = subscription_object.get('id') or ''
    tenant = Tenant.objects.filter(id=tenant_id).first() or Tenant.objects.filter(stripe_customer_id=customer_id).first()
    if not tenant:
        return
    if customer_id and tenant.stripe_customer_id != customer_id:
        tenant.stripe_customer_id = customer_id
        tenant.save(update_fields=['stripe_customer_id'])

    plan = Plan.objects.filter(code=plan_code).first() or Plan.objects.order_by('monthly_price_cents').first()
    if not plan:
        return

    sub, _ = Subscription.objects.update_or_create(
        tenant=tenant,
        defaults={
            'plan': plan,
            'status': subscription_object.get('status') or 'incomplete',
            'stripe_customer_id': customer_id,
            'stripe_subscription_id': stripe_subscription_id,
            'current_period_start': _stripe_dt(subscription_object.get('current_period_start')) or timezone.now(),
            'current_period_end': _stripe_dt(subscription_object.get('current_period_end')),
            'cancel_at_period_end': bool(subscription_object.get('cancel_at_period_end')),
        },
    )
    sub.apply_plan_defaults()
    sub.save()
    _ensure_entitlements(sub)


def _handle_stripe_invoice(invoice_object: dict) -> None:
    customer_id = invoice_object.get('customer') or ''
    tenant = Tenant.objects.filter(stripe_customer_id=customer_id).first()
    if not tenant:
        return
    InvoiceMirror.objects.update_or_create(
        stripe_invoice_id=invoice_object.get('id'),
        defaults={
            'tenant': tenant,
            'stripe_customer_id': customer_id,
            'status': invoice_object.get('status') or '',
            'currency': invoice_object.get('currency') or 'usd',
            'amount_due_cents': int(invoice_object.get('amount_due') or 0),
            'amount_paid_cents': int(invoice_object.get('amount_paid') or 0),
            'hosted_invoice_url': invoice_object.get('hosted_invoice_url') or '',
            'invoice_pdf': invoice_object.get('invoice_pdf') or '',
            'issued_at': _stripe_dt(invoice_object.get('created')),
            'paid_at': _stripe_dt(invoice_object.get('status_transitions', {}).get('paid_at')),
        },
    )


class StripeWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        event = request.data
        if STRIPE_WEBHOOK_SECRET:
            try:
                import stripe
                signature = request.headers.get('Stripe-Signature', '')
                event = stripe.Webhook.construct_event(request.body, signature, STRIPE_WEBHOOK_SECRET)
            except Exception as exc:
                return Response({'error': f'Invalid Stripe webhook: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        event_type = event.get('type')
        obj = (event.get('data') or {}).get('object') or {}
        if event_type in {'customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'}:
            _handle_stripe_subscription(obj)
        if event_type in {'invoice.created', 'invoice.finalized', 'invoice.payment_succeeded', 'invoice.payment_failed'}:
            _handle_stripe_invoice(obj)

        return Response({'received': True})

class VerifyAPIKeyView(APIView):
    permission_classes = [AllowAny]

    @staticmethod
    def _resolve_base_prompt(key: ApiKey) -> str:
        role_prompt = None
        key_roles = list(key.roles.all())
        if key_roles:
            role_prompt = BasePrompt.objects.filter(
                tenant=key.tenant,
                role__in=key_roles,
                is_active=True,
            ).order_by('-updated_at').first()
        if role_prompt:
            return role_prompt.prompt

        tenant_default = BasePrompt.objects.filter(
            tenant=key.tenant,
            role__isnull=True,
            is_active=True,
        ).order_by('-updated_at').first()
        return tenant_default.prompt if tenant_default else ""

    def post(self, request, *args, **kwargs):
        token = request.data.get('token', '')
        if not token or len(token) < 10:
            return Response({"error": "Invalid token format"}, status=401)
        
        prefix = token[:10]
        keys = ApiKey.objects.filter(key_prefix=prefix)
        
        for key in keys:
            if check_password(token, key.hashed_key):
                if not key.is_usable:
                    return Response({"error": "API key is inactive, expired, or revoked"}, status=401)
                scopes = key.scopes or _default_scopes()
                requested_scope = (request.data.get('scope') or '').strip()
                if requested_scope and requested_scope not in scopes and 'admin' not in scopes:
                    return Response({"error": f"API key is missing required scope: {requested_scope}"}, status=403)
                limit = int(key.rate_limit_per_minute or 0)
                if limit > 0:
                    cache_key = f"api-key-rate:{key.id}:{timezone.now().strftime('%Y%m%d%H%M')}"
                    count = cache.get(cache_key, 0)
                    if count >= limit:
                        return Response({"error": "API key rate limit exceeded"}, status=429)
                    cache.set(cache_key, count + 1, timeout=70)
                subscription = _subscription_payload(key.tenant)
                if not subscription.get('active'):
                    return Response(
                        {
                            "error": "Subscription is not active",
                            "subscription": subscription,
                        },
                        status=402,
                    )
                roles = list(key.roles.values_list('name', flat=True))
                base_prompt = self._resolve_base_prompt(key)
                key.last_used_at = timezone.now()
                key.save(update_fields=['last_used_at'])
                return Response({
                    "tenant_id": str(key.tenant.id),
                    "api_key_id": str(key.id),
                    "api_key_prefix": key.key_prefix,
                    "scopes": scopes,
                    "rate_limit_per_minute": limit,
                    "roles": roles,
                    "base_prompt": base_prompt,
                    "generation_config": _resolve_generation_config(key.tenant),
                    "subscription": subscription,
                    "usage": _usage_summary(key.tenant),
                }, status=200)

        return Response({"error": "Unauthorized"}, status=401)


def _resolve_generation_config(tenant: Tenant) -> dict:
    """
    Resolve the tenant's effective generation provider config for the RAG backend.
    Falls back to a global default, then to env defaults (empty dict). The api_key
    is decrypted here and sent only over the trusted internal verify channel.
    """
    cfg = (
        AIModelConfig.objects.filter(tenant=tenant, purpose='generation', is_default=True).first()
        or AIModelConfig.objects.filter(tenant=tenant, purpose='generation').order_by('-updated_at').first()
        or AIModelConfig.objects.filter(tenant__isnull=True, purpose='generation', is_default=True).first()
    )
    if not cfg:
        return {}
    return {
        'provider': cfg.provider,
        'model': cfg.model_name,
        'endpoint_url': cfg.endpoint_url,
        'api_key': cfg.api_key,
    }


def _resolve_base_prompt_for_tenant_roles(tenant: Tenant, role_names: list[str]) -> str:
    role_prompt = None
    if role_names:
        role_prompt = BasePrompt.objects.filter(
            tenant=tenant,
            role__name__in=role_names,
            is_active=True,
        ).order_by('-updated_at').first()
    if role_prompt:
        return role_prompt.prompt

    tenant_default = BasePrompt.objects.filter(
        tenant=tenant,
        role__isnull=True,
        is_active=True,
    ).order_by('-updated_at').first()
    return tenant_default.prompt if tenant_default else ""


def _scopes_for_user(user: User) -> list[str]:
    if can_manage_tenant(user):
        return ['query', 'stream', 'ingest', 'usage', 'admin']
    roles = {role.lower() for role in _tenant_roles(user)}
    if roles & {'faculty', 'staff', 'developer'}:
        return ['query', 'stream', 'ingest', 'usage']
    return ['query', 'stream']


def _scopes_for_membership(membership) -> list[str]:
    if membership.is_admin:
        return ['query', 'stream', 'ingest', 'usage', 'admin']
    roles = {r.lower() for r in membership.roles.values_list('name', flat=True)}
    if roles & {'faculty', 'staff', 'developer'}:
        return ['query', 'stream', 'ingest', 'usage']
    return ['query', 'stream']


class UserLoginView(APIView):
    """
    Step 1 of login: authenticate identity only. We NEVER accept a tenant_id from
    the client. Returns a short identity token plus the workspaces the user is a
    verified member of; the client then calls /auth/workspace/ to enter one.
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        identifier = (request.data.get('username') or request.data.get('email') or '').strip()
        password = request.data.get('password') or ''

        if not identifier or not password:
            return Response({'error': 'username/email and password are required'}, status=400)

        user = authenticate(request=request, username=identifier, password=password)
        if not user and '@' in identifier:
            # Allow login by email address.
            match = User.objects.filter(email__iexact=identifier).first()
            if match:
                user = authenticate(request=request, username=match.username, password=password)
        if not user or not user.is_active:
            return Response({'error': 'Invalid credentials'}, status=401)

        memberships = list(
            Membership.objects.filter(user=user, status='active')
            .select_related('tenant')
            .prefetch_related('roles')
        )

        # Identity token: no tenant_id claim -> cannot touch workspace-scoped data.
        identity = AccessToken.for_user(user)
        identity['username'] = user.username
        identity['token_scope'] = 'identity'

        return Response(
            {
                'identity_token': str(identity),
                'token_type': 'Bearer',
                'expires_at': identity['exp'],
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'is_email_verified': bool(user.is_email_verified),
                },
                'workspaces': [_membership_payload(m) for m in memberships],
            },
            status=200,
        )


class SelectWorkspaceView(APIView):
    """
    Step 2 of login: exchange the identity token for a workspace-scoped token.
    Membership is verified server-side; a tenant the user does not belong to is
    rejected regardless of what slug/id is sent.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        slug = (request.data.get('workspace_slug') or '').strip()
        tenant_id = (request.data.get('tenant_id') or '').strip()
        if not slug and not tenant_id:
            return Response({'error': 'workspace_slug or tenant_id is required'}, status=400)

        membership_qs = Membership.objects.filter(user=user, status='active').select_related('tenant')
        if slug:
            membership = membership_qs.filter(tenant__slug=slug).first()
        else:
            membership = membership_qs.filter(tenant_id=tenant_id).first()

        if not membership:
            return Response({'error': 'You are not a member of this workspace.'}, status=403)

        subscription = _subscription_payload(membership.tenant)
        access, roles, base_prompt = _mint_workspace_token(user, membership)
        return Response(
            {
                'access_token': str(access),
                'token_type': 'Bearer',
                'expires_at': access['exp'],
                'workspace': _membership_payload(membership),
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'tenant_id': str(membership.tenant_id),
                    'roles': roles,
                    'is_tenant_admin': membership.is_admin,
                    'subscription': subscription,
                    'scopes': _scopes_for_membership(membership),
                },
            },
            status=200,
        )


class MyWorkspacesView(APIView):
    """List the workspaces the authenticated identity may enter."""
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        memberships = (
            Membership.objects.filter(user=request.user, status='active')
            .select_related('tenant')
            .prefetch_related('roles')
        )
        return Response({'workspaces': [_membership_payload(m) for m in memberships]})


class AcceptInvitationView(APIView):
    """
    Accept a workspace invitation. The authenticated user's email must match the
    invite; on success a Membership is created with the invited roles.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        raw_token = (request.data.get('token') or '').strip()
        if not raw_token:
            return Response({'error': 'token is required'}, status=400)
        token_hash = hashlib.sha256(raw_token.encode('utf-8')).hexdigest()
        invitation = (
            TenantInvitation.objects.filter(token_hash=token_hash, status='pending')
            .select_related('tenant')
            .prefetch_related('roles')
            .first()
        )
        if not invitation:
            return Response({'error': 'Invalid or already-used invitation'}, status=400)
        if invitation.expires_at and invitation.expires_at <= timezone.now():
            invitation.status = 'expired'
            invitation.save(update_fields=['status'])
            return Response({'error': 'Invitation has expired'}, status=400)
        if invitation.email.lower() != (request.user.email or '').lower():
            return Response({'error': 'This invitation was sent to a different email address.'}, status=403)

        membership, _ = Membership.objects.get_or_create(
            user=request.user, tenant=invitation.tenant,
            defaults={'role': 'member', 'status': 'active', 'invited_by': invitation.invited_by},
        )
        membership.status = 'active'
        membership.save(update_fields=['status'])
        invite_roles = list(invitation.roles.all())
        if invite_roles:
            membership.roles.add(*invite_roles)
        invitation.status = 'accepted'
        invitation.accepted_at = timezone.now()
        invitation.save(update_fields=['status', 'accepted_at'])

        access, roles, _ = _mint_workspace_token(request.user, membership)
        return Response(
            {'workspace': _membership_payload(membership), 'access_token': str(access), 'token_type': 'Bearer'},
            status=200,
        )


class VerifyEmailView(APIView):
    """Confirm a user's email from the signed token in the verification link."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        token = (request.data.get('token') or '').strip()
        if not token:
            return Response({'error': 'token is required'}, status=400)
        user = _verify_email_token(token)
        if not user:
            return Response({'error': 'Invalid or expired verification link'}, status=400)
        if not user.is_email_verified:
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])
        return Response({'verified': True, 'email': user.email})


class CreateWorkspaceView(APIView):
    """
    Create a new workspace for the authenticated identity. The creator becomes
    the owner (Membership). Requires a verified email.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        user = request.user
        if not user.is_email_verified and not user.is_superuser:
            return Response({'error': 'Please verify your email before creating a workspace.'}, status=403)

        name = (request.data.get('name') or '').strip()
        if not name:
            return Response({'error': 'Workspace name is required'}, status=400)

        slug_base = (request.data.get('slug') or slugify(name))[:100] or 'workspace'
        slug = slug_base
        suffix = 1
        while Tenant.objects.filter(slug=slug).exists():
            suffix += 1
            slug = f"{slug_base[:110]}-{suffix}"

        tenant = Tenant.objects.create(name=name, slug=slug, website_url=request.data.get('website_url') or '')
        role_names = ['Admin', 'Member', 'Developer']
        roles = {n: Role.objects.create(tenant=tenant, name=n) for n in role_names}

        plan = _get_default_plan('')
        subscription = Subscription.objects.create(
            tenant=tenant, plan=plan, status='trialing', seats=1,
            current_period_end=timezone.now() + timedelta(days=14),
        )
        subscription.apply_plan_defaults()
        subscription.save()
        _ensure_entitlements(subscription)
        Entitlement.objects.filter(tenant=tenant, feature='seats').update(used=1)

        membership = Membership.objects.create(user=user, tenant=tenant, role='owner', status='active')
        membership.roles.add(roles['Admin'], roles['Developer'])

        access, role_list, base_prompt = _mint_workspace_token(user, membership)
        return Response(
            {
                'workspace': _membership_payload(membership),
                'access_token': str(access),
                'token_type': 'Bearer',
                'subscription': SubscriptionSerializer(subscription).data,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyUserTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        token = (request.data.get('token') or '').strip()
        if not token:
            return Response({'error': 'token is required'}, status=401)

        try:
            validated = JWTAuthentication().get_validated_token(token)
        except Exception:
            return Response({'error': 'Invalid or expired token'}, status=401)

        user_id = validated.get('user_id')
        if not user_id:
            return Response({'error': 'Invalid token payload'}, status=401)

        # The tenant is taken from the verified token claim, then re-checked
        # against an active Membership. Identity tokens (no claim) are rejected.
        tenant_id = validated.get('tenant_id')
        if not tenant_id:
            return Response({'error': 'Token is not scoped to a workspace'}, status=401)

        user = User.objects.filter(id=user_id, is_active=True).first()
        if not user:
            return Response({'error': 'User not found'}, status=401)

        membership = (
            Membership.objects.filter(user=user, tenant_id=tenant_id, status='active')
            .select_related('tenant')
            .prefetch_related('roles')
            .first()
        )
        if not membership and not user.is_superuser:
            return Response({'error': 'No active membership for this workspace'}, status=401)

        if membership:
            roles = list(membership.roles.values_list('name', flat=True))
            tenant = membership.tenant
            is_admin = membership.is_admin
            scopes = _scopes_for_membership(membership)
        else:  # superuser assuming a workspace
            tenant = Tenant.objects.filter(id=tenant_id).first()
            if not tenant:
                return Response({'error': 'Workspace not found'}, status=401)
            roles = list(user.roles.values_list('name', flat=True))
            is_admin = True
            scopes = ['query', 'stream', 'ingest', 'usage', 'admin']

        base_prompt = _resolve_base_prompt_for_tenant_roles(tenant, roles)

        return Response(
            {
                'tenant_id': str(tenant.id),
                'roles': roles,
                'username': user.username,
                'is_tenant_admin': is_admin,
                'base_prompt': base_prompt,
                'generation_config': _resolve_generation_config(tenant),
                'user_id': str(user.id),
                'scopes': scopes,
                'subscription': _subscription_payload(tenant),
                'usage': _usage_summary(tenant),
            },
            status=200,
        )
