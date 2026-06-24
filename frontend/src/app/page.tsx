import type { Metadata } from 'next';
import Link from 'next/link';
import { AuthRedirect } from '@/components/auth-redirect';

export const metadata: Metadata = {
  title: 'Lumora — Open-Source RAG SaaS Platform for Grounded AI Answers',
  description:
    'Lumora is a free, open-source, multi-tenant Retrieval-Augmented Generation (RAG) platform. Deploy AI knowledge assistants that answer from your documents with citations — no hallucinations. Supports Groq, OpenAI, Anthropic, and Ollama.',
  keywords: [
    'RAG platform',
    'retrieval augmented generation',
    'open source AI',
    'knowledge base chatbot',
    'document Q&A',
    'multi-tenant AI SaaS',
    'grounded AI answers',
    'chat with documents',
    'enterprise RAG',
    'local LLM',
    'BYOK AI',
    'document intelligence',
    'Ollama RAG',
    'Groq AI',
    'self-hosted AI',
    'open source knowledge base',
    'university AI assistant',
    'Lumora',
  ],
  openGraph: {
    title: 'Lumora — Open-Source RAG SaaS Platform',
    description:
      'Multi-tenant AI knowledge assistant platform — grounded answers, cited sources, zero hallucinations. Free tier with Groq. Self-hostable. MIT licensed.',
    type: 'website',
    siteName: 'Lumora',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Lumora — Open-Source RAG SaaS Platform',
    description:
      'Free, open-source multi-tenant RAG platform. Ground your AI in real documents. Cite every answer. Run locally or in the cloud.',
  },
  robots: { index: true, follow: true },
};

const GITHUB_URL = 'https://github.com/ranafaraz/rag_saas';
const GITHUB_ISSUES = `${GITHUB_URL}/issues`;
const GITHUB_DISCUSSIONS = `${GITHUB_URL}/discussions`;
const GITHUB_SPONSORS = `${GITHUB_URL}`;

const FEATURES = [
  {
    icon: '🏢',
    title: 'Multi-Tenant Workspaces',
    desc: 'Each organization gets its own isolated environment — separate knowledge bases, roles, API keys, and usage metrics. One deployment, unlimited tenants.',
  },
  {
    icon: '✅',
    title: 'Grounded Answers, Always',
    desc: 'Every response is anchored to retrieved documents with inline citations. If the answer is not in the knowledge base, Lumora says so — no hallucinations, ever.',
  },
  {
    icon: '🔑',
    title: 'Free Tier + Bring Your Own Key',
    desc: 'Start free with Groq\'s fast LLM API. Bring your own OpenAI, Anthropic, or DeepSeek key. Or run 100% locally with Ollama — no cloud required.',
  },
  {
    icon: '⚡',
    title: 'Automated Knowledge Ingestion',
    desc: 'Schedule URL crawlers and PDF parsers to keep your knowledge base fresh automatically. Section-recursive crawling, robots.txt compliance, configurable depth.',
  },
  {
    icon: '💰',
    title: 'Cost Savings Dashboard',
    desc: 'Track query volume, grounding rates, and estimated savings versus GPT-4-class APIs. Full transparency on your AI infrastructure spend — down to the watt-hour.',
  },
  {
    icon: '🛡️',
    title: 'Role-Based Access Control',
    desc: 'Owner, Admin, and Member roles per workspace. Fine-grained permissions backed by Membership-verified JWTs. Invite teammates via email with scoped roles.',
  },
];

