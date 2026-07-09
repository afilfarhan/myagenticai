# SentinelChain

**An Agentic Supply Chain Risk & Compliance Engine**

A multi-agent autonomous system that continuously ingests global news, financial reports, sanctions lists, and environmental data to proactively flag risks, draft mitigation strategies, and execute compliance workflows — reducing analyst data-gathering time from 80% to 10%.

---

## Features

### Multi-Agent Swarm
| Agent | Role | Capabilities |
|-------|------|-------------|
| **Scout** | Data Acquisition | Sanctions monitoring, news search, financial report retrieval, satellite imagery, government registry scraping, dark web monitoring |
| **Analyst** | Reasoning & Synthesis | Cross-reference analysis, probabilistic modeling, Monte Carlo simulations, financial analysis, pattern recognition, trend analysis |
| **Auditor** | Compliance Verification | OFAC sanctions screening, EU CSDDD compliance, ESG verification, export control screening, anti-money laundering checks |
| **Mitigator** | Action & Remediation | Alternative sourcing, financial impact calculation, procurement ticket generation, supplier communication drafting, contingency planning |

### Core Capabilities
- **Autonomous Risk Discovery** (Push) — Continuous polling detects new sanctions, cross-references suppliers, and auto-flags risks with near-real-time MTTD < 4 hours
- **Deep-Dive Investigations** (Pull) — User-initiated queries spin up dedicated agent crews; results streamed live to the UI via Server-Sent Events
- **Human-in-the-Loop (HITL)** — Severe/compliance-critical findings pause the workflow, push Slack alerts, and wait for human Approve/Deny before actions execute
- **Cyclic Agent Reasoning** — LangGraph state machine allows agents to loop back (e.g., insufficient evidence → Scout re-gathers → Analyst re-evaluates) before alerting
- **Multi-Source Verification** — Risk scores require verifiable source URLs/document IDs; Guardrails AI enforces structured JSON output
- **Real-Time Streaming UI** — Next.js + Vercel AI SDK shows agent reasoning steps as they happen
- **PII Masking** — Microsoft Presidio scrubs names, addresses, emails, and phone numbers before data reaches public LLMs
- **Prompt Injection Protection** — Guardrails AI sanitizes all scraped web content treated as untrusted input
- **Semantic Caching** — GPTCache-style query caching keeps cost under $0.50/supplier/month
- **LLM Failover** — LiteLLM gateway: Anthropic → GPT-4o → Bedrock → queue with PagerDuty alert
- **Secure Code Execution** — E2B sandbox isolates Monte Carlo simulations and financial scripts from the host
- **Model Context Protocol (MCP)** — All internal tools (databases, CRM, ERP) exposed as standardized MCP servers with granular access

### Dashboard & UI
- Real-time risk dashboard with alerts, workflow status, and agent health
- Supplier management with filtering by tier, country, industry, and risk level
- Investigation builder with streaming workflow timeline
- HITL approval panel embedded in the investigation view
- Agent status indicators showing Scout/Analyst/Auditor/Mitigator operational state
- Risk score bar charts and severity badges

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Next.js Frontend                      │
│  Dashboard │ Suppliers │ Investigations │ HITL Panel    │
│              Vercel AI SDK (SSE Streaming)               │
└──────────────────────┬──────────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI Backend                         │
│  /api/v1/suppliers  /api/v1/investigations  /health      │
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│ LangGraph │  │  CrewAI   │  │  Tool     │
│ State     │  │  Crews    │  │  Registry │
│ Machine   │  │           │  │           │
└─────┬─────┘  └─────┬─────┘  └─────┬─────┘
      │              │              │
      ▼              ▼              ▼
┌─────────────────────────────────────────────────────────┐
│                     Agent Swarm                          │
│  Scout ──► Analyst ──► Auditor ──► Mitigator            │
│    ▲          │           │                               │
│    └──────────┘  (loop back for more evidence)           │
│                                                          │
│  HITL Interrupt: SEVERE/CRITICAL → Slack → Human → Resume│
└──────────────────────┬──────────────────────────────────┘
                       │
         ┌──────────────┼──────────────┬──────────────┐
         ▼              ▼              ▼              ▼
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│ Pinecone  │  │   Redis   │  │  Tavily   │  │    E2B    │
│ (Vector)  │  │ (Session) │  │  (Search) │  │ (Sandbox) │
└───────────┘  └───────────┘  └───────────┘  └───────────┘
         ▼              ▼              ▼              ▼
┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐
│   Exa     │  │   Apify   │  │    MCP    │  │ Guardrails│
│(Semantic) │  │ (Scraper) │  │ (Internal)│  │   + W&B   │
└───────────┘  └───────────┘  └───────────┘  └───────────┘
```

### LLM Strategy (LiteLLM Gateway with Failover)
| Role | Provider | Model | Use Case |
|------|----------|-------|----------|
| **Primary** | Anthropic | Claude 3.5 Sonnet | Primary reasoning (tool-use accuracy, 200K context for long PDFs) |
| **Multimodal** | OpenAI | GPT-4o | Multimodal (satellite imagery interpretation) |
| **Secure** | AWS Bedrock | Llama 3.1 70B | PII-sensitive compliance checks (never leaves corporate VPC) |
| **Fallback** | LiteLLM | Auto | Automatic failover chain: Anthropic → GPT-4o → Bedrock → Redis queue |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Redis (or Docker)
- Pinecone account
- API keys: Anthropic, OpenAI, Tavily, Exa, Apify, E2B, LangSmith, W&B

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate
pip install -r requirements.txt

# Create .env with your keys:
cp .env.example .env

# Start the API (http://localhost:8000)
uvicorn app.main:app --reload
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# Opens at http://localhost:3000
```

### 3. Verify

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"1.0.0",...}

curl http://localhost:8000/api/v1/agents/status
# {"scout":{"status":"ready","capabilities":[...]}, ...}
```

---

## Implementation Status

### ✅ Phase 0 — Foundation (Complete)
- **Database Layer**: SQLAlchemy 2.0 async models (Supplier, Investigation, Evidence, RiskFactor, MitigationAction, AlternativeSupplier, AgentMessage, CostTracking)
- **Configuration Service**: Pydantic Settings with YAML + `.env` support
- **Redis Manager**: Session cache, pub/sub for SSE, rate limiting, semantic LLM caching
- **Pinecone Vector Store**: Supplier profiles, evidence, risk assessments with mock fallback
- **Embedding Service**: sentence-transformers (local) + OpenAI/Bedrock support with mock fallback

### ✅ Phase 1 — Tool Infrastructure (Complete)
- **Tavily Search**: News/web search with PII masking
- **Exa Semantic Search**: Historical supply chain disruption search
- **Apify Scraper**: Government sanctions lists, registry scraping
- **E2B Sandbox**: Monte Carlo simulations, financial analysis
- **MCP Tool Registry**: CRM, ERP, internal database tools
- **Tool Orchestrator**: Unified execution interface with tracing

### ✅ Phase 2 — Memory & Safety (Complete)
- **MemoryManager**: Coordinates DB, Redis, Pinecone, Embeddings
- **PII Masking**: Microsoft Presidio + regex fallback (PERSON, LOCATION, EMAIL, PHONE, CREDIT_CARD, IBAN, IP, SSN, PASSPORT)
- **Guardrails AI**: Structured output validation + prompt injection detection

### ✅ Phase 3 — Agent Implementation (Complete)
- **ScoutAgent**: Real Tavily/Exa/Apify/MCP tool calls → Evidence objects with source URLs
- **AnalystAgent**: LLM risk synthesis with Guardrails validation, evidence citation enforcement, semantic caching
- **AuditorAgent**: OFAC/CSDDD/ESG/export control checks, HITL trigger for SEVERE/CRITICAL
- **MitigatorAgent**: LLM mitigation generation + Pinecone alternative supplier search
- **OrchestratorAgent**: CrewAI integration for deep-dive, LangGraph for autonomous discovery

### ✅ Phase 4 — LangGraph Workflow (Complete)
- **HITL Interrupts**: `interrupt_before=["auditor"]` with `Command(resume=hitl_response)`
- **SSE Streaming**: Redis pub/sub per workflow, real-time agent step updates
- **Cost Tracking**: Per-workflow/supplier token usage and USD cost

### ✅ Phase 5 — API Completion (Complete)
- **Supplier CRUD**: Full lifecycle with vector store sync + background tasks
- **Investigation CRUD**: Start, status, SSE stream, HITL resume
- **Dev Seed Endpoint**: `POST /api/v1/seed` generates 50 dummy suppliers
- **Agent Status**: Real capabilities from registered agents

### ✅ Phase 6 — Frontend Integration (Complete)
- **API Client**: REST + SSE with auth headers
- **Dashboard**: Real stats, agent health, recent alerts, active workflows
- **Suppliers**: Filterable table, risk bars, add supplier modal
- **Investigations**: Streaming SSE updates, HITL panel, results view
- **Build**: ✅ Compiles (6 static pages, 86.9 kB shared JS)

### ✅ Phase 7 — Observability, Eval & Security (Complete)
- **LangSmith Tracing**: `@traceable` on all agents, tools, LLM calls
- **W&B Weave Evaluation**: Golden set (8 cases), F1/citation/compliance scorers, CI-ready
- **LiteLLM Gateway**: Failover chain, cost tracking, token counting
- **JWT Auth**: Access/refresh tokens, tier-based rate limits, scope-based permissions
- **Audit Logging**: Structured events, correlation IDs, compliance reports (SOC2/ISO27001/GDPR)
- **Prometheus Metrics**: LLM calls, costs, cache hits with Grafana dashboards

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | System metrics |
| `GET` | `/api/v1/agents/status` | Agent operational status |
| `POST` | `/api/v1/suppliers` | Create supplier |
| `GET` | `/api/v1/suppliers` | List suppliers (filterable) |
| `GET` | `/api/v1/suppliers/{id}` | Get supplier details |
| `PATCH` | `/api/v1/suppliers/{id}` | Update supplier |
| `DELETE` | `/api/v1/suppliers/{id}` | Delete supplier (soft) |
| `POST` | `/api/v1/seed` | Generate 50 dummy suppliers (dev) |
| `POST` | `/api/v1/investigations` | Start investigation workflow |
| `GET` | `/api/v1/investigations/{id}` | Get workflow status |
| `GET` | `/api/v1/investigations/{id}/stream` | SSE stream of agent steps |
| `POST` | `/api/v1/investigations/{id}/hitl` | Submit HITL response |
| `GET` | `/api/v1/config` | Public configuration |
| `GET` | `/api/v1/audit/events` | List audit events |
| `GET` | `/api/v1/audit/stats` | Audit statistics |
| `POST` | `/api/v1/audit/test` | Create test audit event |

---

## Configuration

`backend/config.yaml` controls all runtime behavior:

```yaml
llm:
  primary:
    provider: "anthropic"
    model: "claude-3-5-sonnet-20241022"
    temperature: 0.1
    max_tokens: 8192
  multimodal:
    provider: "openai"
    model: "gpt-4o"
  secure:
    provider: "bedrock"
    model: "meta.llama3-1-70b-instruct-v1:0"
    region: "us-east-1"

