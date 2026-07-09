"""
Tool implementations for SentinelChain agents
"""
import asyncio
import json
import structlog
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from uuid import UUID, uuid4

from app.models import Evidence, EvidenceType, Supplier
from app.services.pii_masking import get_pii_masker
from app.config import get_config

# LangSmith tracing
try:
    from langsmith import traceable
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    def traceable(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

logger = structlog.get_logger(__name__)


@dataclass
class ToolResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None


class BaseTool:
    """Base class for all tools"""
    
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.logger = logger.bind(tool=name)
    
    @traceable(run_type="tool", name="base_tool_execute")
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        raise NotImplementedError
    
    def get_schema(self) -> Dict[str, Any]:
        raise NotImplementedError


class TavilySearchTool(BaseTool):
    """Tavily search for news and web content"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("tavily_search", config)
        self.api_key = self.config.get("api_key")
        self.max_results = self.config.get("max_results", 10)
        self.search_depth = self.config.get("search_depth", "advanced")
        self._client = None
    
    async def _get_client(self):
        if self._client is None and self.api_key:
            try:
                from tavily import TavilyClient
                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                self.logger.warning("tavily-python not installed")
        return self._client
    
    @traceable(run_type="tool", name="tavily_search")
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        query = params.get("query", "")
        if not query:
            return ToolResult(success=False, error="Query parameter required")
        
        max_results = params.get("max_results", self.max_results)
        search_depth = params.get("search_depth", self.search_depth)
        
        try:
            client = await self._get_client()
            if not client:
                # Return mock results for development
                return ToolResult(
                    success=True,
                    data=[{
                        "title": f"Mock result for: {query}",
                        "url": "https://example.com/mock",
                        "content": f"This is a mock search result for query: {query}",
                        "score": 0.9,
                        "published_date": datetime.utcnow().isoformat()
                    }],
                    metadata={"query": query, "mock": True}
                )
            
            # Execute search
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                    include_domains=params.get("include_domains"),
                    exclude_domains=params.get("exclude_domains"),
                )
            )
            
            results = response.get("results", [])
            
            # Mask PII in results
            pii_masker = get_pii_masker()
            for result in results:
                if "content" in result:
                    result["content"] = pii_masker.mask(result["content"])
                if "title" in result:
                    result["title"] = pii_masker.mask(result["title"])
            
            return ToolResult(
                success=True,
                data=results,
                metadata={"query": query, "result_count": len(results)}
            )
            
        except Exception as e:
            self.logger.error("Tavily search failed", query=query, error=str(e))
            return ToolResult(success=False, error=str(e))
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": "tavily_search",
            "description": "Search for news, web content, and real-time information",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "default": 10},
                    "search_depth": {"type": "string", "enum": ["basic", "advanced"], "default": "advanced"},
                    "include_domains": {"type": "array", "items": {"type": "string"}},
                    "exclude_domains": {"type": "array", "items": {"type": "string"}}
                },
                "required": ["query"]
            }
        }


class ExaSearchTool(BaseTool):
    """Exa semantic search for historical events and research"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("exa_search", config)
        self.api_key = self.config.get("api_key")
        self.max_results = self.config.get("max_results", 10)
        self._client = None
    
    async def _get_client(self):
        if self._client is None and self.api_key:
            try:
                from exa_py import Exa
                self._client = Exa(api_key=self.api_key)
            except ImportError:
                self.logger.warning("exa-py not installed")
        return self._client
    
    @traceable(run_type="tool", name="exa_search")
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        query = params.get("query", "")
        if not query:
            return ToolResult(success=False, error="Query parameter required")
        
        max_results = params.get("max_results", self.max_results)
        category = params.get("category")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        
        try:
            client = await self._get_client()
            if not client:
                return ToolResult(
                    success=True,
                    data=[{
                        "title": f"Mock historical analysis: {query}",
                        "url": "https://example.com/mock",
                        "text": f"Similar historical events for: {query}",
                        "score": 0.85,
                        "published_date": "2023-06-15"
                    }],
                    metadata={"query": query, "mock": True}
                )
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    num_results=max_results,
                    category=category,
                    start_published_date=start_date,
                    end_published_date=end_date,
                    type="neural"
                )
            )
            
            results = []
            for result in response.results:
                results.append({
                    "title": result.title,
                    "url": result.url,
                    "text": result.text,
                    "score": result.score,
                    "published_date": result.published_date
                })
            
            # Mask PII
            pii_masker = get_pii_masker()
            for result in results:
                if "text" in result:
                    result["text"] = pii_masker.mask(result["text"])
                if "title" in result:
                    result["title"] = pii_masker.mask(result["title"])
            
            return ToolResult(
                success=True,
                data=results,
                metadata={"query": query, "result_count": len(results)}
            )
            
        except Exception as e:
            self.logger.error("Exa search failed", query=query, error=str(e))
            return ToolResult(success=False, error=str(e))
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": "exa_search",
            "description": "Semantic search for finding similar historical supply chain disruptions",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Semantic search query"},
                    "max_results": {"type": "integer", "default": 10},
                    "category": {"type": "string", "enum": ["news", "research", "financial", "government"]},
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"}
                },
                "required": ["query"]
            }
        }


