"""
Configuration module for SentinelChain
"""
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class LLMConfig(BaseSettings):
    provider: str = Field(default="anthropic")
    model: str = Field(default="claude-3-5-sonnet-20241022")
    api_key: Optional[str] = Field(default=None)
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=8192)


class LLMSettings(BaseSettings):
    primary: LLMConfig = Field(default_factory=LLMConfig)
    multimodal: LLMConfig = Field(default_factory=lambda: LLMConfig(provider="openai", model="gpt-4o"))
    secure: LLMConfig = Field(default_factory=lambda: LLMConfig(provider="bedrock", model="meta.llama3-1-70b-instruct-v1:0"))


class ToolConfig(BaseSettings):
    tavily: dict = Field(default_factory=dict)
    exa: dict = Field(default_factory=dict)
    apify: dict = Field(default_factory=dict)
    e2b: dict = Field(default_factory=dict)


class MemoryConfig(BaseSettings):
    pinecone: dict = Field(default_factory=dict)
    redis: dict = Field(default_factory=dict)


class SecurityConfig(BaseSettings):
    presidio: dict = Field(default_factory=dict)
    guardrails: dict = Field(default_factory=dict)
    prompt_injection: dict = Field(default_factory=dict)


class ObservabilityConfig(BaseSettings):
    langsmith: dict = Field(default_factory=dict)
    wandb: dict = Field(default_factory=dict)
    prometheus: dict = Field(default_factory=dict)


class CostControlConfig(BaseSettings):
    semantic_cache: dict = Field(default_factory=dict)
    monthly_budget_usd: float = Field(default=1000.0)
    cost_per_supplier_target: float = Field(default=0.50)


class HITLConfig(BaseSettings):
    slack: dict = Field(default_factory=dict)
    approval_required_for: list[str] = Field(default_factory=lambda: ["SEVERE", "CRITICAL"])


class DatabaseConfig(BaseSettings):
    url: str = Field(default="sqlite+aiosqlite:///./sentinelchain.db")
    pool_size: int = Field(default=10)
    max_overflow: int = Field(default=20)


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    
    name: str = Field(default="SentinelChain")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langgraph: dict = Field(default_factory=dict)
    crewai: dict = Field(default_factory=dict)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    cost_control: CostControlConfig = Field(default_factory=CostControlConfig)
    hitl: HITLConfig = Field(default_factory=HITLConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    global _config
    if _config is None:
        _config = AppConfig()
    return _config


def reset_config():
    global _config
    _config = None