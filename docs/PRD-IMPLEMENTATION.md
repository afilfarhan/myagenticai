# Product Requirements Document (PRD)
## SentinelChain — AI Agent Implementation Guide
**Document Version:** 2.0
**Audience:** AI agents and developers implementing the SentinelChain backend, frontend, and agent capabilities
**Scope:** All main features that must be implemented to reach a functional V1

---

## 1. Executive Summary

SentinelChain is a **multi-agent autonomous supply chain risk & compliance engine**. The project currently has a structural scaffold (directory layout, type definitions, API endpoints, frontend UI shell). Every core behavioral feature — agent reasoning, data acquisition, risk analysis, compliance checking, investigation workflows, SSE streaming, and the frontend data layer — is either a stub or a mock.

This PRD defines exactly what must be built, in what order, and how to verify each feature. It is the source of truth for any AI agent or developer tasked with implementation.

---

## 2. Current State Assessment

### What Exists (Do Not Rebuild)
- **Project structure:** `backend/app/` with `agents/`, `graph/`, `memory/`, `models/`, `schemas/`, `tools/`, `services/`, `api/`, `config.py`, `main.py`
- **Pydantic models:** `Supplier`, `RiskFactor`, `Evidence`, `MitigationAction`, `AlternativeSupplier`, `WorkflowState`, `AgentRole`, `RiskLevel`, `RiskCategory`, `WorkflowType`, `HITLStatus`, `SupplierTier`, `InvestigationRequest`, `InvestigationResponse`, `HITLResponse`
- **Schemas:** Request/response schemas for suppliers, investigations, HITL, health, metrics, agent status
- **LangGraph skeleton:** `GraphState`, routing functions, `SentinelWorkflowRunner` class
- **Frontend pages:** Dashboard (`page.tsx`), suppliers page, investigations page, layout, providers
- **Frontend lib:** `api.ts` (REST + SSE client skeleton), `utils.ts`
- **Config:** `config.yaml`, `pyproject.toml`, `requirements.txt`
- **Agent base classes:** `BaseAgent`, `ScoutAgent`, `AnalystAgent`, `AuditorAgent`, `MitigatorAgent`, `OrchestratorAgent` in `backend/app/agents/__init__.py`

### What Is Missing or Stub
- Every real tool call (Tavily, Exa, Apify, Pinecone, E2B, MCP)
- Every real LLM call (Claude, GPT-4o, Bedrock Llama)
- Database layer (no SQLAlchemy or ORM setup)
- Redis session/cache management
- Vector store operations (Pinecone)
- Document parsing pipeline (Unstructured.io)
- Guardrails AI integration (structured output + prompt injection guard)
- Presidio PII masking
- Real SSE streaming wired to investigation state
- Frontend data fetching (all pages use `mockStats`, `mockRecentAlerts`, `mockActiveWorkflows`)
- HITL Slack notification integration
- Error handling, retry, and failover logic
- Cost tracking and W&B evaluation hooks
- Tests (directory is empty)

---

## 3. Feature Implementation Plan

Features are ordered by dependency. An AI agent must complete them in sequence (or within the same phase, in parallel where noted).

---

### Phase 0 — Foundation (Prerequisite for Everything)

#### 0.1 Database Layer
**File:** `backend/app/services/database.py` (new file)

Create an async SQLAlchemy (or `aiosqlite` + SQLAlchemy 2.0) database service.

Models to persist:
- `Supplier` — id, name, country, industry, tier, is_active, created_at, updated_at
- `Investigation` — id, workflow_id (UUID), supplier_id (FK), status, created_at, result (JSON)
- `RiskFactor` — id, investigation_id (FK), category, level, title, description, confidence, evidence (JSON), metadata (JSON)
- `MitigationAction` — id, investigation_id (FK), title, description, status
- `AlternativeSupplier` — id, investigation_id (FK), name, risk_score, cost_diff, lead_time_diff

Acceptance criteria:
- `pip install sqlalchemy[asyncio] aiosqlite` added to `requirements.txt`
- `DATABASE_URL` read from `config.yaml` or `settings.ENV`
- Session factory with `async_sessionmaker`
- `init_db()` called on app startup (lifespan in `main.py`)
- `Base.metadata.create_all()` runs successfully