class ApifyScraperTool(BaseTool):
    """Apify scraper for government registries and official sources"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("apify_scraper", config)
        self.api_token = self.config.get("api_token")
        self.timeout = self.config.get("timeout", 300)
        self._client = None
    
    async def _get_client(self):
        if self._client is None and self.api_token:
            try:
                from apify_client import ApifyClient
                self._client = ApifyClient(self.api_token)
            except ImportError:
                self.logger.warning("apify-client not installed")
        return self._client
    
    @traceable(run_type="tool", name="apify_scraper")
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        actor_id = params.get("actor_id", "")
        run_input = params.get("run_input", {})
        
        if not actor_id:
            return ToolResult(success=False, error="Actor ID required")
        
        try:
            client = await self._get_client()
            if not client:
                # Mock sanctions list data
                return ToolResult(
                    success=True,
                    data=[{
                        "entity_name": "Mock Sanctioned Entity",
                        "list_name": "EU Sanctions List",
                        "date_added": datetime.utcnow().isoformat(),
                        "reason": "Money laundering",
                        "source_url": "https://example.com/sanctions/1"
                    }],
                    metadata={"actor_id": actor_id, "mock": True}
                )
            
            loop = asyncio.get_event_loop()
            run = await loop.run_in_executor(
                None,
                lambda: client.actor(actor_id).call(run_input=run_input, timeout_secs=self.timeout)
            )
            
            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                return ToolResult(success=False, error="No dataset returned")
            
            items = []
            async for item in client.dataset(dataset_id).iterate_items():
                items.append(item)
            
            return ToolResult(
                success=True,
                data=items,
                metadata={"actor_id": actor_id, "item_count": len(items)}
            )
            
        except Exception as e:
            self.logger.error("Apify scraper failed", actor_id=actor_id, error=str(e))
            return ToolResult(success=False, error=str(e))
    
    async def get_sanctions_list(self, source: str = "eu") -> ToolResult:
        """Get sanctions list from specific source"""
        actors = {
            "eu": "apify/eu-sanctions-list",
            "ofac": "apify/ofac-sdn-list",
            "un": "apify/un-sanctions-list",
            "uk": "apify/uk-sanctions-list",
        }
        
        actor_id = actors.get(source.lower())
        if not actor_id:
            return ToolResult(success=False, error=f"Unknown sanctions source: {source}")
        
        return await self.execute({"actor_id": actor_id, "run_input": {}})
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": "apify_scraper",
            "description": "Scrape government sanction registries, foreign news sites, and official databases",
            "parameters": {
                "type": "object",
                "properties": {
                    "actor_id": {"type": "string", "description": "Apify actor ID to run"},
                    "run_input": {"type": "object", "description": "Input parameters for the actor"}
                },
                "required": ["actor_id"]
            }
        }


class E2BCodeTool(BaseTool):
    """E2B sandbox for safe code execution"""
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__("e2b_code", config)
        self.api_key = self.config.get("api_key")
        self.timeout = self.config.get("timeout", 120)
        self._sandbox = None
    
    async def _get_sandbox(self):
        if self._sandbox is None and self.api_key:
            try:
                from e2b_code_interpreter import Sandbox
                self._sandbox = await Sandbox.create(api_key=self.api_key, timeout=self.timeout)
            except ImportError:
                self.logger.warning("e2b-code-interpreter not installed")
        return self._sandbox
    
    @traceable(run_type="tool", name="e2b_code")
    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        code = params.get("code", "")
        if not code:
            return ToolResult(success=False, error="Code parameter required")
        
        timeout = params.get("timeout", self.timeout)
        packages = params.get("packages", [])
        
        try:
            sandbox = await self._get_sandbox()
            if not sandbox:
                # Mock execution
                return ToolResult(
                    success=True,
                    data={
                        "stdout": "Mock execution complete",
                        "stderr": "",
                        "exit_code": 0,
                        "execution_time_ms": 100,
                        "files": {}
                    },
                    metadata={"mock": True}
                )
            
            # Install packages if needed
            if packages:
                for pkg in packages:
                    await sandbox.commands.run(f"pip install {pkg}")
            
            # Execute code
            execution = await sandbox.run_code(code, timeout=timeout)
            
            return ToolResult(
                success=True,
                data={
                    "stdout": execution.logs.stdout,
                    "stderr": execution.logs.stderr,
                    "exit_code": execution.exit_code,
                    "execution_time_ms": execution.execution_time,
                    "files": {f.name: f.content for f in execution.files} if execution.files else {}
                },
                metadata={"code_length": len(code)}
            )
            
        except Exception as e:
            self.logger.error("E2B code execution failed", error=str(e))
            return ToolResult(success=False, error=str(e))
    
    async def run_financial_analysis(self, supplier_data: Dict[str, Any]) -> ToolResult:
        """Run pre-built financial analysis script"""
        code = f"""
