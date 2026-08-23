"""
CrewAI deep-dive investigation crew for SentinelChain.

Wraps the existing tool registry as CrewAI tools and runs a four-agent crew
(Scout -> Analyst -> Auditor -> Mitigator) mirroring the LangGraph pipeline.
The LangGraph workflow remains the default engine; enable this crew via:

    crewai:
      enabled: true

The crew executes in a dedicated worker thread (CrewAI is synchronous), while
step events are bridged back to the running event loop so the existing SSE
channel (`workflow:{id}:events`) keeps working unchanged.
"""
import asyncio
import json
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

import structlog

from app.config import get_config
from app.memory import get_memory_manager
from app.tools import ToolRegistry

logger = structlog.get_logger(__name__)


def _build_crew_tools(registry: ToolRegistry) -> list:
    """Wrap async SentinelChain tools as synchronous CrewAI tools.

    The crew runs inside a worker thread with no active event loop, so it is
    safe to drive the async tool methods with ``asyncio.run`` there.
    """
    try:
        from crewai.tools import BaseTool
    except ImportError as exc:  # pragma: no cover - guarded by feature flag
        raise RuntimeError("crewai is not installed; enable requires crewai==0.80.0") from exc

    wrapped = []

    def make(name, description, tool):
        class _Wrapped(BaseTool):
            name: str = name
            description: str = description

            def _run(self, query: str) -> str:
                params = {"query": query}
                result = asyncio.run(tool.execute(params))
                if not result.success:
                    return f"TOOL_ERROR: {result.error}"
                return json.dumps(result.data, default=str)

        return _Wrapped()

    schemas = {
        "tavily_search": "Search recent news and web sources about a supplier, "
                        "sanctions, or supply chain disruption.",
        "exa_search": "Semantic search over historical supply chain disruptions "
                      "similar to a described scenario.",
        "apify_scraper": "Scrape government registries and sanctions lists for a supplier name.",
    }
    for key, description in schemas.items():
        tool = registry.get_tool(key)
        if tool:
            wrapped.append(make(key.replace("_search", "").replace("_scraper", ""), description, tool))

    return wrapped


