"""
LLM Gateway Service for SentinelChain - LiteLLM-based provider failover
"""
import os
import json
import structlog
from typing import Optional, Dict, Any, List, AsyncGenerator
from dataclasses import dataclass
from enum import Enum
import uuid

import litellm
from litellm import acompletion, aembedding, token_counter
from litellm.exceptions import RateLimitError, APIError, Timeout

from app.config import get_config

logger = structlog.get_logger(__name__)


class ProviderRole(str, Enum):
    PRIMARY = "primary"
    MULTIMODAL = "multimodal"
    SECURE = "secure"


@dataclass
class ProviderConfig:
    role: ProviderRole
    model: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    aws_region: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 8192
    fallback: Optional[str] = None


class LLMGateway:
    """
    LiteLLM-based gateway with provider failover chain:
    Primary (Anthropic) -> Fallback (OpenAI) -> Secure (Bedrock) -> Queue
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.providers: Dict[ProviderRole, ProviderConfig] = {}
        self._initialize_providers()
        
        # LiteLLM settings
        litellm.set_verbose = False
        litellm.drop_params = True
        litellm.modify_params = True
        
        # Cost tracking
        self.cost_callbacks: List[callable] = []
        
    def _initialize_providers(self):
        """Initialize provider configs from YAML/env"""
        cfg = get_config()
        
        # Primary - Anthropic
        self.providers[ProviderRole.PRIMARY] = ProviderConfig(
            role=ProviderRole.PRIMARY,
            model=cfg.llm.primary.model,
            api_key=os.getenv("ANTHROPIC_API_KEY") or cfg.llm.primary.api_key,
            temperature=cfg.llm.primary.temperature,
            max_tokens=cfg.llm.primary.max_tokens,
            fallback="multimodal"
        )
        
        # Multimodal - OpenAI
        self.providers[ProviderRole.MULTIMODAL] = ProviderConfig(
            role=ProviderRole.MULTIMODAL,
            model=cfg.llm.multimodal.model,
            api_key=os.getenv("OPENAI_API_KEY") or cfg.llm.multimodal.api_key,
            temperature=cfg.llm.multimodal.temperature,
            max_tokens=cfg.llm.multimodal.max_tokens,
            fallback="secure"
        )
        
        # Secure - AWS Bedrock
        self.providers[ProviderRole.SECURE] = ProviderConfig(
            role=ProviderRole.SECURE,
            model=cfg.llm.secure.model,
            api_base=f"https://bedrock-runtime.{cfg.llm.secure.region}.amazonaws.com",
            aws_region=cfg.llm.secure.region,
            temperature=cfg.llm.secure.temperature,
            max_tokens=cfg.llm.secure.max_tokens,
            fallback="queue"
        )
        
        logger.info("LLM Gateway initialized", 
                   primary=self.providers[ProviderRole.PRIMARY].model,
                   multimodal=self.providers[ProviderRole.MULTIMODAL].model,
                   secure=self.providers[ProviderRole.SECURE].model)
    
    def register_cost_callback(self, callback: callable):
        """Register callback for cost tracking"""
        self.cost_callbacks.append(callback)
    
    def _compute_cost(self, response, model: str,
                      input_tokens: int, output_tokens: int) -> float:
        """Best-effort USD cost for one completion.

        1. LiteLLM pricing via ``completion_response`` (works across versions).
        2. Static per-million-token price table from config
           (``cost_control.model_prices: {"<model>": {"input": x, "output": y}}``).
        3. Zero when neither is available - tracking must never break calls.
        """
        try:
            return float(litellm.completion_cost(completion_response=response, model=model))
        except Exception:
            pass

        prices = (get_config().cost_control.model_prices or {}) if hasattr(
            get_config().cost_control, "model_prices") else {}
        entry = prices.get(model) or {}
        try:
            return (
                input_tokens / 1_000_000 * float(entry.get("input", 0))
                + output_tokens / 1_000_000 * float(entry.get("output", 0))
            )
        except Exception:
            return 0.0

    async def _track_cost(self, response, model: str, provider_role: ProviderRole,
                          metadata: Optional[Dict[str, Any]] = None):
        """Extract and track token usage/cost from response"""
        try:
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0

            cost = self._compute_cost(response, model, input_tokens, output_tokens)

            for callback in self.cost_callbacks:
                await callback(
                    model=model,
                    provider=provider_role.value,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.warning("Cost tracking failed", error=str(e))
    
    async def complete(
        self,
        messages: List[Dict[str, str]],
        role: ProviderRole = ProviderRole.PRIMARY,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Any:
        """
        Complete with automatic failover chain.
        
        Args:
            messages: Chat messages
            role: Provider role to use
            temperature: Override temperature
            max_tokens: Override max tokens
            stream: Whether to stream
            metadata: Extra metadata for tracing/cost
            **kwargs: Additional LiteLLM params
            
        Returns:
            LiteLLM completion response or async generator if streaming
        """
        current_role = role
        last_error = None
        
        for attempt in range(3):  # Max 3 providers in chain
            provider = self.providers.get(current_role)
            if not provider:
                raise ValueError(f"No provider configured for role: {current_role}")
            
            try:
                response = await acompletion(
                    model=provider.model,
                    messages=messages,
                    temperature=temperature or provider.temperature,
                    max_tokens=max_tokens or provider.max_tokens,
                    stream=stream,
                    api_key=provider.api_key,
                    api_base=provider.api_base,
                    aws_region=provider.aws_region,
                    metadata={
                        "provider_role": current_role.value,
                        "attempt": attempt + 1,
                        **(metadata or {})
                    },
                    **kwargs
                )
                
                if stream:
                    return self._wrap_stream(response, provider.model, current_role, metadata)

                await self._track_cost(response, provider.model, current_role, metadata)
                logger.info("LLM completion success", 
                           model=provider.model, 
                           role=current_role.value,
                           attempt=attempt + 1)
                return response
                
            except RateLimitError as e:
                last_error = e
                logger.warning("Rate limited, trying fallback", 
                              model=provider.model, 
                              role=current_role.value,
                              fallback=provider.fallback)
                
                if provider.fallback and provider.fallback in [r.value for r in ProviderRole]:
                    current_role = ProviderRole(provider.fallback)
                    continue
                elif provider.fallback == "queue":
                    return await self._queue_request(messages, role, temperature, max_tokens, stream, metadata, kwargs)
                raise
                
            except (APIError, Timeout) as e:
                last_error = e
                logger.warning("Provider error, trying fallback",
                              model=provider.model,
                              role=current_role.value,
                              error=str(e),
                              fallback=provider.fallback)
                
                if provider.fallback and provider.fallback in [r.value for r in ProviderRole]:
                    current_role = ProviderRole(provider.fallback)
                    continue
                elif provider.fallback == "queue":
                    return await self._queue_request(messages, role, temperature, max_tokens, stream, metadata, kwargs)
                raise
                
            except Exception as e:
                last_error = e
                logger.error("Unexpected LLM error", 
                            model=provider.model,
                            role=current_role.value,
                            error=str(e))
                raise
        
        # Exhausted all providers
        raise RuntimeError(f"All LLM providers failed. Last error: {last_error}")
    
    def _wrap_stream(self, stream, model: str, role: ProviderRole, metadata: Dict) -> AsyncGenerator:
        """Wrap streaming response with cost tracking"""
        async def tracked_stream():
            full_response = ""
            input_tokens = 0
            output_tokens = 0
            
            async for chunk in stream:
                full_response += chunk.choices[0].delta.content or ""
                yield chunk
                
                # Track tokens from stream if available
                if hasattr(chunk, 'usage') and chunk.usage:
                    input_tokens = chunk.usage.prompt_tokens
                    output_tokens = chunk.usage.completion_tokens
            
            # Final cost tracking
            if input_tokens or output_tokens:
                cost = self._compute_cost(response=None, model=model,
                                          input_tokens=input_tokens, output_tokens=output_tokens)
                for callback in self.cost_callbacks:
                    await callback(
                        model=model,
                        provider=role.value,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost,
                        metadata=metadata or {},
                    )
        
        return tracked_stream()
    
    async def _queue_request(self, messages, role, temperature, max_tokens, stream, metadata, kwargs):
        """Queue request for retry when all providers exhausted"""
        try:
            import redis.asyncio as redis
            redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
            
            queue_item = {
                "id": str(uuid.uuid4()),
                "messages": messages,
                "role": role.value,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": stream,
                "metadata": metadata,
                "kwargs": kwargs,
                "retries": 0,
                "created_at": __import__('datetime').datetime.utcnow().isoformat()
            }
            
            await redis_client.lpush("llm_retry_queue", json.dumps(queue_item))
            await redis_client.close()
            
            logger.info("Request queued for retry", queue_id=queue_item["id"])
            
            # Return a placeholder response
            class QueuedResponse:
                def __init__(self):
                    self.choices = [type('obj', (object,), {'message': type('obj', (object,), {'content': "Request queued for retry. Please check back shortly."})})()]
                    self.usage = None
            
            return QueuedResponse()
            
        except Exception as e:
            logger.error("Failed to queue request", error=str(e))
            raise RuntimeError("All providers exhausted and queue unavailable") from e
    
    async def embed(
        self,
        texts: List[str],
        role: ProviderRole = ProviderRole.PRIMARY,
        **kwargs
    ) -> List[List[float]]:
        """Generate embeddings with failover"""
        provider = self.providers.get(role)
        if not provider:
            raise ValueError(f"No provider for role: {role}")
        
        try:
            response = await aembedding(
                model=provider.model,
                input=texts,
                api_key=provider.api_key,
                api_base=provider.api_base,
                **kwargs
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error("Embedding failed", model=provider.model, error=str(e))
            # Fallback to primary if not already using it
            if role != ProviderRole.PRIMARY:
                return await self.embed(texts, ProviderRole.PRIMARY, **kwargs)
            raise
    
    async def count_tokens(self, messages: List[Dict], model: str = None) -> int:
        """Count tokens for messages"""
        model = model or self.providers[ProviderRole.PRIMARY].model
        return token_counter(model=model, messages=messages)


# Global instance
_llm_gateway: Optional[LLMGateway] = None


def get_llm_gateway(config: Dict[str, Any] = None) -> LLMGateway:
    """Get or create LLM gateway instance"""
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = LLMGateway(config)
    return _llm_gateway


async def close_llm_gateway():
    """Close gateway (for graceful shutdown)"""
    global _llm_gateway
    _llm_gateway = None