import pandas as pd
import numpy as np
from scipy import stats

# Supplier financial data
data = {json.dumps(supplier_data)}

# Calculate key ratios
if 'revenue' in data and 'total_assets' in data:
    asset_turnover = data['revenue'] / data['total_assets'] if data['total_assets'] > 0 else 0
else:
    asset_turnover = 0

if 'current_assets' in data and 'current_liabilities' in data:
    current_ratio = data['current_assets'] / data['current_liabilities'] if data['current_liabilities'] > 0 else 0
else:
    current_ratio = 0

if 'net_income' in data and 'total_equity' in data:
    roe = data['net_income'] / data['total_equity'] if data['total_equity'] > 0 else 0
else:
    roe = 0

# Monte Carlo simulation for cash flow projection
np.random.seed(42)
n_simulations = 10000
if 'operating_cash_flow' in data and 'cash_flow_volatility' in data:
    simulations = np.random.normal(
        data['operating_cash_flow'], 
        data['cash_flow_volatility'], 
        n_simulations
    )
    prob_negative = (simulations < 0).mean()
    mean_cf = simulations.mean()
    std_cf = simulations.std()
else:
    prob_negative = 0.5
    mean_cf = 0
    std_cf = 0

results = {{
    "asset_turnover": asset_turnover,
    "current_ratio": current_ratio,
    "roe": roe,
    "cash_flow_projection": {{
        "mean": float(mean_cf),
        "std": float(std_cf),
        "prob_negative": float(prob_negative),
        "percentile_5": float(np.percentile(simulations, 5)) if 'simulations' in locals() else 0,
        "percentile_95": float(np.percentile(simulations, 95)) if 'simulations' in locals() else 0,
    }}
}}