const UNIQUE = [
  {
    title: 'Zero-Hallucination Design',
    desc: 'Answers come exclusively from retrieved context. Confident refusals when the evidence is absent — not fabricated confidence.',
  },
  {
    title: 'Truly Open Source',
    desc: 'MIT licensed, every line auditable on GitHub. No vendor lock-in, no telemetry, no surprise pricing tiers hidden behind "Enterprise."',
  },
  {
    title: 'Multi-Provider LLM Routing',
    desc: 'Switch between Groq, OpenAI, Anthropic, DeepSeek, Ollama, or vLLM at workspace granularity — without changing a single line of app code.',
  },
  {
    title: 'Privacy-First Architecture',
    desc: 'Run entirely on-prem with Ollama + Qdrant + Django + FastAPI. Your documents and queries never leave your own infrastructure.',
  },
  {
    title: 'Academic-Grade Multi-Tenancy',
    desc: 'Born from university research at IUB. Multi-role, multi-workspace, and battle-tested for real institutional deployments with diverse user populations.',
  },
  {
    title: 'LangChain-Free RAG Pipeline',
    desc: 'Custom, auditable retrieval pipeline — no framework magic, no hidden prompt leakage. You own the retrieval logic and can inspect every step.',
  },
];

const USE_CASES = [
  {
    icon: '🎓',
    title: 'Universities & Schools',
    desc: 'Give students and faculty an AI portal over institutional knowledge: admission policies, course catalogs, financial aid guides, and academic calendars.',
  },
  {
    icon: '🏭',
    title: 'Enterprise Teams',
    desc: 'Deploy internal knowledge bases for HR policies, engineering docs, compliance materials, and support runbooks — fully searchable with AI.',
  },
  {
    icon: '🔬',
    title: 'Research Institutions',
    desc: 'Build literature review assistants that retrieve from curated paper collections. Cited answers with source traceability and version control.',
  },
  {
    icon: '🏛️',
    title: 'Government & Public Sector',
    desc: 'Public-facing Q&A systems for policy documents, regulations, and citizen services — with full audit trails and on-prem deployment.',
  },
];

const TECH_STACK = [
  { category: 'Frontend', badges: ['Next.js 16', 'TypeScript', 'Tailwind CSS v4', 'App Router'] },
  { category: 'Core API', badges: ['Django 5', 'PostgreSQL', 'Celery', 'REST Framework', 'JWT'] },
  { category: 'RAG Engine', badges: ['FastAPI', 'Qdrant Vector DB', 'Custom Pipeline', 'BGE Embeddings'] },
  { category: 'LLM Providers', badges: ['Groq', 'OpenAI', 'Anthropic', 'DeepSeek', 'Ollama', 'vLLM'] },
  { category: 'Ingestion', badges: ['Celery + Redis', 'MongoDB', 'PDF Parser', 'Web Crawler'] },
  { category: 'Deployment', badges: ['Docker Compose', 'Self-Hostable', 'Production-Ready'] },
];

const ROADMAP_DONE = [
  'Multi-tenant workspaces with RBAC',
  'Grounded RAG with inline citations',
  'Free tier (Groq) + BYOK + Ollama fallback',
  'Automated URL and PDF ingestion scheduling',
  'Cost savings and usage analytics dashboard',
  'Guided onboarding tour and progress checklist',
];

const ROADMAP_UPCOMING = [
  'Vision RAG — answers from images and diagrams',
  'Agent Mode — multi-step reasoning with tool use',
  'Evaluation Framework — automated RAGAS-style scoring',
  'Fine-tuning Pipelines — adapt models to your domain',
  'Plugin Marketplace — Notion, Confluence, Slack connectors',
  'Native Mobile Apps — iOS and Android clients',
  'GraphRAG — knowledge graph enhanced retrieval',
  'SOC 2 / GDPR compliance tooling',
];