#### 0.2 Configuration Service
**File:** `backend/app/services/config.py` (new file)

Replace config usage with a proper Pydantic `BaseSettings` class.

```python
class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./sentinelchain.db"
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    version: str = "1.0.0"
    # ... all fields from config.yaml
```

Acceptance criteria:
- `get_config()` returns a singleton `Settings` instance
- `.env` file overrides `config.yaml` values
- All current `config.tools`, `config.llm`, `config.memory` paths work

#### 0.3 Redis Session Manager
**File:** `backend/app/memory/redis_manager.py` (new file)

Implement `RedisManager` for:
- Short-term workflow state storage (LangGraph checkpointer replacement)
- Semantic caching (`GPTCache`-style key: hash of supplier_id + query + model)
- Pub/sub for SSE streaming

Acceptance criteria:
- Uses `redis.asyncio` client
- `set(key, value, ttl)` / `get(key)` / `delete(key)` work
- Cache key: `sha256(supplier_id + query + model_name) → response`
- TTL: 24 hours for cache entries
- Connection graceful on Redis unavailability (fallback to in-memory `dict`)

#### 0.4 Pinecone Vector Store
**File:** `backend/app/memory/vector_store.py` (new file)

Implement `VectorStore` for:
- Storing supplier profile embeddings
- Semantic search for similar suppliers
- Storing past investigation embeddings

Acceptance criteria:
- Uses `pinecone.Pinecone` client
- `upsert(supplier_id, embedding, metadata)` — metadata includes name, country, industry, tier, risk_history
- `search(query_embedding, top_k=5, filter_dict={})` returns matching supplier IDs + scores
- `delete(supplier_id)` works
- Index name from config (`pinecone.index_name`)

#### 0.5 Embedding Service
**File:** `backend/app/services/embeddings.py` (new file)

Generate embeddings for supplier names, queries, and risk descriptions.

Acceptance criteria:
- Uses `sentence-transformers` (local) or OpenAI `text-embedding-3-small`
- `embed(text: str) -> List[float]` and `embed_batch(texts: List[str]) -> List[List[float]]`
- 1536-dim output (match OpenAI) or 384-dim (match `all-MiniLM-L6-v2`)

---

### Phase 1 — Tool Infrastructure (Used by All Agents)

#### 1.1 Web Search: Tavily
**File:** `backend/app/tools/web_search.py` (new file)

Implement `TavilyTool` for news and web search.

Acceptance criteria:
- `search(query: str, max_results: int = 5) -> List[Dict]`
- Returns: `[{title, url, content, score}]`
- API key from `config.tools.tavily.api_key`
- Error: returns empty list on failure, does not crash the workflow

#### 1.2 Semantic Search: Exa
**File:** `backend/app/tools/semantic_search.py` (new file)

Implement `ExaTool` for finding similar historical supply chain disruptions.

Acceptance criteria:
- `search(query: str, num_results: int = 5) -> List[Dict]`
- Returns: `[{title, url, text, score}]`
- API key from `config.tools.exa.api_key`

#### 1.3 Scraping: Apify
**File:** `backend/app/tools/scraper.py` (new file)

Implement `ApifyTool` for scraping government sanctions lists, news sites, and dark web monitoring sources.

Acceptance criteria:
- `scrape(actor_id: str, run_input: dict) -> List[Dict]` — generic actor invocation
- `get_sanctions_list(source: str) -> List[Dict]` — fetches OFAC/EU/UN sanctions
- API token from `config.tools.apify.api_token`

#### 1.4 Code Execution: E2B
**File:** `backend/app/tools/sandbox.py` (new file)

Implement `E2BSandbox` for safe Python code execution (Monte Carlo, financial calculations).

Acceptance criteria:
- `run_code(code: str, timeout: int = 30) -> Dict` — outputs `{stdout, stderr, files, exit_code}`
- `run_financial_analysis(supplier_data: dict) -> Dict` — pre-built financial script
- API key from `config.tools.e2b.api_key`

