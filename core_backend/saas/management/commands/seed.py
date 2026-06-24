from django.core.management.base import BaseCommand
from saas.models import (
    Tenant,
    Plan,
    Subscription,
    Entitlement,
    UsageEvent,
    Role,
    User,
    Membership,
    ApiKey,
    Document,
    BasePrompt,
    PromptVersion,
    AIModelConfig,
    IngestionSource,
    IngestionSchedule,
    IngestionRunLog,
)
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
import requests
import os

class Command(BaseCommand):
    help = 'Seeds the database with a Stanford University demo tenant and triggers ingestion.'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting database seed...")

        # 1. Tenancy
        tenant_uuid = "00000000-0000-0000-0000-000000000001"
        tenant, _ = Tenant.objects.update_or_create(
            id=tenant_uuid,
            defaults={
                'name': 'Stanford University Demo',
                'slug': 'stanford-demo',
                'website_url': 'https://www.stanford.edu/',
                'is_demo': True,
            },
        )

        starter_plan, _ = Plan.objects.update_or_create(
            code='education-starter',
            defaults={
                'name': 'Education Starter',
                'description': 'Starter subscription for pilots and department-level education knowledge assistants.',
                'monthly_price_cents': 4900,
                'seat_limit': 25,
                'document_quota': 500,
                'source_quota': 40,
                'ingestion_runs_per_month': 250,
                'chat_messages_per_month': 10000,
                'features': {'sso': False, 'audit_retention_days': 30},
                'is_public': True,
            },
        )

        # Remove records from prior demo seed runs before recreating clean data.
        IngestionRunLog.objects.filter(tenant=tenant).delete()
        IngestionSchedule.objects.filter(tenant=tenant).delete()
        IngestionSource.objects.filter(tenant=tenant).delete()
        Document.objects.filter(tenant=tenant).delete()
        PromptVersion.objects.filter(tenant=tenant).delete()
        BasePrompt.objects.filter(tenant=tenant).delete()
        ApiKey.objects.filter(tenant=tenant).delete()
        User.objects.filter(tenant=tenant).delete()
        UsageEvent.objects.filter(tenant=tenant).delete()
        Entitlement.objects.filter(tenant=tenant).delete()

        subscription, _ = Subscription.objects.update_or_create(
            tenant=tenant,
            defaults={
                'plan': starter_plan,
                'status': 'active',
                'seats': 3,
                'current_period_start': timezone.now(),
                'current_period_end': timezone.now() + timedelta(days=30),
            },
        )
        subscription.apply_plan_defaults()
        subscription.save()
        for feature, limit in {
            'seats': subscription.seat_limit,
            'documents': subscription.document_quota,
            'sources': subscription.source_quota,
            'ingestion_runs': subscription.ingestion_runs_per_month,
            'chat_messages': subscription.chat_messages_per_month,
            'audit_retention_days': 30,
        }.items():
            Entitlement.objects.update_or_create(
                tenant=tenant,
                feature=feature,
                defaults={
                    'limit': limit,
                    'used': 0,
                    'source': 'seed',
                    'resets_monthly': feature != 'audit_retention_days',
                },
            )

        # Default free tier: Groq hosted (powerful, no local GPU). Falls back to
        # Ollama automatically when no GROQ_API_KEY is configured.
        AIModelConfig.objects.update_or_create(
            tenant=None,
            purpose='generation',
            provider='groq',
            model_name=os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'),
            defaults={
                'endpoint_url': os.getenv('GROQ_BASE_URL', 'https://api.groq.com/openai/v1'),
                'is_default': True,
                'config': {'temperature': 0.0, 'max_tokens': 768},
            },
        )
        AIModelConfig.objects.update_or_create(
            tenant=None,
            purpose='generation',
            provider='vllm',
            model_name='Qwen/Qwen3-8B',
            defaults={
                'endpoint_url': os.getenv('VLLM_BASE_URL', 'http://vllm:8000/v1'),
                'is_default': False,
                'config': {'temperature': 0.0, 'max_tokens': 768},
            },
        )
        AIModelConfig.objects.update_or_create(
            tenant=None,
            purpose='embedding',
            provider='custom',
            model_name='BAAI/bge-m3',
            defaults={
                'endpoint_url': '',
                'is_default': True,
                'config': {'dimension': 1024},
            },
        )

        # 2. Roles
        student_role, _ = Role.objects.get_or_create(tenant=tenant, name='Student')
        faculty_role, _ = Role.objects.get_or_create(tenant=tenant, name='Faculty')
        admin_role, _ = Role.objects.get_or_create(tenant=tenant, name='Admin')
        all_roles = [student_role, faculty_role, admin_role]

        # 3. Users
        demo_users = [
            ('stanford_student', 'student@example.edu', student_role, False),
            ('stanford_faculty', 'faculty@example.edu', faculty_role, False),
            ('stanford_admin', 'admin@example.edu', admin_role, True),
        ]
        for username, email, role, is_admin in demo_users:
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    'email': email,
                    'tenant': tenant,
                    'is_tenant_admin': is_admin,
                    'is_active': True,
                    'is_email_verified': True,
                },
            )
            user.roles.set([role])
            user.set_password('password123')
            user.save()
            # Membership is the source of truth for workspace access.
            membership, _ = Membership.objects.update_or_create(
                user=user,
                tenant=tenant,
                defaults={'role': 'owner' if is_admin else 'member', 'status': 'active'},
            )
            membership.roles.set([role])

        # 4. API Keys
        # For demo purposes, enforce exact tokens documented in README.
        def create_mock_key(role, raw_key):
            ApiKey.objects.filter(key_prefix=raw_key[:10]).delete()
            api_key = ApiKey.objects.create(
                tenant=tenant,
                name=f"Stanford {role.name} Key",
                key_prefix=raw_key[:10],
                hashed_key=make_password(raw_key),
                is_active=True
            )
            api_key.roles.set([role])
        create_mock_key(student_role, "sk_su_stu_demo")
        create_mock_key(faculty_role, "sk_su_fac_demo")
        create_mock_key(admin_role, "sk_su_adm_demo")

        default_prompt, _ = BasePrompt.objects.update_or_create(
            tenant=tenant,
            role=None,
            name="Default Assistant Prompt",
            defaults={
                "prompt": (
                    "You are the Stanford University demo knowledge assistant for this SaaS product. "
                    "Answer only from tenant knowledge base context, be concise, cite sources, "
                    "and refuse unsupported claims. Do not imply official affiliation."
                ),
                "is_active": True,
            },
        )
        student_prompt, _ = BasePrompt.objects.update_or_create(
            tenant=tenant,
            role=student_role,
            name="Student Helper Prompt",
            defaults={
                "prompt": "Prioritize admissions, financial aid, academic calendar, and student policy answers.",
                "is_active": True,
            },
        )
        faculty_prompt, _ = BasePrompt.objects.update_or_create(
            tenant=tenant,
            role=faculty_role,
            name="Faculty Operations Prompt",
            defaults={
                "prompt": "Prioritize teaching policy, advising, course administration, and faculty-facing operational answers.",
                "is_active": True,
            },
        )
        admin_prompt, _ = BasePrompt.objects.update_or_create(
            tenant=tenant,
            role=admin_role,
            name="Admin Operations Prompt",
            defaults={
                "prompt": "Prioritize source operations, governance, auditability, and administrative process answers.",
                "is_active": True,
            },
        )
        for prompt in [default_prompt, student_prompt, faculty_prompt, admin_prompt]:
            PromptVersion.objects.update_or_create(
                tenant=tenant,
                base_prompt=prompt,
                version=1,
                defaults={
                    'prompt': prompt.prompt,
                    'change_note': 'Seeded market-ready demo prompt.',
                },
            )

        demo_documents = [
            ("Admissions Overview", "url", "https://admission.stanford.edu/", "completed", [student_role, faculty_role, admin_role]),
            ("Undergraduate Financial Aid", "url", "https://financialaid.stanford.edu/undergrad/", "completed", [student_role, admin_role]),
            ("Student Policy Reference", "url", "https://studentservices.stanford.edu/more-resources/student-policies/admissions/admission-financial-aid", "completed", [student_role, faculty_role, admin_role]),
            ("Faculty Advising Notes", "text", "seed://faculty-advising-notes", "completed", [faculty_role, admin_role]),
            ("Admin Source Governance Checklist", "text", "seed://admin-source-governance", "completed", [admin_role]),
            ("Pending Registrar Calendar Import", "url", "https://registrar.stanford.edu/academic-calendar", "pending", [student_role, faculty_role, admin_role]),
        ]
        for title, source_type, source_uri, doc_status, doc_roles in demo_documents:
            doc = Document.objects.create(
                tenant=tenant,
                title=title,
                source_type=source_type,
                source_uri=source_uri,
                status=doc_status,
            )
            doc.roles.set(doc_roles)

        self.stdout.write(self.style.SUCCESS("Database records seeded successfully!"))

        # 5. Clear old vectors for this fixed demo tenant and queue official Stanford web ingestion.
        qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
        qdrant_port = os.getenv("QDRANT_PORT", "6333")
        qdrant_url = f"http://{qdrant_host}:{qdrant_port}/collections/rag_chunks/points/delete"
        try:
            res = requests.post(
                qdrant_url,
                json={
                    "filter": {
                        "must": [
                            {
                                "key": "metadata.tenant_id",
                                "match": {"value": str(tenant.id)},
                            }
                        ]
                    }
                },
                timeout=15,
            )
            if res.status_code in {200, 202}:
                self.stdout.write(self.style.SUCCESS("Cleared existing demo tenant vectors from Qdrant."))
            elif res.status_code == 404:
                self.stdout.write("Qdrant collection does not exist yet; skipping vector cleanup.")
            else:
                self.stdout.write(self.style.WARNING(f"Qdrant cleanup returned {res.status_code}: {res.text[:200]}"))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not clear Qdrant vectors: {exc}"))

        source_urls = [
            "https://www.stanford.edu/admission/",
            "https://admission.stanford.edu/",
            "https://financialaid.stanford.edu/undergrad/",
            "https://studentservices.stanford.edu/more-resources/student-policies/admissions/admission-financial-aid",
            "https://facts.stanford.edu/",
        ]

        public_source = IngestionSource.objects.create(
            tenant=tenant,
            name="Stanford Public Website",
            source_type="url",
            config={
                "urls": source_urls,
                "crawl_mode": "section_recursive",
                "include_pdfs": True,
                "obey_robots_txt": True,
                "max_depth": 1,
                "max_pages": 40,
                "max_pdfs": 10,
                "max_pdf_size_mb": 20,
                "requests_per_second": 1,
            },
            is_active=True,
        )
        aid_source = IngestionSource.objects.create(
            tenant=tenant,
            name="Financial Aid Section",
            source_type="url",
            config={
                "urls": ["https://financialaid.stanford.edu/undergrad/"],
                "crawl_mode": "section_recursive",
                "include_pdfs": True,
                "obey_robots_txt": True,
                "max_depth": 1,
                "max_pages": 25,
                "max_pdfs": 6,
                "max_pdf_size_mb": 20,
                "requests_per_second": 1,
            },
            is_active=True,
        )
        policy_source = IngestionSource.objects.create(
            tenant=tenant,
            name="Student Policy Reference",
            source_type="url",
            config={
                "urls": ["https://studentservices.stanford.edu/more-resources/student-policies/admissions/admission-financial-aid"],
                "crawl_mode": "single_page",
                "include_pdfs": False,
                "obey_robots_txt": True,
                "max_depth": 0,
                "max_pages": 1,
                "max_pdfs": 0,
                "max_pdf_size_mb": 20,
                "requests_per_second": 1,
            },
            is_active=True,
        )
        admin_key = ApiKey.objects.filter(tenant=tenant, roles=admin_role).first()
        student_key = ApiKey.objects.filter(tenant=tenant, roles=student_role).first()
        schedule_specs = [
            (public_source, admin_key, "Daily Stanford public website refresh", "", [student_role, faculty_role, admin_role], "daily", True, "success", "Seeded baseline public-site schedule."),
            (aid_source, student_key or admin_key, "Weekly financial aid refresh", "https://financialaid.stanford.edu/undergrad/", [student_role, admin_role], "weekly", True, "success", "Seeded financial aid refresh schedule."),
            (policy_source, admin_key, "Monthly policy page refresh", "https://studentservices.stanford.edu/more-resources/student-policies/admissions/admission-financial-aid", [student_role, faculty_role, admin_role], "monthly", False, "skipped", "Seeded inactive policy schedule for admin management demo."),
        ]
        for source, api_key, title, source_url, schedule_roles, frequency, active, log_status, details in schedule_specs:
            if not api_key:
                continue
            schedule = IngestionSchedule.objects.create(
                tenant=tenant,
                source=source,
                api_key=api_key,
                title=title,
                source_url=source_url,
                frequency=frequency,
                next_run_at=timezone.now(),
                last_run_at=timezone.now(),
                last_status=log_status,
                is_active=active,
            )
            schedule.roles.set(schedule_roles)
            IngestionRunLog.objects.create(
                tenant=tenant,
                schedule=schedule,
                status=log_status,
                details=details,
            )

        rag_api_url = os.getenv("RAG_API_URL", "http://rag_api:8001")
        internal_token = os.getenv("RAG_INTERNAL_INGEST_TOKEN", "")
        if not internal_token:
            self.stdout.write(self.style.WARNING("RAG_INTERNAL_INGEST_TOKEN is not configured; skipping web ingestion."))
            return

        try:
            res = requests.post(
                f"{rag_api_url}/internal/ingest/urls",
                json={
                    "tenant_id": str(tenant.id),
                    "title": "Stanford Public Website",
                    "source_uris": source_urls,
                    "roles": [role.name for role in all_roles],
                    "crawl_options": {
                        "crawl_mode": "section_recursive",
                        "include_pdfs": True,
                        "obey_robots_txt": True,
                        "max_depth": 1,
                        "max_pages": 40,
                        "max_pdfs": 10,
                        "max_pdf_size_mb": 20,
                        "requests_per_second": 1,
                    },
                },
                headers={"X-Ingestion-Token": internal_token},
                timeout=30,
            )
            if res.status_code == 200:
                self.stdout.write(self.style.SUCCESS("Queued Stanford website ingestion."))
            else:
                self.stdout.write(self.style.ERROR(f"Failed to queue Stanford website ingestion ({res.status_code}): {res.text[:300]}"))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Could not reach FastAPI to queue Stanford website ingestion: {exc}"))
