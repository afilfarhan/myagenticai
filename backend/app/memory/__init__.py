"""
Memory layer for SentinelChain - Pinecone (long-term) and Redis (short-term)
"""
import json
import asyncio
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from dataclasses import dataclass
import structlog

from app.models import Supplier, Evidence, RiskFactor, WorkflowState, AgentMessage
from app.config import get_config

logger = structlog.get_logger(__name__)


@dataclass
class VectorDocument:
    id: str
    vector: List[float]
    metadata: Dict[str, Any]
    text: str


class BaseMemoryStore(ABC):
    """Abstract base class for memory stores"""
    
    @abstractmethod
    async def initialize(self) -> bool:
        pass
    
    @abstractmethod
    async def close(self) -> None:
        pass


class PineconeMemoryStore(BaseMemoryStore):
    """Long-term memory using Pinecone vector database"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config().memory.pinecone
        self.index_name = self.config.get("index_name", "sentinelchain-suppliers")
        self.dimension = self.config.get("dimension", 1536)
        self.metric = self.config.get("metric", "cosine")
        self._client = None
        self._index = None
        self.logger = logger.bind(store="pinecone")
    
    async def initialize(self) -> bool:
        try:
            # In production: from pinecone import Pinecone
            # self._client = Pinecone(api_key=self.config.get("api_key"))
            # self._index = self._client.Index(self.index_name)
            self.logger.info("Pinecone memory store initialized", index=self.index_name)
            return True
        except Exception as e:
            self.logger.error("Failed to initialize Pinecone", error=str(e))
            return False
    
    async def close(self) -> None:
        if self._client:
            # await self._client.close()
            pass
    
    async def upsert_supplier_profile(self, supplier: Supplier, embedding: List[float]) -> bool:
        """Store or update supplier profile with embedding"""
        try:
            vector_doc = VectorDocument(
                id=str(supplier.id),
                vector=embedding,
                metadata={
                    "name": supplier.name,
                    "legal_name": supplier.legal_name,
                    "tier": supplier.tier.value,
                    "country": supplier.country,
                    "region": supplier.region,
                    "industry": supplier.industry,
                    "risk_score": supplier.risk_score,
                    "last_assessed": supplier.last_assessed.isoformat() if supplier.last_assessed else None,
                    "is_active": supplier.is_active,
                    "type": "supplier_profile"
                },
                text=f"{supplier.name} {supplier.legal_name or ''} {supplier.country} {supplier.industry or ''}"
            )
            
            # In production: await self._index.upsert(vectors=[vector_doc.__dict__])
            self.logger.info("Upserted supplier profile", supplier_id=supplier.id)
            return True
        except Exception as e:
            self.logger.error("Failed to upsert supplier profile", error=str(e))
            return False
    
    async def query_similar_suppliers(
        self, 
        embedding: List[float], 
        top_k: int = 10,
        filter_dict: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Find similar suppliers based on embedding"""
        try:
            # In production: results = await self._index.query(vector=embedding, top_k=top_k, filter=filter_dict, include_metadata=True)
            mock_results = [
                {
                    "id": str(uuid4()),
                    "score": 0.92,
                    "metadata": {"name": "Similar Supplier", "country": "Germany", "risk_score": 25.0}
                }
            ]
            return mock_results[:top_k]
        except Exception as e:
            self.logger.error("Failed to query similar suppliers", error=str(e))
            return []
    
    async def store_evidence(self, evidence: Evidence, embedding: List[float]) -> bool:
        """Store evidence with embedding for retrieval"""
        try:
            vector_doc = VectorDocument(
                id=str(evidence.id),
                vector=embedding,
                metadata={
                    "supplier_id": str(evidence.supplier_id),
                    "type": evidence.type.value,
                    "source": evidence.source,
                    "title": evidence.title,
                    "published_at": evidence.published_at.isoformat() if evidence.published_at else None,
                    "credibility_score": evidence.credibility_score,
                    "relevance_score": evidence.relevance_score,
                    "type": "evidence"
                },
                text=f"{evidence.title} {evidence.content}"
            )
            
            # In production: await self._index.upsert(vectors=[vector_doc.__dict__])
            return True
        except Exception as e:
            self.logger.error("Failed to store evidence", error=str(e))
            return False
    
    async def search_evidence(
        self, 
        query_embedding: List[float], 
        supplier_id: UUID = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for relevant evidence"""
        filter_dict = {"type": "evidence"}
        if supplier_id:
            filter_dict["supplier_id"] = str(supplier_id)
        
        try:
            # In production: results = await self._index.query(vector=query_embedding, top_k=top_k, filter=filter_dict, include_metadata=True)
            mock_results = [
                {
                    "id": str(uuid4()),
                    "score": 0.88,
                    "metadata": {
                        "title": "Relevant evidence",
                        "supplier_id": str(supplier_id) if supplier_id else str(uuid4()),
                        "type": "NEWS_ARTICLE"
                    }
                }
            ]
            return mock_results[:top_k]
        except Exception as e:
            self.logger.error("Failed to search evidence", error=str(e))
            return []
    
    async def store_risk_assessment(self, risk_factor: RiskFactor, embedding: List[float]) -> bool:
        """Store risk assessment for historical tracking"""
        try:
            vector_doc = VectorDocument(
                id=str(risk_factor.id),
                vector=embedding,
                metadata={
                    "supplier_id": str(risk_factor.supplier_id),
                    "category": risk_factor.category.value,
                    "level": risk_factor.level.value,
                    "title": risk_factor.title,
                    "confidence": risk_factor.confidence,
                    "impact_score": risk_factor.impact_score,
                    "likelihood_score": risk_factor.likelihood_score,
                    "detected_at": risk_factor.detected_at.isoformat(),
                    "type": "risk_assessment"
                },
                text=f"{risk_factor.title} {risk_factor.description} {risk_factor.category.value}"
            )
            
            # In production: await self._index.upsert(vectors=[vector_doc.__dict__])
            return True
        except Exception as e:
            self.logger.error("Failed to store risk assessment", error=str(e))
            return False


class RedisMemoryStore(BaseMemoryStore):
    """Short-term memory using Redis for session state"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or get_config().memory.redis
        self.url = self.config.get("url", "redis://localhost:6379")
        self.max_connections = self.config.get("max_connections", 50)
        self.socket_timeout = self.config.get("socket_timeout", 5)
        self._client = None
        self.logger = logger.bind(store="redis")
    
    async def initialize(self) -> bool:
        try:
            # In production: import redis.asyncio as redis
            # self._client = redis.from_url(self.url, max_connections=self.max_connections, 
            #                               socket_timeout=self.socket_timeout)
            self.logger.info("Redis memory store initialized", url=self.url)
            return True
        except Exception as e:
            self.logger.error("Failed to initialize Redis", error=str(e))
            return False
    
    async def close(self) -> None:
        if self._client:
            # await self._client.close()
            pass
    
    # Workflow State Management
    async def save_workflow_state(self, state: WorkflowState, ttl: int = 3600) -> bool:
        """Save workflow state with TTL"""
        try:
            key = f"workflow:{state.workflow_id}"
            data = state.model_dump_json()
            # In production: await self._client.setex(key, ttl, data)
            self.logger.debug("Saved workflow state", workflow_id=state.workflow_id)
            return True
        except Exception as e:
            self.logger.error("Failed to save workflow state", error=str(e))
            return False
    
    async def get_workflow_state(self, workflow_id: UUID) -> Optional[WorkflowState]:
        """Retrieve workflow state"""
        try:
            key = f"workflow:{workflow_id}"
            # In production: data = await self._client.get(key)
            data = None  # mock
            if data:
                return WorkflowState.model_validate_json(data)
            return None
        except Exception as e:
            self.logger.error("Failed to get workflow state", error=str(e))
            return None
    
    async def delete_workflow_state(self, workflow_id: UUID) -> bool:
        """Delete workflow state"""
        try:
            key = f"workflow:{workflow_id}"
            # In production: await self._client.delete(key)
            return True
        except Exception as e:
            self.logger.error("Failed to delete workflow state", error=str(e))
            return False
    
    # Agent Communication
    async def publish_message(self, channel: str, message: AgentMessage) -> bool:
        """Publish message to agent channel"""
        try:
            # In production: await self._client.publish(channel, message.model_dump_json())
            return True
        except Exception as e:
            self.logger.error("Failed to publish message", error=str(e))
            return False
    
    async def subscribe_channel(self, channel: str) -> Any:
        """Subscribe to agent channel"""
        # In production: return self._client.pubsub().subscribe(channel)
        return None
    
    # Session Cache
    async def cache_session_data(self, session_id: str, data: Dict[str, Any], ttl: int = 1800) -> bool:
        """Cache session data"""
        try:
            key = f"session:{session_id}"
            # In production: await self._client.setex(key, ttl, json.dumps(data))
            return True
        except Exception as e:
            self.logger.error("Failed to cache session data", error=str(e))
            return False
    
    async def get_session_data(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get cached session data"""
        try:
            key = f"session:{session_id}"
            # In production: data = await self._client.get(key)
            data = None  # mock
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            self.logger.error("Failed to get session data", error=str(e))
            return None
    
    # Rate Limiting
    async def check_rate_limit(self, key: str, limit: int, window: int) -> Tuple[bool, int]:
        """Check and increment rate limit counter"""
        try:
            redis_key = f"ratelimit:{key}"
            # In production: current = await self._client.incr(redis_key)
            # if current == 1: await self._client.expire(redis_key, window)
            current = 1  # mock
            return current <= limit, current
        except Exception as e:
            self.logger.error("Rate limit check failed", error=str(e))
            return True, 0
    
    # Semantic Cache for Cost Control
    async def cache_llm_response(self, query_hash: str, response: Dict[str, Any], ttl: int = 86400) -> bool:
        """Cache LLM response for semantic caching"""
        try:
            key = f"llm_cache:{query_hash}"
            # In production: await self._client.setex(key, ttl, json.dumps(response))
            return True
        except Exception as e:
            self.logger.error("Failed to cache LLM response", error=str(e))
            return False
    
    async def get_cached_llm_response(self, query_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached LLM response"""
        try:
            key = f"llm_cache:{query_hash}"
            # In production: data = await self._client.get(key)
            data = None  # mock
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            self.logger.error("Failed to get cached LLM response", error=str(e))
            return None


class MemoryManager:
    """High-level memory manager coordinating both stores"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.pinecone = PineconeMemoryStore(self.config.get("pinecone"))
        self.redis = RedisMemoryStore(self.config.get("redis"))
        self.logger = logger.bind(component="memory_manager")
    
    async def initialize(self) -> bool:
        pinecone_ok = await self.pinecone.initialize()
        redis_ok = await self.redis.initialize()
        return pinecone_ok and redis_ok
    
    async def close(self) -> None:
        await self.pinecone.close()
        await self.redis.close()
    
    # Supplier Profile Management
    async def save_supplier_profile(self, supplier: Supplier, embedding: List[float]) -> bool:
        return await self.pinecone.upsert_supplier_profile(supplier, embedding)
    
    async def find_similar_suppliers(self, embedding: List[float], **kwargs) -> List[Dict[str, Any]]:
        return await self.pinecone.query_similar_suppliers(embedding, **kwargs)
    
    # Evidence Management
    async def store_evidence(self, evidence: Evidence, embedding: List[float]) -> bool:
        return await self.pinecone.store_evidence(evidence, embedding)
    
    async def search_evidence(self, query_embedding: List[float], **kwargs) -> List[Dict[str, Any]]:
        return await self.pinecone.search_evidence(query_embedding, **kwargs)
    
    # Risk Assessment History
    async def store_risk_assessment(self, risk_factor: RiskFactor, embedding: List[float]) -> bool:
        return await self.pinecone.store_risk_assessment(risk_factor, embedding)
    
    # Workflow State
    async def save_workflow_state(self, state: WorkflowState) -> bool:
        return await self.redis.save_workflow_state(state)
    
    async def get_workflow_state(self, workflow_id: UUID) -> Optional[WorkflowState]:
        return await self.redis.get_workflow_state(workflow_id)
    
    # Agent Communication
    async def send_agent_message(self, to_agent: str, message: AgentMessage) -> bool:
        channel = f"agent:{to_agent}"
        return await self.redis.publish_message(channel, message)
    
    # Session Management
    async def set_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        return await self.redis.cache_session_data(session_id, data)
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.redis.get_session_data(session_id)
    
    # Cost Control - Semantic Caching
    async def cache_llm_call(self, query: str, response: Dict[str, Any]) -> bool:
        import hashlib
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return await self.redis.cache_llm_response(query_hash, response)
    
    async def get_cached_llm_call(self, query: str) -> Optional[Dict[str, Any]]:
        import hashlib
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]
        return await self.redis.get_cached_llm_response(query_hash)
    
    # Rate Limiting
    async def check_rate_limit(self, identifier: str, limit: int = 100, window: int = 60) -> Tuple[bool, int]:
        return await self.redis.check_rate_limit(identifier, limit, window)