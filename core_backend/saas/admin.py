from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
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

admin.site.register(Tenant)
admin.site.register(Plan)
admin.site.register(Subscription)
admin.site.register(Entitlement)
admin.site.register(UsageEvent)
admin.site.register(InvoiceMirror)
admin.site.register(TenantInvitation)
admin.site.register(Role)
admin.site.register(User, UserAdmin)
admin.site.register(ApiKey)
admin.site.register(Document)
admin.site.register(BasePrompt)
admin.site.register(PromptVersion)
admin.site.register(AIModelConfig)
admin.site.register(EvaluationRun)
admin.site.register(IngestionSource)
admin.site.register(IngestionSchedule)
admin.site.register(IngestionRunLog)