#### 1.5 MCP Tool Registry
**File:** `backend/app/tools/mcp_registry.py` (new file)

Implement `MCPToolRegistry` to expose CRM, ERP, and internal databases as MCP tools.

Acceptance criteria:
- `register_tool(name, description, input_schema, handler)` 
- `call_tool(name, arguments) -> Any`
- Tools exposed: `crm_lookup_supplier`, `erp_get_inventory`, `db_query_suppliers`
- MCP server runs on `localhost:{config.tools.mcp.port}`

#### 1.6 Tool Orchestrator
**File:** `backend/app/tools/__init__.py`

Create `ToolRegistry` class that aggregates all tools and delegates calls.

Acceptance criteria:
- `ToolRegistry(tools_config)` initializes all tool instances
- `execute(tool_name, **kwargs)` routes to correct tool
- Returns structured result or raises `ToolExecutionError`

---

### Phase 2 — Memory & Memory Tools (Used by Agents)

#### 2.1 Memory Manager
**File:** `backend/app/memory/__init__.py`

Implement `MemoryManager` combining Redis + Pinecone + SQLite.

Acceptance criteria:
- `initialize()` — connects to Redis, Pinecone, creates DB tables
- `save_supplier_profile(supplier, embedding)`
- `save_workflow_state(state: WorkflowState)`
- `get_workflow_state(workflow_id) -> Optional[WorkflowState]`
- `search_similar_suppliers(query_embedding, top_k)`
- `cache_query(key_hash, response) -> Optional[dict]`
- `close()` — closes all connections gracefully

#### 2.2 PII Masking (Presidio)
**File:** `backend/app/services/pii_masking.py` (new file)

Implement `PIIMasker` using Microsoft Presidio.

Acceptance criteria:
- `mask(text: str) -> str` — scrubs PERSON, LOCATION, EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, IBAN_CODE, IP_ADDRESS
- `anonymize(text: str) -> str` — replaces with `[REDACTED]`
- Applied BEFORE any text is sent to public LLMs (Claude, GPT-4o)
- Applied to Scout-gathered evidence, user queries, HITL payloads

#### 2.3 Guardrails AI Integration
**File:** `backend/app/services/guardrails.py` (new file)

Implement structured output validation + prompt injection detection.

Acceptance criteria:
- `validate_risk_output(raw_llm_output: str) -> RiskTaxonomy` — enforces strict JSON schema for risk data
- `detect_prompt_injection(text: str) -> bool` — returns True if injection detected
- Applied to:
  - All Analyst outputs (risk factors must have source URLs)
  - All Auditor outputs (compliance results in strict format)
  - All user inputs
- `RAIL` or `Validator` config loaded from `config/guardrails.yaml`

---

### Phase 3 — Agent Implementation (Core Intelligence)

_Ai agents implementing this phase must read the existing `backend/app/agents/__init__.py` to understand the current stubs before writing code._

#### 3.1 Scout Agent — Real Data Acquisition
**File:** `backend/app/agents/__init__.py`

Replace the stub `_gather_evidence()` with real tool calls.

Acceptance criteria:
- For `supplier_id` provided:
  1. Call `TavilyTool.search(f"{supplier_name} news risk")` → 5 results
  2. Call `ExaTool.search(f"{supplier_name} financial report")` → 3 results
  3. Call `ApifyTool.get_sanctions_list()` → check if supplier/related entities appear
  4. Call `VectorStore.search(supplier_embedding)` → find related suppliers with risk history
  5. Call `MCPToolRegistry.call_tool("crm_lookup_supplier", supplier_id)` → internal data
- Each result becomes an `Evidence` object: `{id, source, content, url, timestamp, confidence}`
- Returns `List[Evidence]` with at least 3 items (if tools succeed) or 0 (if all fail, with error logged)
- Each evidence entry MUST have a verifiable `source` field (URL or document ID) — this is enforced by Guardrails in the Analyst phase
- PII masks all tool outputs before storing in `context.evidence`

