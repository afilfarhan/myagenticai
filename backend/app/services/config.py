"""
Configuration service for SentinelChain - Pydantic Settings with YAML + .env support
"""
import os
from pathlib import Path
from typing import Optional, Any, Dict, List
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class LLMConfig(BaseSettings):
    provider: str = Field(default="anthropic")
    model: str = Field(default="claude-3-5-sonnet-20241022")
    api_key: Optional[str] = Field(default=None)
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=8192)


class LLMSettings(BaseSettings):
    primary: LLMConfig = Field(default_factory=lambda: LLMConfig(provider="anthropic", model="claude-3-5-sonnet-20241022"))
    multimodal: LLMConfig = Field(default_factory=lambda: LLMConfig(provider="openai", model="gpt-4o"))
    secure: LLMConfig = Field(default_factory=lambda: LLMConfig(provider="bedrock", model="meta.llama3-1-70b-instruct-v1:0"))


class ToolConfig(BaseSettings):
    tavily: Dict[str, Any] = Field(default_factory=dict)
    exa: Dict[str, Any] = Field(default_factory=dict)
    apify: Dict[str, Any] = Field(default_factory=dict)
    e2b: Dict[str, Any] = Field(default_factory=dict)
    mcp: Dict[str, Any] = Field(default_factory=dict)


class MemoryConfig(BaseSettings):
    pinecone: Dict[str, Any] = Field(default_factory=dict)
    redis: Dict[str, Any] = Field(default_factory=dict)


class SecurityConfig(BaseSettings):
    presidio: Dict[str, Any] = Field(default_factory=dict)
    guardrails: Dict[str, Any] = Field(default_factory=dict)
    prompt_injection: Dict[str, Any] = Field(default_factory=dict)


class ObservabilityConfig(BaseSettings):
    langsmith: Dict[str, Any] = Field(default_factory=dict)
    wandb: Dict[str, Any] = Field(default_factory=dict)
    prometheus: Dict[str, Any] = Field(default_factory=dict)


class CostControlConfig(BaseSettings):
    semantic_cache: Dict[str, Any] = Field(default_factory=dict)
    monthly_budget_usd: float = Field(default=1000.0)
    cost_per_supplier_target: float = Field(default=0.50)


class HITLConfig(BaseSettings):
    slack: Dict[str, Any] = Field(default_factory=dict)
    approval_required_for: List[str] = Field(default_factory=lambda: ["SEVERE", "CRITICAL"])


class AuthConfig(BaseSettings):
    jwt_secret: str = Field(default="change-me-in-production")
    access_token_ttl_min: int = Field(default=15)
    refresh_token_ttl_days: int = Field(default=7)


class DatabaseConfig(BaseSettings):
    url: str = Field(default="sqlite+aiosqlite:///./sentinelchain.db")
    pool_size: int = Field(default=10)
    max_overflow: int = Field(default=20)

    @field_validator("url", mode="before")
    @classmethod
    def _default_unresolved_placeholder(cls, v):
        """Fall back to local SQLite when ${DATABASE_URL} is not set."""
        if isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            return "sqlite+aiosqlite:///./sentinelchain.db"
        return v


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )
    
    # App settings
    name: str = Field(default="SentinelChain")
    version: str = Field(default="1.0.0")
    environment: str = Field(default="development")
    debug: bool = Field(default=True)
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    
    # Sub-configurations
    llm: LLMSettings = Field(default_factory=LLMSettings)
    langgraph: Dict[str, Any] = Field(default_factory=dict)
    crewai: Dict[str, Any] = Field(default_factory=dict)
    tools: ToolConfig = Field(default_factory=ToolConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    cost_control: CostControlConfig = Field(default_factory=CostControlConfig)
    hitl: HITLConfig = Field(default_factory=HITLConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    
    @field_validator("database", mode="before")
    @classmethod
    def parse_database_url(cls, v):
        if isinstance(v, str):
            return {"url": v}
        return v
    
    @classmethod
    def from_yaml(cls, yaml_path: str = "config.yaml") -> "Settings":
        """Load settings from YAML file, then override with .env"""
        # Make ${VAR} placeholders in YAML resolvable from .env / environment.
        load_dotenv()

        config_path = Path(yaml_path)
        if config_path.exists():
            with open(config_path, "r") as f:
                yaml_data = yaml.safe_load(f) or {}

            def _expand(value):
                if isinstance(value, str) and "${" in value:
                    return os.path.expandvars(value)
                if isinstance(value, dict):
                    return {k: _expand(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [_expand(v) for v in value]
                return value

            yaml_data = _expand(yaml_data)

            # Flatten nested dict for SettingsConfigDict.
            # The `app` section maps to top-level Settings fields.
            flat_data = {}
            for key, value in yaml_data.items():
                if isinstance(value, dict):
                    if key == "app":
                        flat_data.update(value)
                        continue
                    for sub_key, sub_value in value.items():
                        flat_data[f"{key}__{sub_key}"] = sub_value
                else:
                    flat_data[key] = value

            # Create instance with YAML data, .env will override via pydantic
            return cls(**flat_data)

        return cls()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings.from_yaml("config.yaml")


def get_config() -> Settings:
    """Alias for get_settings for backward compatibility"""
    return get_settings()


def reset_config() -> None:
    """Clear cached settings (useful for testing)"""
    get_settings.cache_clear()