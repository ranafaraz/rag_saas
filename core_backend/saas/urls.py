from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TenantViewSet,
    PlanViewSet,
    SubscriptionViewSet,
    EntitlementViewSet,
    UsageEventViewSet,
    InvoiceMirrorViewSet,
    TenantInvitationViewSet,
    RoleViewSet,
    UserViewSet,
    ApiKeyViewSet,
    DocumentViewSet,
    BasePromptViewSet,
    PromptVersionViewSet,
    AIModelConfigViewSet,
    EvaluationRunViewSet,
    IngestionSourceViewSet,
    IngestionScheduleViewSet,
    IngestionRunLogViewSet,
    CurrentUserView,
    UsageSummaryView,
    BillingSummaryView,
    BillingCheckoutView,
    StripeWebhookView,
    VerifyAPIKeyView,
    UserLoginView,
    VerifyUserTokenView,
)

router = DefaultRouter()
router.register(r'tenants', TenantViewSet)
router.register(r'plans', PlanViewSet)
router.register(r'subscriptions', SubscriptionViewSet)
router.register(r'entitlements', EntitlementViewSet)
router.register(r'usage-events', UsageEventViewSet)
router.register(r'invoices', InvoiceMirrorViewSet)
router.register(r'invitations', TenantInvitationViewSet)
router.register(r'roles', RoleViewSet)
router.register(r'users', UserViewSet)
router.register(r'api-keys', ApiKeyViewSet)
router.register(r'documents', DocumentViewSet)
router.register(r'base-prompts', BasePromptViewSet)
router.register(r'prompt-versions', PromptVersionViewSet)
router.register(r'ai-model-configs', AIModelConfigViewSet)
router.register(r'evaluation-runs', EvaluationRunViewSet)
router.register(r'ingestion-sources', IngestionSourceViewSet)
router.register(r'ingestion-schedules', IngestionScheduleViewSet)
router.register(r'ingestion-run-logs', IngestionRunLogViewSet)

urlpatterns = [
    path('auth/me/', CurrentUserView.as_view(), name='current-user'),
    path('auth/verify/', VerifyAPIKeyView.as_view(), name='verify-api-key'),
    path('auth/login/', UserLoginView.as_view(), name='user-login'),
    path('auth/verify-user-token/', VerifyUserTokenView.as_view(), name='verify-user-token'),
    path('usage/summary/', UsageSummaryView.as_view(), name='usage-summary'),
    path('billing/summary/', BillingSummaryView.as_view(), name='billing-summary'),
    path('billing/checkout/', BillingCheckoutView.as_view(), name='billing-checkout'),
    path('billing/stripe/webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
    path('', include(router.urls)),
]