class DeepDiveCrew:
    """Four-role CrewAI crew executing a deep-dive supplier investigation."""

    ROLE_TO_AGENT = {
        "Scout": ("SCOUT", "evidence"),
        "Analyst": ("ANALYST", "risk factors"),
        "Auditor": ("AUDITOR", "compliance"),
        "Mitigator": ("MITIGATOR", "mitigations"),
    }

    def __init__(
        self,
        workflow_id: UUID,
        supplier_name: Optional[str] = None,
        query: str = "",
        supplier_context: Optional[Dict[str, Any]] = None,
    ):
        self.workflow_id = workflow_id
        self.supplier_name = supplier_name or "the target supplier"
        self.query = query
        self.supplier_context = supplier_context or {}
        cfg = get_config()
        self.crewai_cfg = getattr(cfg, "crewai", {}) or {}
        self.llm_cfg = cfg.llm.primary
        self.logger = logger.bind(component="deep_dive_crew", workflow_id=str(workflow_id))

    # ------------------------------------------------------------------ #
    # Event bridging                                                      #
    # ------------------------------------------------------------------ #

    def _make_step_callback(self, loop: asyncio.AbstractEventLoop):
        """Build a crew step callback that republishes to the SSE channel."""

        def on_step(item) -> None:
            message = self._extract_message(item)
            agent = self._extract_agent(message)
            self._events.append(message)
            try:
                asyncio.run_coroutine_threadsafe(self._publish_step(agent, message), loop)
            except Exception as exc:  # never break the crew on telemetry
                self.logger.warning("Failed to queue crew event", error=str(exc))

        return on_step

    @staticmethod
    def _extract_message(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("message") or item.get("task") or item.get("description") or "crew step")
        return str(getattr(item, "description", None) or item)

    def _extract_agent(self, message: str) -> str:
        for role in self.ROLE_TO_AGENT:
            if role.lower() in message.lower():
                return role.upper()
        return "ORCHESTRATOR"

    async def _publish_step(self, agent: str, message: str) -> None:
        try:
            memory_manager = await get_memory_manager()
            await memory_manager.publish_workflow_event(self.workflow_id, {
                "workflow_id": str(self.workflow_id),
                "agent": agent,
                "message": message,
                "status": "RUNNING",
                "step": len(self._events),
                "hitl_required": False,
                "hitl_payload": None,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as exc:
            self.logger.warning("Failed to publish crew event", error=str(exc))

    # ------------------------------------------------------------------ #
    # Execution                                                           #
    # ------------------------------------------------------------------ #

    async def run(self) -> Dict[str, Any]:
        """Run the crew and return a result dict for workflow state_data."""
        self._events: list = []
        loop = asyncio.get_running_loop()
        result = await asyncio.to_thread(self._run_sync, loop)
        self.logger.info("Deep-dive crew finished")
        return result

    def _build_crew(self, tools: list, loop: asyncio.AbstractEventLoop):
        from crewai import Agent, Crew, Process, Task, LLM

        llm = LLM(
            model=f"{self.llm_cfg.provider}/{self.llm_cfg.model}",
            temperature=self.llm_cfg.temperature,
            max_tokens=self.llm_cfg.max_tokens,
        )
        verbose = bool(self.crewai_cfg.get("verbose", False))
        max_iter = int(self.crewai_cfg.get("max_iter", 10))

        common = {"llm": llm, "verbose": verbose, "max_iter": max_iter, "allow_delegation": False}

        scout = Agent(
            role="Supply Chain Intelligence Scout",
            goal="Collect concrete, sourced evidence relevant to the investigation query",
            backstory="Veteran OSINT analyst specialising in supplier risk signals.",
            tools=tools,
            **common,
        )
        analyst = Agent(
            role="Risk Analyst",
            goal="Synthesise collected evidence into specific risk factors with levels",
            backstory="Supply chain risk modeller known for calibrated, evidence-cited judgments.",
            **common,
        )
        auditor = Agent(
            role="Compliance Auditor",
            goal="Check findings against OFAC, CSDDD, export-control and ESG obligations",
            backstory="Former regulator enforcing sanctions and ESG compliance in global supply chains.",
            **common,
        )
        mitigator = Agent(
            role="Mitigation Strategist",
            goal="Propose practical mitigation actions and alternative suppliers",
            backstory="Procurement strategist who has de-risked Fortune 500 supply chains.",
            **common,
        )

        context = (
            f"Supplier: {self.supplier_name}\n"
            f"Investigation brief: {self.query}\n"
            f"Known profile: {json.dumps(self.supplier_context, default=str)}"
        )

        tasks = [
            Task(
                description=(
                    f"{context}\n\nUse the available search and scraping tools to gather "
                    "recent, sourced evidence (news, sanctions lists, financial signals) "
                    "relevant to the brief. Return a numbered list of findings, each with "
                    "source URL and date."
                ),
                expected_output="Numbered evidence list with source URLs and dates.",
                agent=scout,
            ),
            Task(
                description=(
                    "Using the gathered evidence, produce a JSON object of risk factors:\n"
                    '{"risk_factors": [{"category": "GEOPOLITICAL|FINANCIAL|ESG|REGULATORY|'
                    'OPERATIONAL|CYBER|NATURAL_DISASTER|SUPPLIER_VIABILITY", '
                    '"level": "LOW|MEDIUM|HIGH|SEVERE|CRITICAL", "title": str, '
                    '"description": str, "confidence": float}], '
                    '"needs_more_evidence": bool, "summary": str}\n'
                    "JSON only, no commentary."
                ),
                expected_output="A single valid JSON object.",
                agent=analyst,
            ),
            Task(
                description=(
                    "Review the risk assessment for OFAC sanctions exposure, CSDDD due "
                    "diligence gaps, export controls and ESG violations. Append a "
                    '"compliance" object: {"violations": [str], '
                    '"hitl_required": bool, "recommendation": str} to the same JSON.'
                ),
                expected_output="The updated single valid JSON object.",
                agent=auditor,
            ),
            Task(
                description=(
                    "For each HIGH-or-worse risk factor propose one mitigation action "
                    "(title, action_type, estimated_timeline_days). Add \"mitigations\": "
                    "[...] to the JSON. This is the final output."
                ),
                expected_output="The final complete valid JSON object.",
                agent=mitigator,
            ),
        ]

        return Crew(
            agents=[scout, analyst, auditor, mitigator],
            tasks=tasks,
            process=Process.sequential,
            verbose=verbose,
            step_callback=self._make_step_callback(loop),
        )

    def _run_sync(self, loop: asyncio.AbstractEventLoop) -> Dict[str, Any]:
        registry = ToolRegistry()
        tools = _build_crew_tools(registry)
        crew = self._build_crew(tools, loop)

        try:
            raw = str(crew.kickoff())
        finally:
            # Close async tools from this thread-safe context.
            try:
                asyncio.run(registry.close())
            except Exception:
                pass

        parsed = self._parse_output(raw)
        parsed.setdefault("summary", raw[:2000])
        parsed["engine"] = "crewai"
        return parsed

    @staticmethod
    def _parse_output(raw: str) -> Dict[str, Any]:
        """Best-effort extraction of the structured JSON the crew produced."""
        try:
            from json_repair import repair_json

            repaired = repair_json(raw, return_objects=True)
            if isinstance(repaired, dict):
                return repaired
        except Exception:
            pass
        # Fallback: find the outermost JSON object manually.
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        return {}