print(json.dumps(results))
"""
        return await self.execute({"code": code, "packages": ["pandas", "numpy", "scipy"]})
    
    def get_schema(self) -> Dict[str, Any]:
        return {
            "name": "e2b_code",
            "description": "Execute Python code safely in sandbox for simulations and analysis",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                    "timeout": {"type": "integer", "default": 120},
                    "packages": {"type": "array", "items": {"type": "string"}, "description": "Additional pip packages to install"}
                },
                "required": ["code"]
            }
        }


class MCPToolManager:
    """Manager for MCP (Model Context Protocol) servers"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.servers: Dict[str, Any] = {}
        self.logger = logger.bind(component="mcp_manager")
    
    async def connect_server(self, name: str, command: str, args: List[str], env: Dict[str, str] = None) -> bool:
        """Connect to an MCP server"""
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env or {}
            )
            
            # Test connection
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
            
            self.servers[name] = {
                "params": server_params,
                "tools": [t.name for t in tools.tools],
                "connected": True
            }
            self.logger.info("MCP server connected", name=name, tools=len(tools.tools))
            return True
            
        except Exception as e:
            self.logger.error("Failed to connect MCP server", name=name, error=str(e))
            return False
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Call a tool on an MCP server"""
        if server_name not in self.servers:
            return ToolResult(success=False, error=f"MCP server {server_name} not connected")
        
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client
            
            server_info = self.servers[server_name]
            async with stdio_client(server_info["params"]) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    
                    return ToolResult(
                        success=True,
                        data=result.content[0].text if result.content else None,
                        metadata={"server": server_name, "tool": tool_name}
                    )
                    
        except Exception as e:
            self.logger.error("MCP tool call failed", server=server_name, tool=tool_name, error=str(e))
            return ToolResult(success=False, error=str(e))
    
    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """List available tools on an MCP server"""
        if server_name not in self.servers:
            return []
        
        try:
            from mcp import ClientSession
            from mcp.client.stdio import stdio_client
            
            server_info = self.servers[server_name]
            async with stdio_client(server_info["params"]) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    
                    return [
                        {
                            "name": t.name,
                            "description": t.description,
                            "input_schema": t.inputSchema
                        }
                        for t in tools.tools
                    ]
        except Exception as e:
            self.logger.error("Failed to list MCP tools", server=server_name, error=str(e))
            return []


class ToolRegistry:
    """Registry of all available tools for agents"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config().tools
        self.tools: Dict[str, BaseTool] = {}
        self.mcp_manager = MCPToolManager(config.get("mcp") if config else None)
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Initialize all configured tools"""
        self.tools["tavily_search"] = TavilySearchTool(self.config.get("tavily", {}))
        self.tools["exa_search"] = ExaSearchTool(self.config.get("exa", {}))
        self.tools["apify_scraper"] = ApifyScraperTool(self.config.get("apify", {}))
        self.tools["e2b_code"] = E2BCodeTool(self.config.get("e2b", {}))
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        return self.tools.get(name)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        return [tool.get_schema() for tool in self.tools.values()]
    
    @traceable(run_type="tool", name="tool_registry_execute")
    async def execute_tool(self, name: str, params: Dict[str, Any]) -> ToolResult:
        tool = self.get_tool(name)
        if not tool:
            return ToolResult(success=False, error=f"Tool {name} not found")
        return await tool.execute(params)
    
    async def close(self):
        """Close all tools"""
        for tool in self.tools.values():
            if hasattr(tool, 'close'):
                await tool.close()


# Global registry
_tool_registry: Optional[ToolRegistry] = None


def get_tool_registry(config: Dict[str, Any] = None) -> ToolRegistry:
    """Get or create tool registry"""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry(config)
    return _tool_registry


async def close_tool_registry():
    """Close tool registry"""
    global _tool_registry
    if _tool_registry:
        await _tool_registry.close()
        _tool_registry = None