#### 3.2 Analyst Agent — Real Reasoning & Synthesis
**File:** `backend/app/agents/__init__.py`

Replace the stub `_analyze_evidence()` with LLM-powered analysis.

Acceptance criteria:
- Uses LLM (config.llm.primary — Claude 3.5 Sonnet) via LangChain
- Prompt template (see Section 7) instructs Analyst to:
  1. Review all evidence items
  2. Identify risk factors across categories: `FINANCIAL`, `GEOPOLITICAL`, `REGULATORY`, `ESG`, `OPERATIONAL`, `REPUTATIONAL`
  3. Assign `RiskLevel` (LOW/MEDIUM/HIGH/SEVERE/CRITICAL) and confidence score
  4. Each risk factor MUST cite at least one evidence URL/document ID
  5. Flag if evidence is insufficient (loops back to Scout)
  - Output is validated through Guardrails AI (`validate_risk_output`)
  - If validation fails, retry once; if it fails again, return the raw output with an error flag
- Returns `List[RiskFactor]`

#### 3.3 Auditor Agent — Real Compliance Checking
**File:** `backend/app/agents/__init__.py`

Replace the stub `_verify_compliance()` with real compliance checks.

Acceptance criteria:
- Uses LLM (config.llm.secure — Llama 3.1 70B via Bedrock) for PII-sensitive checks
- Checks each risk factor against:
  - OFAC SDN list (via Apify scraper)
  - EU CSDDD requirements (via pre-loaded rules JSON)
  - Export control regulations (via MCP tool: `db_query_export_controls`)
- Sets `rf.metadata["compliance_verified"] = True/False` with finding
- `_check_hitl_required()`: returns `True` if any risk is SEVERE/CRITICAL, or HIGH + REGULATORY
- `_prepare_hitl_payload()`: builds Slack-ready payload with recommendation (FREEZE_PAYMENTS / INVESTIGATE_FURTHER / ESCALATE)

#### 3.4 Mitigator Agent — Real Action Generation
**File:** `backend.app/agents/__init__.py`

Replace stubs `_generate_mitigations()` and `_find_alternatives()`.

Acceptance criteria:
- `_generate_mitigations()`:
  1. For each risk factor, use LLM to generate 1-3 specific mitigation actions
  2. Each action has: title, description, estimated_cost, estimated_time_days, priority
  3. Store as `MitigationAction` objects
- `_find_alternatives()`:
  1. Query Pinecone for suppliers in same industry/country with lower risk scores
  2. Score alternatives: `risk_score` < 40, active status
  3. Calculate cost/lead-time differences using pre-loaded market data (mock or MCP)
  4. Store as `AlternativeSupplier` objects

#### 3.5 Orchestrator Agent — CrewAI Integration
**File:** `backend/app/agents/__init__.py`

Wire the Orchestrator to CrewAI for deep-dive investigations (Workflow 2).

Acceptance criteria:
- For `WorkflowType.DEEP_DIVE_INVESTIGATION`, spin up a CrewAI crew with:
  - Crew: `InvestigationCrew`
  - Agents: Scout, Analyst, Auditor, Mitigator (mapped from existing base classes)
  - Tasks: sequential with conditional delegation
- For `WorkflowType.AUTONOMOUS_DISCOVERY`, use the existing LangGraph state machine (no change needed to graph)
- CrewAI is used ONLY for deep-dive; autonomous discovery uses LangGraph directly

---

### Phase 4 — LangGraph Workflow (State Machine)

#### 4.1 Fix HITL Interrupt
**File:** `backend/app/graph/__init__.py`

The current `return_interrupt()` returns a `Command` but the HITL resume path needs fixing.

Acceptance criteria:
- When `hitl_required=True`, the graph compiles with `interrupt_before=["auditor"]` or uses `interrupt()` correctly
- After HITL response, `resume_after_hitl()` re-invokes the graph with `Command(resume=hitl_response)`
- Workflow state correctly transitions from `WAITING_HITL` → `RUNNING` → `COMPLETED` / `CANCELLED`

#### 4.2 SSE Streaming Integration
**File:** `backend/app/main.py` (update stream endpoint)
**File:** `backend/app/services/streaming.py` (new file)