langgraph:
  recursion_limit: 10
  checkpoint_interval: 5

memory:
  pinecone:
    index_name: "sentinelchain-suppliers"
    dimension: 1536
  redis:
    url: "redis://localhost:6379"
  embeddings:
    provider: "sentence_transformers"
    model: "all-MiniLM-L6-v2"
    dimension: 384

auth:
  jwt_secret: "${JWT_SECRET_KEY}"
  access_token_ttl_min: 15
  refresh_token_ttl_days: 7

cost_control:
  semantic_cache: true
  monthly_budget_usd: 1000
  cost_per_supplier_target: 0.50

observability:
  langsmith:
    enabled: true
    project: "sentinelchain-prod"
  wandb:
    enabled: true
    project: "sentinelchain-eval"
```

Environment variables (`.env`):
```env
# LLM Providers
ANTHROPIC_API_KEY=    OPENAI_API_KEY=       TAVILY_API_KEY=
EXA_API_KEY=          APIFY_API_TOKEN=      E2B_API_KEY=

# Vector Database
PINECONE_API_KEY=     PINECONE_ENVIRONMENT=us-east-1

# Cache & Session
REDIS_URL=redis://localhost:6379

# Observability
LANGSMITH_API_KEY=    WANDB_API_KEY=        WANDB_ENTITY=

# Database
DATABASE_URL=sqlite+aiosqlite:///./sentinelchain.db

