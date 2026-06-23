from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
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
from django.db.models import F, Q, Sum
from django.utils.text import slugify

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
    try:
        return list(user.roles.values_list('name', flat=True))
    except Exception:
        return []


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

        event = UsageEvent.objects.create(
            tenant=tenant,
            event_type=event_type,
            quantity=max(quantity, 1),
            metadata=request.data.get('metadata') or {},
            period_start=timezone.localdate().replace(day=1),
        )
        entitlement_feature = {
            'chat_message': 'chat_messages',
            'ingestion_run': 'ingestion_runs',
            'document_ingested': 'documents',
            'source_created': 'sources',
        }.get(event_type)
        if entitlement_feature:
            Entitlement.objects.filter(tenant=tenant, feature=entitlement_feature).update(
                used=F('used') + event.quantity
            )
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

class DocumentViewSet(TenantScopedModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    filterset_fields = ['tenant', 'status']
    allow_content_manager_writes = True


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

        UsageEvent.objects.create(
            tenant=tenant,
            user=request.user if request.user.is_authenticated else None,
            event_type='source_created',
            quantity=len(created),
            metadata={'source': 'bulk_create'},
            period_start=timezone.localdate().replace(day=1),
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


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'id': str(user.id),
            'username': user.username,
            'email': user.email,
            'tenant_id': str(user.tenant_id) if user.tenant_id else None,
            'tenant_name': user.tenant.name if user.tenant_id else '',
            'roles': _tenant_roles(user),
            'is_tenant_admin': bool(user.is_tenant_admin),
            'subscription': _subscription_payload(user.tenant) if user.tenant_id else None,
            'usage': _usage_summary(user.tenant) if user.tenant_id else None,
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
        keys = ApiKey.objects.filter(key_prefix=prefix, is_active=True)
        
        for key in keys:
            if check_password(token, key.hashed_key):
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
                # Alternatively add user rules
                return Response({
                    "tenant_id": str(key.tenant.id),
                    "roles": roles,
                    "base_prompt": base_prompt,
                    "subscription": subscription,
                    "usage": _usage_summary(key.tenant),
                }, status=200)

        return Response({"error": "Unauthorized"}, status=401)


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


class UserLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        username = (request.data.get('username') or '').strip()
        password = request.data.get('password') or ''
        tenant_id = (request.data.get('tenant_id') or '').strip()

        if not username or not password:
            return Response({'error': 'username and password are required'}, status=400)

        user = authenticate(request=request, username=username, password=password)
        if not user or not user.is_active:
            return Response({'error': 'Invalid credentials'}, status=401)

        if not user.tenant_id:
            return Response({'error': 'User is not assigned to any tenant'}, status=403)

        if tenant_id and str(user.tenant_id) != tenant_id:
            return Response({'error': 'User does not belong to the selected tenant'}, status=403)

        roles = list(user.roles.values_list('name', flat=True))
        base_prompt = _resolve_base_prompt_for_tenant_roles(user.tenant, roles)

        access = AccessToken.for_user(user)
        access['tenant_id'] = str(user.tenant_id)
        access['roles'] = roles
        access['username'] = user.username
        access['is_tenant_admin'] = bool(user.is_tenant_admin)
        access['base_prompt'] = base_prompt

        return Response(
            {
                'access_token': str(access),
                'token_type': 'Bearer',
                'expires_at': access['exp'],
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'tenant_id': str(user.tenant_id),
                    'roles': roles,
                    'is_tenant_admin': bool(user.is_tenant_admin),
                    'subscription': _subscription_payload(user.tenant),
                },
            },
            status=200,
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

        user = User.objects.filter(id=user_id, is_active=True).first()
        if not user or not user.tenant_id:
            return Response({'error': 'User not found or not assigned to tenant'}, status=401)

        roles = list(user.roles.values_list('name', flat=True))
        base_prompt = _resolve_base_prompt_for_tenant_roles(user.tenant, roles)

        return Response(
            {
                'tenant_id': str(user.tenant_id),
                'roles': roles,
                'username': user.username,
                'is_tenant_admin': bool(user.is_tenant_admin),
                'base_prompt': base_prompt,
                'user_id': str(user.id),
                'subscription': _subscription_payload(user.tenant),
                'usage': _usage_summary(user.tenant),
            },
            status=200,
        )