Wire the SSE endpoint to real workflow state updates.

Acceptance criteria:
- `/api/v1/investigations/{workflow_id}/stream` uses Redis pub/sub
- Each agent step publishes a message to `workflow:{workflow_id}:events`
- SSE endpoint subscribes via `aioredis` and yields `data: {json}` lines
- Frontend receives real-time updates: agent name, message, timestamp, progress %

#### 4.3 Cost Tracking
**File:** `backend/app/services/cost_tracker.py` (new file)

Track LLM token usage and API call costs per investigation.

Acceptance criteria:
- Record: LLM provider, model, input_tokens, output_tokens, cost_usd
- Aggregate per supplier and per month
- Expose via `/api/v1/metrics`

---

### Phase 5 — Backend API Completion

All endpoints in `main.py` must return real data (no more 404s and empty lists).

#### 5.1 Complete Supplier CRUD
**File:** `backend/app/api/suppliers.py` (new file)

- `POST /api/v1/suppliers` — saves to DB, generates embedding, stores in Pinecone
- `GET /api/v1/suppliers` — queries DB with filters (tier, country, risk_level, is_active)
- `GET /api/v1/suppliers/{id}` — returns supplier + last investigation summary
- `PATCH /api/v1/suppliers/{id}` — updates DB and Pinecone embedding
- `DELETE /api/v1/suppliers/{id}` — soft delete

#### 5.2 Complete Investigation CRUD
**File:** `backend/app/api/investigations.py` (new file)

- `POST /api/v1/investigations` — triggers workflow (autonomous or deep-dive), returns investigation ID
- `GET /api/v1/investigations/{id}` — returns current status + partial results
- `POST /api/v1/investigations/{id}/hitl` — records HITL response, resumes workflow
- `GET /api/v1/investigations/{id}/stream` — SSE (Phase 4.2)

#### 5.3 Agent Status Endpoint
**File:** `backend/app/main.py`

- `GET /api/v1/agents/status` — return actual agent states from `OrchestratorAgent.get_capabilities()`

#### 5.4 Seed Data Endpoint (Dev Only)
- `POST /api/v1/seed` — generates 50 dummy suppliers for development
- Dev-only: returns 500 if `environment=production`

---

### Phase 6 — Frontend Data Integration

_All mock data in the frontend must be replaced with real API calls._

#### 6.1 API Client Updates
**File:** `frontend/src/lib/api.ts`

- `getSuppliers(filters)` → `GET /api/v1/suppliers`
- `getSupplier(id)` → `GET /api/v1/suppliers/{id}`
- `createSupplier(data)` → `POST /api/v1/suppliers`
- `startInvestigation(data)` → `POST /api/v1/investigations`
- `getInvestigation(id)` → `GET /api/v1/investigations/{id}`
- `submitHITL(id, response)` → `POST /api/v1/investigations/{id}/hitl`
- `subscribeToWorkflow(id, callback)` — SSE subscription using `EventSource`

#### 6.2 Dashboard Page
**File:** `frontend/src/app/page.tsx`

Replace `mockStats` and `mockRecentAlerts` with real data fetched from:
- `/api/v1/metrics` → stats
- `/api/v1/investigations?limit=5` → recent alerts (risk factors)

Acceptance criteria:
- Stats load on mount with loading skeleton
- Alerts poll every 60s or use SSE
- Clicking "New Investigation" navigates to `/investigations`

#### 6.3 Suppliers Page
**File:** `frontend/src/app/suppliers/page.tsx`

- Table loads from `GET /api/v1/suppliers`
- Filters: tier, country, risk level, search query
- Each row links to supplier detail page
- "Add Supplier" button opens a form modal

#### 6.4 Investigations Page
**File:** `frontend/src/app/investigations/page.tsx`

- "New Investigation" form: supplier selector or free-text query
- After submission, navigates to streaming view
- Streaming view: shows live agent steps from SSE
- HITL panel: renders when `hitl_required=true` with Approve / Deny / Escalate buttons
- Completed investigation shows: risk factors, mitigation actions, alternative suppliers

