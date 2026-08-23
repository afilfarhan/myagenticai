"""
Redis Manager for SentinelChain - Session state, caching, pub/sub, rate limiting
"""
import json
import asyncio
from typing import Optional, Any, Dict, List, Tuple
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)


class RedisManager:
    """Async Redis manager with fallback to in-memory storage"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.url = self.config.get("url", "redis://localhost:6379")
        self.max_connections = self.config.get("max_connections", 50)
        self.socket_timeout = self.config.get("socket_timeout", 5)
        self.socket_connect_timeout = self.config.get("socket_connect_timeout", 5)
        
        self._client: Optional["redis.asyncio.Redis"] = None
        self._pubsub: Optional["redis.asyncio.client.PubSub"] = None
        self._fallback_store: Dict[str, Any] = {}
        self._fallback_pubsub: Dict[str, List[asyncio.Queue]] = {}
        self._use_fallback = False
        self._connected = False
    
    async def initialize(self) -> bool:
        """Initialize Redis connection"""
        try:
            import redis.asyncio as redis
            self._client = redis.from_url(
                self.url,
                max_connections=self.max_connections,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                decode_responses=True,
            )
            # Test connection
            await self._client.ping()
            self._connected = True
            self._use_fallback = False
            logger.info("Redis connected successfully", url=self.url)
            return True
        except Exception as e:
            logger.warning("Redis connection failed, using in-memory fallback", error=str(e))
            self._use_fallback = True
            self._connected = False
            return False
    
    async def close(self) -> None:
        """Close Redis connections"""
        if self._client:
            await self._client.close()
            self._client = None
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    # --- Key-Value Operations ---
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set key with optional TTL"""
        try:
            if self._use_fallback:
                self._fallback_store[key] = {
                    "value": value,
                    "expires_at": datetime.utcnow() + timedelta(seconds=ttl) if ttl else None
                }
                return True
            
            serialized = json.dumps(value, default=str)
            if ttl:
                await self._client.setex(key, ttl, serialized)
            else:
                await self._client.set(key, serialized)
            return True
        except Exception as e:
            logger.error("Redis set failed", key=key, error=str(e))
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get key value"""
        try:
            if self._use_fallback:
                entry = self._fallback_store.get(key)
                if entry:
                    if entry["expires_at"] and entry["expires_at"] < datetime.utcnow():
                        del self._fallback_store[key]
                        return None
                    return entry["value"]
                return None
            
            value = await self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error("Redis get failed", key=key, error=str(e))
            return None
    
    async def delete(self, key: str) -> bool:
        """Delete key"""
        try:
            if self._use_fallback:
                self._fallback_store.pop(key, None)
                return True
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.error("Redis delete failed", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        try:
            if self._use_fallback:
                entry = self._fallback_store.get(key)
                if entry:
                    if entry["expires_at"] and entry["expires_at"] < datetime.utcnow():
                        del self._fallback_store[key]
                        return False
                    return True
                return False
            return await self._client.exists(key) > 0
        except Exception as e:
            logger.error("Redis exists failed", key=key, error=str(e))
            return False
    
    # --- Workflow State Management ---
    
    async def save_workflow_state(self, state: "WorkflowState", ttl: int = 3600) -> bool:
        """Save workflow state with TTL"""
        from app.models import WorkflowState
        key = f"workflow:{state.workflow_id}"
        data = state.model_dump(mode="json")
        return await self.set(key, data, ttl)
    
    async def get_workflow_state(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow state"""
        key = f"workflow:{workflow_id}"
        return await self.get(key)
    
    async def delete_workflow_state(self, workflow_id: str) -> bool:
        """Delete workflow state"""
        key = f"workflow:{workflow_id}"
        return await self.delete(key)
    
    # --- Pub/Sub for SSE Streaming ---
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> bool:
        """Publish message to channel"""
        try:
            serialized = json.dumps(message, default=str)
            if self._use_fallback:
                if channel not in self._fallback_pubsub:
                    self._fallback_pubsub[channel] = []
                for queue in self._fallback_pubsub[channel]:
                    try:
                        queue.put_nowait(message)
                    except asyncio.QueueFull:
                        pass
                return True
            
            await self._client.publish(channel, serialized)
            return True
        except Exception as e:
            logger.error("Redis publish failed", channel=channel, error=str(e))
            return False
    
    async def subscribe(self, channel: str) -> "asyncio.Queue":
        """Subscribe to channel, returns async queue"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        
        if self._use_fallback:
            if channel not in self._fallback_pubsub:
                self._fallback_pubsub[channel] = []
            self._fallback_pubsub[channel].append(queue)
            return queue
        
        if not self._pubsub:
            self._pubsub = self._client.pubsub()
        
        await self._pubsub.subscribe(channel)
        
        # Start background task to forward messages
        async def forward_messages():
            try:
                async for message in self._pubsub.listen():
                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await queue.put(data)
                        except (json.JSONDecodeError, asyncio.QueueFull):
                            pass
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("Pubsub forward error", channel=channel, error=str(e))
        
        asyncio.create_task(forward_messages())
        return queue
    
    async def unsubscribe(self, channel: str, queue: "asyncio.Queue") -> None:
        """Unsubscribe queue from channel"""
        if self._use_fallback:
            if channel in self._fallback_pubsub:
                try:
                    self._fallback_pubsub[channel].remove(queue)
                except ValueError:
                    pass
            return
        
        if self._pubsub:
            await self._pubsub.unsubscribe(channel)
    
    # --- Session Cache ---
    
    async def cache_session_data(self, session_id: str, data: Dict[str, Any], ttl: int = 1800) -> bool:
        """Cache session data"""
        key = f"session:{session_id}"
        return await self.set(key, data, ttl)
    
    async def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get cached session data"""
        key = f"session:{session_id}"
        return await self.get(key)
    
    # --- Rate Limiting ---
    
    async def check_rate_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """Check and increment rate limit counter"""
        try:
            redis_key = f"ratelimit:{key}"
            if self._use_fallback:
                # Simple in-memory rate limiting (not accurate for distributed)
                current = self._fallback_store.get(redis_key, 0)
                current += 1
                self._fallback_store[redis_key] = current
                return current <= limit, current
            
            current = await self._client.incr(redis_key)
            if current == 1:
                await self._client.expire(redis_key, window)
            return current <= limit, current
        except Exception as e:
            logger.error("Rate limit check failed", error=str(e))
            return True, 0
    
    # --- Semantic Cache for LLM Cost Control ---
    
    async def cache_llm_response(self, query_hash: str, response: Dict[str, Any], ttl: int = 86400) -> bool:
        """Cache LLM response for semantic caching"""
        key = f"llm_cache:{query_hash}"
        return await self.set(key, response, ttl)
    
    async def get_cached_llm_response(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached LLM response"""
        key = f"llm_cache:{query_hash}"
        return await self.get(key)
    
    # --- Agent Communication ---
    
    async def send_agent_message(self, to_agent: str, message: "AgentMessage") -> bool:
        """Send message to agent channel"""
        channel = f"agent:{to_agent}"
        return await self.publish(channel, message.model_dump(mode="json"))
    
    async def listen_agent_channel(self, agent: str) -> "asyncio.Queue":
        """Listen to agent channel"""
        channel = f"agent:{agent}"
        return await self.subscribe(channel)


# Global instance
_redis_manager: Optional[RedisManager] = None


async def get_redis_manager() -> RedisManager:
    """Get or create Redis manager"""
    global _redis_manager
    if _redis_manager is None:
        from app.config import get_config
        config = get_config()
        _redis_manager = RedisManager(config.memory.redis)
        await _redis_manager.initialize()
    return _redis_manager


async def close_redis_manager() -> None:
    """Close Redis manager"""
    global _redis_manager
    if _redis_manager:
        await _redis_manager.close()
        _redis_manager = None