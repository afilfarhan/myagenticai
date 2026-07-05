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
- **LLM Failover** — If Anthropic rate-limits, automatically falls back to GPT-4o; if both fail, queues in Redis for retry with optional PagerDuty alert
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

### LLM Strategy
| Provider | Model | Use Case |
|----------|-------|----------|
| Anthropic | Claude 3.5 Sonnet | Primary reasoning (tool-use accuracy, 200K context for long PDFs) |
| OpenAI | GPT-4o | Multimodal (satellite imagery interpretation) |
| AWS Bedrock | Llama 3.1 70B | PII-sensitive compliance checks (never leaves corporate VPC) |

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
| `DELETE` | `/api/v1/suppliers/{id}` | Delete supplier |
| `POST` | `/api/v1/investigations` | Start investigation workflow |
| `GET` | `/api/v1/investigations/{id}` | Get workflow status |
| `GET` | `/api/v1/investigations/{id}/stream` | SSE stream of agent steps |
| `POST` | `/api/v1/investigations/{id}/hitl` | Submit HITL response |
| `GET` | `/api/v1/config` | Public configuration |

---

## Use Cases

### 1. Autonomous Sanctions Monitoring
**Scenario:** A new entity is added to the EU sanctions list.

1. **Scout** continuously polls Apify for sanctions registry updates
2. Finds new sanctioned entity; queries Pinecone → discovers it's a Tier-2 sub-contractor for your supplier
3. **Analyst** searches Tavily for context, confirms money laundering violation
4. **Auditor** checks against OFAC/CSDDD frameworks, flags as **SEVERE**
5. **HITL interrupt:** Graph pauses, sends Slack alert to Chief Compliance Officer: *"Supplier Y uses sanctioned Entity X. Recommend freezing payments. Approve?"*
6. CCO clicks "Approve" → **Mitigator** drafts email to supplier, logs event in CRM

### 2. Financial Stability Investigation
**Scenario:** User types: *"Investigate financial stability of TechCorp Taiwan over last 6 months"*

1. Orchestrator spins up dedicated CrewAI crew
2. **Scout** pulls latest 10-Q filing → Unstructured.io parses tables/text
3. **Analyst** reads filing, detects 40% drop in cash reserves → E2B runs solvency ratio script
4. Results streamed live via Vercel AI SDK: summary, solvency chart, and 3 recommended alternative suppliers

### 3. ESG Compliance Audit
**Scenario:** Quarterly ESG review of all Tier-1 suppliers.

1. **Scout** gathers environmental reports, news articles, regulatory filings for each supplier
2. **Analyst** cross-references with ESG framework requirements
3. **Auditor** validates against CSDDD and local environmental regulations
4. Generates compliance gap report with priority-ranked remediation actions

### 4. Supply Chain Disruption Response
**Scenario:** Port strike detected at major shipping hub.

1. **Scout** detects news of port strike via Tavily
2. **Analyst** cross-references supplier shipping manifests → calculates probabilistic delay (Monte Carlo via E2B)
3. **Mitigator** identifies alternative suppliers with lower risk scores, calculates cost/lead-time differences, pre-fills procurement tickets

---

## Configuration

`backend/config.yaml` controls all runtime behavior:

```yaml
llm:
  primary:    anthropic / claude-3-5-sonnet-20241022
  multimodal: openai / gpt-4o
  secure:     bedrock / meta.llama3-1-70b-instruct-v1:0

langgraph:
  recursion_limit: 10     # prevents infinite agent loops

cost_control:
  semantic_cache: true    # GPTCache-style deduplication
  monthly_budget_usd: 1000
  cost_per_supplier_target: 0.50

security:
  presidio: true          # PII masking before LLM calls
  guardrails: true        # structured output + prompt injection detection

hitl:
  slack_webhook: ...
  approval_required_for: [SEVERE, CRITICAL]
```

Environment variables (`.env`):
```env
ANTHROPIC_API_KEY=    OPENAI_API_KEY=       TAVILY_API_KEY=
EXA_API_KEY=          APIFY_API_TOKEN=      E2B_API_KEY=
PINECONE_API_KEY=     REDIS_URL=redis://localhost:6379
LANGSMITH_API_KEY=    WANDB_API_KEY=        DATABASE_URL=sqlite+aiosqlite:///./sentinelchain.db
SLACK_WEBHOOK_URL=
```

---

## Project Structure

```
sentinelchain/
├── backend/
│   ├── app/
│   │   ├── agents/__init__.py    # Scout, Analyst, Auditor, Mitigator, Orchestrator
│   │   ├── graph/__init__.py     # LangGraph state machine with HITL interrupts
│   │   ├── memory/__init__.py    # Pinecone vector store + Redis session/cache
│   │   ├── models/__init__.py    # Pydantic models (Supplier, RiskFactor, Evidence, etc.)
│   │   ├── schemas/__init__.py   # Request/response schemas
│   │   ├── tools/__init__.py     # Tavily, Exa, Apify, E2B, MCP tool registry
│   │   ├── config.py             # Configuration loader (Pydantic Settings)
│   │   └── main.py               # FastAPI application with lifespan
│   ├── config.yaml               # YAML configuration
│   ├── requirements.txt          # All Python dependencies
│   └── pyproject.toml            # Project metadata + tool configs (ruff, mypy, pytest)
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           # Dashboard (stats, alerts, workflows, agents)
│   │   │   ├── layout.tsx         # Root layout
│   │   │   ├── providers.tsx      # React Query + Toast provider
│   │   │   ├── loading.tsx        # Loading skeleton
│   │   │   ├── error.tsx          # Error boundary
│   │   │   ├── investigations/page.tsx  # Investigation builder + SSE stream + HITL panel
│   │   │   └── suppliers/page.tsx       # Supplier table with filters
│   │   └── lib/
│   │       ├── api.ts             # API client (REST + SSE streaming)
│   │       └── utils.ts           # cn(), formatDate, risk colors, icons
│   ├── package.json               # Next.js 14, Vercel AI SDK, react-query, recharts
│   ├── tsconfig.json              # TypeScript strict mode
│   └── tailwind.config.js         # Custom risk colors + animations
├── .gitignore                     # Python, Node, IDE, env files
├── PRD.md                         # Original Product Requirements Document
└── README.md                      # (this file)
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

## Contributing

See [CONTRIBUTING.md](docs/CONTRIBUTING.md).

## License

Proprietary — All rights reserved.