#### 6.5 Supplier Detail Page
**File:** `frontend/src/app/suppliers/[id]/page.tsx`

- Supplier info + risk history
- Last investigation results (risk factors, actions)
- "Start Investigation" button

---

### Phase 7 — Observability, Eval & Security

#### 7.1 LangSmith Tracing
- Every agent tool call and LLM call wrapped in `@traceable` decorator from `langsmith`
- Project name: `sentinelchain`
- Traces include: workflow_id, supplier_id, agent_role

#### 7.2 W&B Weave Evaluation
**File:** `backend/app/services/evaluation.py` (new file)

- Log Analyst outputs to W&B Weave for evaluation against golden datasets
- Track: false_positive_rate, accuracy, precision, recall per risk category
- Evaluation runs on completed investigations (post-hoc, not blocking)

#### 7.3 LLM Failover
**File:** `backend/app/services/llm_factory.py` (new file)

- Primary: Anthropic Claude 3.5 Sonnet
- Fallback: OpenAI GPT-4o
- Secure: AWS Bedrock Llama 3.1 70B
- If primary rate-limited → automatically switch to fallback
- If both fail → queue in Redis for retry (max 3 retries, exponential backoff)
- Optional PagerDuty alert on repeated failures

#### 7.4 Security Hardening
- CORS: restrict to frontend origin in production (not `"*"`)
- OAuth 2.0 for internal CRM/ERP tool calls (stub for now, add `auth.py`)
- Rate limiting on all API endpoints (`slowapi` or custom)
- API key rotation reminder (comment in `.env.example`)

---

## 4. Prompt Templates (Required for Agent Implementation)

### Analyst Prompt Template
```
You are the Analyst agent in SentinelChain, a supply chain risk analysis system.

Your task: analyze the following evidence about supplier "{supplier_name}" and identify risk factors.

## Evidence
{evidence_list}

## Instructions
1. Review each piece of evidence carefully.
2. Identify risk factors across these categories:
   - FINANCIAL (cash flow, debt, credit rating)
   - GEOPOLITICAL (trade wars, sanctions, port strikes, political instability)
   - REGULATORY (sanctions lists, export controls, new laws)
   - ESG (environmental violations, labor disputes, carbon footprint)
   - OPERATIONAL (factory fires, shipping delays, quality failures)
   - REPUTATIONAL (scandals, negative press, lawsuits)
3. Assign a RiskLevel to each: LOW, MEDIUM, HIGH, SEVERE, or CRITICAL
4. Assign a confidence score (0.0 to 1.0) based on evidence quality
5. For each risk factor, cite at least one evidence URL or document ID as the source
6. If evidence is insufficient to reach a confident assessment, say so explicitly and request more data from Scout.

## Output Format (STRICT JSON — do not deviate)
{{
  "risk_factors": [
    {{
      "id": "rf-<uuid>",
      "category": "<RISK_CATEGORY>",
      "level": "<RISK_LEVEL>",
      "title": "<short title>",
      "description": "<1-2 sentence description>",
      "confidence": <float>,
      "evidence_ids": ["<evidence_id>"],
      "metadata": {{}}
    }}
  ],
  "needs_more_evidence": <bool>,
  "summary": "<1 paragraph summary>"
}}
```

### Mitigator Prompt Template
```
You are the Mitigator agent in SentinelChain. Given the following identified risk factors for supplier "{supplier_name}", generate mitigation actions and suggest alternative suppliers.

## Risk Factors
{risk_factors_json}

## Instructions
1. For each HIGH, SEVERE, and CRITICAL risk factor, generate 1-3 specific mitigation actions.
2. Mitigation actions must include: title, description, estimated_cost_usd, estimated_time_days, priority (HIGH/MEDIUM/LOW)
3. Suggest 3 alternative suppliers (real or plausible industry peers) with:
   - name, country, industry, estimated_risk_score, cost_advantage_pct, lead_time_days

## Output Format (STRICT JSON)
{{
  "mitigation_actions": [...],
  "alternative_suppliers": [...],
  "summary": "<1 paragraph summary>"
}}
```