export default function LandingPage() {
  return (
    <div className="lp-page">
      <AuthRedirect />

      {/* ── Nav ─────────────────────────────────────────────────── */}
      <nav className="lp-nav" aria-label="Main navigation">
        <div className="lp-nav-inner">
          <a href="/" className="lp-logo" aria-label="Lumora home">
            <span className="lp-logo-mark" aria-hidden="true">L</span>
            <span className="lp-logo-name">Lumora</span>
          </a>

          <div className="lp-nav-links">
            <a href="#features">Features</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#roadmap">Roadmap</a>
            <a href="#open-source">Open Source</a>
            <a href="#funding">Funding</a>
          </div>

          <div className="lp-nav-ctas">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="lp-btn lp-btn-ghost"
              aria-label="Star Lumora on GitHub"
            >
              ⭐ GitHub
            </a>
            <Link href="/login" className="lp-btn lp-btn-primary">
              Try Demo →
            </Link>
          </div>
        </div>
      </nav>

      {/* ── Hero ─────────────────────────────────────────────────── */}
      <section className="lp-hero" aria-label="Hero">
        <div className="lp-hero-inner">
          <div className="lp-badge" role="status">
            <span className="lp-badge-dot" aria-hidden="true" />
            Open Source · Free Tier Available · MIT License
          </div>

          <h1 className="lp-hero-title">
            Where Documents<br />
            Become{' '}
            <span className="lp-gradient-text">Answers</span>
          </h1>

          <p className="lp-hero-sub">
            Lumora is an open-source, multi-tenant Retrieval-Augmented Generation (RAG) platform.
            Deploy your own AI knowledge assistant — grounded in your documents, every answer cited
            by evidence, privately hosted anywhere.
          </p>

          <div className="lp-hero-ctas">
            <Link href="/login" className="lp-btn lp-btn-primary lp-btn-lg">
              Try Live Demo →
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="lp-btn lp-btn-outline lp-btn-lg"
              style={{ color: '#94a3b8', borderColor: 'rgba(148,163,184,0.4)' }}
            >
              ⭐ View on GitHub
            </a>
          </div>

          <div className="lp-hero-stats" role="list" aria-label="Key metrics">
            {[
              { num: '10+', label: 'Microservices' },
              { num: '3', label: 'LLM Providers Free' },
              { num: '100%', label: 'Cited Answers' },
              { num: 'MIT', label: 'Open License' },
            ].map((s) => (
              <div key={s.label} className="lp-stat-item" role="listitem">
                <div className="lp-stat-num">{s.num}</div>
                <div className="lp-stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ─────────────────────────────────────────────── */}
      <section className="lp-section" id="features" aria-labelledby="features-title">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-eyebrow">Features</span>
            <h2 className="lp-section-title" id="features-title">
              Enterprise-grade RAG,<br />open and accessible
            </h2>
            <p className="lp-section-sub">
              Everything your team needs to build a knowledge-powered AI assistant — without paying
              for a proprietary platform or giving up data control.
            </p>
          </div>

          <div className="lp-features-grid">
            {FEATURES.map((f) => (
              <article key={f.title} className="lp-feature-card">
                <div className="lp-feature-icon" aria-hidden="true">{f.icon}</div>
                <h3 className="lp-feature-title">{f.title}</h3>
                <p className="lp-feature-desc">{f.desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── How It Works ─────────────────────────────────────────── */}
      <section className="lp-section lp-section-alt" id="how-it-works" aria-labelledby="hiw-title">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-eyebrow">How It Works</span>
            <h2 className="lp-section-title" id="hiw-title">
              From documents to answers<br />in three steps
            </h2>
            <p className="lp-section-sub">
              No PhD in ML required. Lumora handles the retrieval pipeline — you focus on the
              knowledge.
            </p>
          </div>

          <div className="lp-steps">
            {[
              {
                num: '1',
                title: 'Connect Your Knowledge Sources',
                desc: 'Add URLs, sitemaps, or upload PDFs. Lumora\'s intelligent crawler handles section-recursive scraping, PDF extraction, chunking, and vector embedding — all on a configurable schedule.',
              },
              {
                num: '2',
                title: 'Ask in Plain Language',
                desc: 'Users type natural-language questions in the chat interface. No query syntax, no boolean operators, no training required. Your whole team can find answers from day one.',
              },
              {
                num: '3',
                title: 'Get Cited, Grounded Answers',
                desc: 'Lumora retrieves the most relevant document chunks, generates a precise answer grounded in evidence, and shows exactly which sources it used — downloadable and shareable.',
              },
            ].map((step) => (
              <div key={step.num} className="lp-step">
                <div className="lp-step-num" aria-hidden="true">{step.num}</div>
                <h3 className="lp-step-title">{step.title}</h3>
                <p className="lp-step-desc">{step.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Why Lumora ───────────────────────────────────────────── */}
      <section className="lp-section" id="uniqueness" aria-labelledby="unique-title">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-eyebrow">Why Lumora</span>
            <h2 className="lp-section-title" id="unique-title">
              What sets Lumora apart
            </h2>
            <p className="lp-section-sub">
              Dozens of RAG tools exist. Here is why researchers, developers, and institutions choose
              Lumora.
            </p>
          </div>

          <div className="lp-unique-grid">
            {UNIQUE.map((u) => (
              <div key={u.title} className="lp-unique-item">
                <span className="lp-unique-check" aria-hidden="true">✓</span>
                <div>
                  <div className="lp-unique-title">{u.title}</div>
                  <p className="lp-unique-desc">{u.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Use Cases ────────────────────────────────────────────── */}
      <section
        className="lp-section lp-section-dark"
        id="use-cases"
        aria-labelledby="usecases-title"
      >
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-eyebrow">Use Cases</span>
            <h2 className="lp-section-title" id="usecases-title">
              Built for teams that run on knowledge
            </h2>
            <p className="lp-section-sub">
              From research labs to enterprise helpdesks — if your team answers questions from
              documents, Lumora is for you.
            </p>
          </div>

          <div className="lp-use-cases-grid">
            {USE_CASES.map((uc) => (
              <article key={uc.title} className="lp-use-case-card">
                <div className="lp-use-case-icon" aria-hidden="true">{uc.icon}</div>
                <h3 className="lp-use-case-title">{uc.title}</h3>
                <p className="lp-use-case-desc">{uc.desc}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tech Stack ───────────────────────────────────────────── */}
      <section className="lp-section lp-section-alt" id="tech-stack" aria-labelledby="tech-title">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-eyebrow">Tech Stack</span>
            <h2 className="lp-section-title" id="tech-title">
              Transparent, auditable,<br />production-ready
            </h2>
            <p className="lp-section-sub">
              No framework lock-in. Every component is replaceable, documented, and open source.
            </p>
          </div>

          <div className="lp-tech-rows">
            {TECH_STACK.map((row) => (
              <div key={row.category} className="lp-tech-row">
                <div className="lp-tech-category">{row.category}</div>
                <div className="lp-tech-badges">
                  {row.badges.map((b) => (
                    <span key={b} className="lp-tech-badge">{b}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Roadmap ──────────────────────────────────────────────── */}
      <section
        className="lp-section lp-section-dark"
        id="roadmap"
        aria-labelledby="roadmap-title"
      >
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-eyebrow">Roadmap</span>
            <h2 className="lp-section-title" id="roadmap-title">
              What's shipped and what's next
            </h2>
            <p className="lp-section-sub">
              Lumora is actively developed. The roadmap is public and community-driven — your voice
              shapes what ships next.
            </p>
          </div>

          <div className="lp-roadmap-cols">
            <div>
              <div className="lp-roadmap-col-title" style={{ color: '#14b8a6' }}>
                ✅ Shipped
              </div>
              <div className="lp-roadmap-list">
                {ROADMAP_DONE.map((item) => (
                  <div key={item} className="lp-roadmap-item done">
                    <span className="lp-roadmap-icon">✓</span>
                    {item}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="lp-roadmap-col-title" style={{ color: 'rgba(255,255,255,0.5)' }}>
                🛠️ Coming Soon
              </div>
              <div className="lp-roadmap-list">
                {ROADMAP_UPCOMING.map((item) => (
                  <div key={item} className="lp-roadmap-item upcoming">
                    <span className="lp-roadmap-icon">○</span>
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ textAlign: 'center', marginTop: 40 }}>
            <a
              href={GITHUB_DISCUSSIONS}
              target="_blank"
              rel="noopener noreferrer"
              className="lp-btn lp-btn-outline lp-btn-lg"
              style={{ color: '#14b8a6', borderColor: 'rgba(20,184,166,0.4)' }}
            >
              Vote on the Roadmap →
            </a>
          </div>
        </div>
      </section>

      {/* ── Open Source ──────────────────────────────────────────── */}
      <section className="lp-section" id="open-source" aria-labelledby="oss-title">
        <div className="lp-section-inner">
          <div className="lp-section-header">
            <span className="lp-eyebrow">Open Source</span>
            <h2 className="lp-section-title" id="oss-title">
              Join the Lumora community
            </h2>
            <p className="lp-section-sub">
              Lumora is built in the open. Every issue, PR, and discussion is welcome. We believe
              AI knowledge management should be transparent, auditable, and collectively owned.
            </p>
          </div>

          <div className="lp-oss-grid">
            <div className="lp-oss-card">
              <div className="lp-oss-icon" aria-hidden="true">🛠️</div>
              <h3 className="lp-oss-title">Contribute Code</h3>
              <p className="lp-oss-desc">
                Fix bugs, add features, improve documentation. All skill levels welcome — from
                first-timers to ML engineers. We follow conventional commits and keep reviews fast.
              </p>
              <a
                href={GITHUB_ISSUES}
                target="_blank"
                rel="noopener noreferrer"
                className="lp-btn lp-btn-outline"
              >
                Browse Open Issues
              </a>
            </div>

            <div className="lp-oss-card">
              <div className="lp-oss-icon" aria-hidden="true">💬</div>
              <h3 className="lp-oss-title">Shape the Roadmap</h3>
              <p className="lp-oss-desc">
                Have an idea for Lumora? Open a GitHub Discussion. The roadmap is community-driven —
                the most-requested features get prioritized. Your use case matters.
              </p>
              <a
                href={GITHUB_DISCUSSIONS}
                target="_blank"
                rel="noopener noreferrer"
                className="lp-btn lp-btn-outline"
              >
                Start a Discussion
              </a>
            </div>

            <div className="lp-oss-card">
              <div className="lp-oss-icon" aria-hidden="true">⭐</div>
              <h3 className="lp-oss-title">Spread the Word</h3>
              <p className="lp-oss-desc">
                Star the repo, share Lumora with your team, or write about it. Every star signals
                to the community that open-source AI infrastructure is worth investing in.
              </p>
              <a
                href={GITHUB_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="lp-btn lp-btn-primary"
              >
                ⭐ Star on GitHub
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ── Funding & Sponsorship ────────────────────────────────── */}
      <section className="lp-funding" id="funding" aria-labelledby="funding-title">
        <div className="lp-funding-inner">
          <div className="lp-eyebrow" style={{ color: 'rgba(255,255,255,0.55)' }}>
            Funding &amp; Sponsorship
          </div>
          <h2 className="lp-funding-title" id="funding-title">
            Help Lumora grow
          </h2>
          <p className="lp-funding-sub">
            Lumora is built and maintained by researchers and developers who believe AI knowledge
            management should be open and accessible to everyone — not just those who can afford
            expensive proprietary platforms. Your support directly funds development time,
            infrastructure, and new features.
          </p>

          <div className="lp-funding-options">
            <a
              href={GITHUB_SPONSORS}
              target="_blank"
              rel="noopener noreferrer"
              className="lp-funding-option"
            >
              <div className="lp-funding-option-icon">💖</div>
              <div className="lp-funding-option-title">GitHub Sponsors</div>
              <div className="lp-funding-option-sub">Become a recurring sponsor</div>
            </a>

            <a href={GITHUB_DISCUSSIONS} target="_blank" rel="noopener noreferrer" className="lp-funding-option">
              <div className="lp-funding-option-icon">🔬</div>
              <div className="lp-funding-option-title">Research Partnership</div>
              <div className="lp-funding-option-sub">Academic &amp; industry collaboration</div>
            </a>

            <a href={GITHUB_DISCUSSIONS} target="_blank" rel="noopener noreferrer" className="lp-funding-option">
              <div className="lp-funding-option-icon">🏢</div>
              <div className="lp-funding-option-title">Enterprise Support</div>
              <div className="lp-funding-option-sub">Priority issues, custom integrations</div>
            </a>

            <a href={GITHUB_DISCUSSIONS} target="_blank" rel="noopener noreferrer" className="lp-funding-option">
              <div className="lp-funding-option-icon">🎓</div>
              <div className="lp-funding-option-title">Academic Grant</div>
              <div className="lp-funding-option-sub">Partner with IUB research team</div>
            </a>
          </div>
        </div>
      </section>

      {/* ── Final CTA ────────────────────────────────────────────── */}
      <section className="lp-cta" aria-labelledby="cta-title">
        <h2 className="lp-cta-title" id="cta-title">
          Ready to illuminate your knowledge?
        </h2>
        <p className="lp-cta-sub">
          Try the live demo in seconds — no signup required. Or deploy your own instance in minutes.
        </p>
        <div className="lp-cta-buttons">
          <Link href="/login" className="lp-btn lp-btn-primary lp-btn-lg">
            Try Live Demo →
          </Link>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="lp-btn lp-btn-ghost lp-btn-lg"
          >
            Deploy Your Own ↗
          </a>
        </div>
      </section>

      {/* ── Footer ───────────────────────────────────────────────── */}
      <footer className="lp-footer" aria-label="Site footer">
        <div className="lp-footer-inner">
          <div className="lp-footer-top">
            <div>
              <a href="/" className="lp-logo" style={{ marginBottom: 8 }}>
                <span className="lp-logo-mark" aria-hidden="true">L</span>
                <span className="lp-logo-name" style={{ color: '#fff' }}>Lumora</span>
              </a>
              <div className="lp-footer-brand-tag" style={{ marginTop: 8 }}>
                Illuminate your knowledge.
              </div>
            </div>

            <div className="lp-footer-links-group">
              <div className="lp-footer-col">
                <div className="lp-footer-col-title">Product</div>
                <a href="#features">Features</a>
                <a href="#how-it-works">How It Works</a>
                <a href="#roadmap">Roadmap</a>
                <a href="#tech-stack">Tech Stack</a>
                <Link href="/login">Try Demo</Link>
              </div>

              <div className="lp-footer-col">
                <div className="lp-footer-col-title">Community</div>
                <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
                <a href={GITHUB_ISSUES} target="_blank" rel="noopener noreferrer">Issues</a>
                <a href={GITHUB_DISCUSSIONS} target="_blank" rel="noopener noreferrer">Discussions</a>
                <a href={GITHUB_SPONSORS} target="_blank" rel="noopener noreferrer">Sponsors</a>
              </div>

              <div className="lp-footer-col">
                <div className="lp-footer-col-title">Legal</div>
                <a
                  href={`${GITHUB_URL}/blob/main/LICENSE`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  MIT License
                </a>
                <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">Open Source</a>
              </div>
            </div>
          </div>

          <div className="lp-footer-bottom">
            <span>
              © 2024–2025 Lumora · Built with care at{' '}
              <a href="https://iub.edu.pk" target="_blank" rel="noopener noreferrer">IUB</a>
              {' '}· MIT License
            </span>
            <span style={{ display: 'flex', gap: 16 }}>
              <a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">GitHub</a>
              <a
                href={`${GITHUB_URL}/blob/main/LICENSE`}
                target="_blank"
                rel="noopener noreferrer"
              >
                License
              </a>
              <Link href="/login">Demo</Link>
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