# Security
JWT_SECRET_KEY=your-32-byte-secret-here
SLACK_WEBHOOK_URL=
```

---

## Project Structure

```
sentinelchain/
├── backend/
│   ├── app/
│   │   ├── agents/__init__.py        # Scout, Analyst, Auditor, Mitigator, Orchestrator
│   │   ├── graph/__init__.py         # LangGraph state machine with HITL interrupts
│   │   ├── memory/__init__.py        # MemoryManager coordinating all stores
│   │   │   ├── redis_manager.py      # Redis session/cache/pubsub/rate-limit
│   │   │   ├── vector_store.py       # Pinecone supplier/evidence/risk vectors
│   │   ├── models/__init__.py        # Pydantic models (Supplier, RiskFactor, Evidence, etc.)
│   │   ├── schemas/__init__.py       # Request/response schemas
│   │   ├── tools/__init__.py         # Tavily, Exa, Apify, E2B, MCP tool registry
│   │   ├── services/
│   │   │   ├── database.py           # SQLAlchemy async models + DatabaseService
│   │   │   ├── config.py             # Pydantic Settings with YAML + .env
│   │   │   ├── embeddings.py         # sentence-transformers + OpenAI/Bedrock
│   │   │   ├── pii_masking.py        # Microsoft Presidio + regex fallback
│   │   │   ├── guardrails.py         # Structured output + prompt injection
│   │   │   ├── llm_gateway.py        # LiteLLM failover + cost tracking
│   │   │   └── audit.py              # Structured audit logging + compliance
│   │   ├── api/
│   │   │   ├── auth.py               # JWT + API key auth, rate limiting, permissions
│   │   │   └── audit.py              # Audit API endpoints
│   │   ├── config.py                 # Configuration loader
│   │   └── main.py                   # FastAPI app with lifespan + routers
│   ├── config.yaml                   # YAML configuration
│   ├── requirements.txt              # All Python dependencies
│   ├── pyproject.toml                # Project metadata + tool configs
│   └── .env.example                  # Environment variable template
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx              # Dashboard (stats, alerts, workflows, agents)
│   │   │   ├── layout.tsx            # Root layout
│   │   │   ├── providers.tsx         # React Query + Toast provider
│   │   │   ├── loading.tsx           # Loading skeleton
│   │   │   ├── error.tsx             # Error boundary
│   │   │   ├── investigations/page.tsx  # Investigation builder + SSE + HITL
│   │   │   └── suppliers/page.tsx    # Supplier table with filters
│   │   └── lib/
│   │       ├── api.ts                # API client (REST + SSE streaming)
│   │       └── utils.ts              # cn(), formatDate, risk colors, icons
│   ├── package.json                  # Next.js 14, Vercel AI SDK, react-query, recharts
│   ├── tsconfig.json                 # TypeScript strict mode
│   └── tailwind.config.js            # Custom risk colors + animations
├── docs/
│   ├── PRD-IMPLEMENTATION.md         # Complete implementation guide
│   └── PRD-PHASE7.md                 # Phase 7 detailed requirements
├── .gitignore
└── README.md
```

---

## Success Metrics (KPIs)

| Metric | Manual Baseline | SentinelChain Target |
|--------|----------------|---------------------|
| Mean Time to Detect (MTTD) | 14 Days | < 4 Hours |
| Analyst Time on Data Gathering | 80% | 10% |
| False Positive Rate | 45% | < 15% |
| Cost per Risk Assessment | $150 (labor) | $12 (compute) |

---

## Phased Rollout

| Phase | Weeks | Deliverables |
|-------|-------|-------------|
| **Alpha** | 1–4 | LangGraph + Scout + Analyst + Tavily + MCP + 50 dummy suppliers |
| **Beta** | 5–8 | Auditor + Mitigator + HITL via Slack + Guardrails + live enterprise data (shadow mode) |
| **V1 GA** | 9–12 | Next.js frontend + Vercel AI SDK + E2B + Llama 3.1 via Bedrock + autonomous actions for low/medium risk |

---

## Security

- **PII Masking:** Microsoft Presidio scrubs PERSON, LOCATION, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, IBAN_CODE, IP_ADDRESS before data reaches Claude/GPT-4o
- **Prompt Injection:** Guardrails AI threshold-based detection on all user inputs + scraped web content
- **Internal Access:** OAuth 2.0 + zero-trust network for CRM/ERP tool calls
- **Structured Output:** Guardrails AI enforces strict JSON risk taxonomy — blocks "creative" LLM outputs
- **Sandboxed Code:** E2B isolates all Analyst financial scripts and Monte Carlo simulations
- **Auth:** JWT with tier-based rate limits, scope-based permissions, API key support for service accounts
- **Audit:** Structured logging with correlation IDs, real-time alerts, compliance reports (SOC2/ISO27001/GDPR)

---

## License

Proprietary — All rights reserved.