---

## 5. Acceptance Criteria (Summary)

| Feature | Pass Condition |
|--------|---------------|
| Database | App starts, tables created, supplier CRUD works |
| Redis | Cache hit/miss works, pub/sub delivers SSE messages |
| Pinecone | Embeddings upserted, similarity search returns results |
| Scout Agent | Returns ≥3 Evidence objects with URLs per investigation |
| Analyst Agent | Returns RiskFactor list validated by Guardrails, each with evidence IDs |
| Auditor Agent | Flags SEVERE/CRITICAL risks for HITL, compliance results stored |
| Mitigator Agent | Returns ≥1 action per HIGH+ risk, ≥3 alternative suppliers |
| HITL | Pauses workflow, Slack notification sent, resume works after Approve/Deny |
| SSE Stream | Frontend receives live agent messages within 2s of state change |
| Frontend Dashboard | Loads real stats from API (no mock data) |
| Frontend Investigations | New investigation triggers real workflow, streaming visible |
| Frontend Suppliers | Table loads, filters work, create supplier works |
| LLM Failover | Falls back to GPT-4o if Claude rate-limited |
| PII Masking | No raw PII in agent messages or LLM inputs (verified in logs) |
| Guardrails | Invalid JSON responses are caught and retried |
| LangSmith Traces | Every LLM call appears in LangSmith dashboard |
| W&B Evaluation | Completed investigations logged to W&B |

---

## 6. Implementation Order for an AI Agent

1. **Setup:** Install updated `requirements.txt`, create `.env` from template
2. **Phase 0:** Database → Config → Redis → Pinecone → Embeddings
3. **Phase 1:** Tavily, Exa, Apify, E2B, MCP tools
4. **Phase 2:** MemoryManager, PII Masking, Guardrails
5. **Phase 3:** Scout → Analyst → Auditor → Mitigator (one agent at a time, verify each)
6. **Phase 4:** Fix HITL, SSE streaming, cost tracking
7. **Phase 5:** Complete all API endpoints, add seed endpoint
8. **Phase 6:** Frontend data integration (api.ts → each page)
9. **Phase 7:** Observability, failover, security hardening

---

## 7. Reference Files

| File | Purpose |
|------|---------|
| `backend/app/models/__init__.py` | Pydantic models (read, do not modify unless fixing) |
| `backend/app/schemas/__init__.py` | API schemas (read, reference for JSON shapes) |
| `backend/app/graph/__init__.py` | LangGraph workflow (update node functions) |
| `backend/app/agents/__init__.py` | Agent classes (replace stub methods) |
| `backend/config.yaml` | Runtime configuration |
| `backend/app/main.py` | FastAPI app (complete endpoint implementations) |
| `frontend/src/lib/api.ts` | API client (replace mock calls) |
| `frontend/src/app/page.tsx` | Dashboard (replace mock data) |
| `frontend/src/app/investigations/page.tsx` | Investigations page |
| `frontend/src/app/suppliers/page.tsx` | Suppliers page |

---

## 8. Non-Negotiable Rules

1. **Never send raw PII to public LLMs.** Always run `PIIMasker.mask()` first.
2. **Every risk factor must cite a verifiable source.** Guardrails enforces this; do not bypass.
3. **Maximum 10 steps per workflow** (configurable via `max_steps`). Enforced by `_increment_step()`.
4. **HITL is mandatory for SEVERE and CRITICAL findings.** Do not auto-approve.
5. **Cost per supplier target: <$0.50/month.** Use semantic caching; log all costs.
6. **Failover must be silent to the user.** If Claude fails, the user only sees results — not errors.
7. **Partial results are better than no results.** If a tool fails, log it and continue with available data; mark confidence lower.

---

## 9. Testing Requirements

For each implemented feature:
- Unit test: mock tool/LLM, verify agent output shape
- Integration test: run full workflow end-to-end with mock data
- Frontend test: verify page renders with real API response

Minimum test coverage target: **60%** for new code.

Run tests:
```bash
cd backend
pytest tests/ -v --cov=app
```
