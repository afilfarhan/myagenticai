"""
Memory Manager for SentinelChain - Coordinates database, vector store, Redis, and embeddings
"""
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import structlog

from app.models import (
    Supplier, Evidence, RiskFactor, WorkflowState, AgentMessage,
    WorkflowType, HITLStatus, RiskLevel, RiskCategory, EvidenceType, SupplierTier
)
from app.services.database import DatabaseService, get_database_service
from app.memory.redis_manager import RedisManager, get_redis_manager
from app.memory.vector_store import VectorStore, get_vector_store
from app.services.embeddings import EmbeddingService, get_embedding_service, MockEmbeddingService

logger = structlog.get_logger(__name__)


class MemoryManager:
    """High-level memory manager coordinating all storage layers"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.db: Optional[DatabaseService] = None
        self.redis: Optional[RedisManager] = None
        self.vector_store: Optional[VectorStore] = None
        self.embeddings: Optional[EmbeddingService] = None
        self._initialized = False
    
    async def initialize(self) -> bool:
        """Initialize all memory components"""
        try:
            # Initialize database
            self.db = get_database_service()
            
            # Initialize Redis
            self.redis = await get_redis_manager()
            
            # Initialize Vector Store
            self.vector_store = await get_vector_store()
            
            # Initialize Embeddings
            # Use mock if no API keys configured
            from app.services.config import get_config
            cfg = get_config()
            embedding_config = cfg.memory.embeddings if hasattr(cfg.memory, 'embeddings') else {}
            
            if isinstance(embedding_config, dict):
                provider = embedding_config.get("provider", "sentence_transformers")
            else:
                provider = getattr(embedding_config, 'provider', 'sentence_transformers')
            
            if provider == "sentence_transformers":
                self.embeddings = EmbeddingService(embedding_config)
            else:
                # Use mock for development
                self.embeddings = MockEmbeddingService(dimension=384)
            
            await self.embeddings.initialize()
            
            self._initialized = True
            logger.info("Memory manager initialized successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to initialize memory manager", error=str(e))
            return False
    
    async def close(self) -> None:
        """Close all connections"""
        if self.embeddings:
            await self.embeddings.close()
        if self.vector_store:
            await self.vector_store.close()
        if self.redis:
            await self.redis.close()
        self._initialized = False
    
    # --- Text preparation helpers ---
    
    def _get_supplier_text(self, supplier: Supplier) -> str:
        """Generate text representation for supplier embedding"""
        parts = [
            supplier.name,
            supplier.legal_name or "",
            supplier.country,
            supplier.region or "",
            supplier.industry or "",
            supplier.tier.value,
        ]
        return " ".join(filter(None, parts))
    
    def _get_evidence_text(self, evidence: Evidence) -> str:
        """Generate text representation for evidence embedding"""
        parts = [
            evidence.title,
            evidence.content,
            evidence.source,
            evidence.type.value,
        ]
        return " ".join(filter(None, parts))
    
    def _get_risk_text(self, risk_factor: RiskFactor) -> str:
        """Generate text representation for risk factor embedding"""
        parts = [
            risk_factor.title,
            risk_factor.description,
            risk_factor.category.value,
            risk_factor.level.value,
        ]
        return " ".join(filter(None, parts))
    
    # --- Supplier Profile Management ---
    
    async def save_supplier_profile(self, supplier: Supplier) -> bool:
        """Save supplier to database and vector store"""
        try:
            # Generate embedding
            text = self._get_supplier_text(supplier)
            embedding = await self.embeddings.embed(text)
            
            # Save to database
            await self.db.create_supplier(
                id=supplier.id,
                name=supplier.name,
                legal_name=supplier.legal_name,
                tier=supplier.tier.value,
                country=supplier.country,
                region=supplier.region,
                industry=supplier.industry,
                website=supplier.website,
                contact_email=supplier.contact_email,
                contact_phone=supplier.contact_phone,
                risk_score=supplier.risk_score,
                last_assessed=supplier.last_assessed,
                is_active=supplier.is_active,
                metadata=supplier.metadata,
                created_at=supplier.created_at,
                updated_at=supplier.updated_at,
            )
            
            # Save to vector store
            metadata = {
                "name": supplier.name,
                "legal_name": supplier.legal_name,
                "tier": supplier.tier.value,
                "country": supplier.country,
                "region": supplier.region,
                "industry": supplier.industry,
                "risk_score": supplier.risk_score,
                "last_assessed": supplier.last_assessed.isoformat() if supplier.last_assessed else None,
                "is_active": supplier.is_active,
            }
            await self.vector_store.upsert_supplier_profile(supplier.id, embedding, metadata)
            
            # Cache in Redis
            await self.redis.cache_session_data(
                f"supplier:{supplier.id}", 
                supplier.model_dump(mode="json"), 
                ttl=3600
            )
            
            logger.info("Supplier profile saved", supplier_id=str(supplier.id))
            return True
            
        except Exception as e:
            logger.error("Failed to save supplier profile", supplier_id=str(supplier.id), error=str(e))
            return False
    
    async def find_similar_suppliers(
        self, 
        query_text: str = None,
        supplier: Supplier = None,
        top_k: int = 10,
        filter_dict: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Find similar suppliers using vector search"""
        try:
            if supplier:
                text = self._get_supplier_text(supplier)
            elif query_text:
                text = query_text
            else:
                return []
            
            embedding = await self.embeddings.embed(text)
            results = await self.vector_store.search_similar_suppliers(
                embedding, top_k=top_k, filter_dict=filter_dict
            )
            
            return results
            
        except Exception as e:
            logger.error("Failed to find similar suppliers", error=str(e))
            return []
    
    async def get_supplier(self, supplier_id: UUID) -> Optional[Supplier]:
        """Get supplier by ID"""
        # Try Redis cache first
        cached = await self.redis.get_session_data(f"supplier:{supplier_id}")
        if cached:
            return Supplier(**cached)
        
        # Fall back to database
        db_supplier = await self.db.get_supplier(supplier_id)
        if db_supplier:
            return Supplier(
                id=db_supplier.id,
                name=db_supplier.name,
                legal_name=db_supplier.legal_name,
                tier=SupplierTier(db_supplier.tier),
                country=db_supplier.country,
                region=db_supplier.region,
                industry=db_supplier.industry,
                website=db_supplier.website,
                contact_email=db_supplier.contact_email,
                contact_phone=db_supplier.contact_phone,
                risk_score=db_supplier.risk_score,
                last_assessed=db_supplier.last_assessed,
                is_active=db_supplier.is_active,
                metadata=db_supplier.metadata,
                created_at=db_supplier.created_at,
                updated_at=db_supplier.updated_at,
            )
        return None
    
    async def list_suppliers(
        self,
        tier: Optional[str] = None,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        is_active: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Supplier], int]:
        """List suppliers with filters"""
        db_suppliers, total = await self.db.list_suppliers(
            tier=tier, country=country, industry=industry,
            is_active=is_active, limit=limit, offset=offset
        )
        
        suppliers = [
            Supplier(
                id=s.id,
                name=s.name,
                legal_name=s.legal_name,
                tier=SupplierTier(s.tier),
                country=s.country,
                region=s.region,
                industry=s.industry,
                website=s.website,
                contact_email=s.contact_email,
                contact_phone=s.contact_phone,
                risk_score=s.risk_score,
                last_assessed=s.last_assessed,
                is_active=s.is_active,
                metadata=s.metadata,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in db_suppliers
        ]
        
        return suppliers, total
    
    async def update_supplier(self, supplier_id: UUID, **kwargs) -> Optional[Supplier]:
        """Update supplier"""
        db_supplier = await self.db.update_supplier(supplier_id, **kwargs)
        if not db_supplier:
            return None
        
        # Invalidate cache
        await self.redis.delete(f"supplier:{supplier_id}")
        
        # Update vector store if risk_score or key fields changed
        if any(k in kwargs for k in ["risk_score", "tier", "country", "industry", "is_active"]):
            supplier = await self.get_supplier(supplier_id)
            if supplier:
                await self.save_supplier_profile(supplier)
        
        return await self.get_supplier(supplier_id)
    
    async def delete_supplier(self, supplier_id: UUID) -> bool:
        """Soft delete supplier"""
        result = await self.db.delete_supplier(supplier_id)
        if result:
            await self.redis.delete(f"supplier:{supplier_id}")
            await self.vector_store.delete_supplier(supplier_id)
        return result
    
    # --- Evidence Management ---
    
    async def store_evidence(self, evidence: Evidence) -> bool:
        """Store evidence in database and vector store"""
        try:
            # Generate embedding
            text = self._get_evidence_text(evidence)
            embedding = await self.embeddings.embed(text)
            
            # Save to database
            await self.db.add_evidence(
                id=evidence.id,
                supplier_id=evidence.supplier_id,
                investigation_id=None,
                type=evidence.type.value,
                source=evidence.source,
                title=evidence.title,
                content=evidence.content,
                url=evidence.url,
                published_at=evidence.published_at,
                retrieved_at=evidence.retrieved_at,
                credibility_score=evidence.credibility_score,
                relevance_score=evidence.relevance_score,
                metadata=evidence.metadata,
            )
            
            # Save to vector store
            metadata = {
                "supplier_id": str(evidence.supplier_id),
                "type": evidence.type.value,
                "source": evidence.source,
                "title": evidence.title,
                "published_at": evidence.published_at.isoformat() if evidence.published_at else None,
                "credibility_score": evidence.credibility_score,
                "relevance_score": evidence.relevance_score,
            }
            await self.vector_store.upsert_evidence(evidence.id, embedding, metadata)
            
            return True
            
        except Exception as e:
            logger.error("Failed to store evidence", evidence_id=str(evidence.id), error=str(e))
            return False
    
    async def search_evidence(
        self, 
        query_text: str, 
        supplier_id: UUID = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for relevant evidence"""
        try:
            embedding = await self.embeddings.embed(query_text)
            results = await self.vector_store.search_evidence(
                embedding, supplier_id=supplier_id, top_k=top_k
            )
            return results
            
        except Exception as e:
            logger.error("Failed to search evidence", error=str(e))
            return []
    
    # --- Risk Assessment History ---
    
    async def store_risk_assessment(self, risk_factor: RiskFactor) -> bool:
        """Store risk assessment for historical tracking"""
        try:
            text = self._get_risk_text(risk_factor)
            embedding = await self.embeddings.embed(text)
            
            # Save to vector store for historical similarity search
            metadata = {
                "supplier_id": str(risk_factor.supplier_id),
                "category": risk_factor.category.value,
                "level": risk_factor.level.value,
                "title": risk_factor.title,
                "confidence": risk_factor.confidence,
                "impact_score": risk_factor.impact_score,
                "likelihood_score": risk_factor.likelihood_score,
                "detected_at": risk_factor.detected_at.isoformat(),
            }
            await self.vector_store.upsert_risk_assessment(risk_factor.id, embedding, metadata)
            
            return True
            
        except Exception as e:
            logger.error("Failed to store risk assessment", risk_factor_id=str(risk_factor.id), error=str(e))
            return False
    
    async def search_historical_risks(
        self, 
        query_text: str, 
        supplier_id: UUID = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Search historical risk assessments"""
        try:
            embedding = await self.embeddings.embed(query_text)
            results = await self.vector_store.search_risk_assessments(
                embedding, supplier_id=supplier_id, top_k=top_k
            )
            return results
            
        except Exception as e:
            logger.error("Failed to search historical risks", error=str(e))
            return []
    
    # --- Workflow State Management ---
    
    async def save_workflow_state(self, state: WorkflowState) -> bool:
        """Save workflow state to Redis and database"""
        try:
            # Save to Redis (fast, for active workflows)
            await self.redis.save_workflow_state(state)
            
            # Save investigation to database (persistent)
            investigation = await self.db.get_investigation(state.workflow_id)
            if not investigation:
                await self.db.create_investigation(
                    workflow_id=state.workflow_id,
                    supplier_id=state.supplier_id,
                    workflow_type=state.workflow_type.value,
                    status=state.status,
                    query=state.state_data.get("query"),
                    investigation_result=state.state_data,
                    hitl_required=state.hitl_required,
                    hitl_status=state.hitl_status.value if state.hitl_status else None,
                    hitl_payload=state.hitl_payload,
                    error=state.error,
                    step_count=state.step_count,
                    max_steps=state.max_steps,
                    created_at=state.created_at,
                    updated_at=state.updated_at,
                    completed_at=state.completed_at,
                )
            else:
                await self.db.update_investigation(
                    state.workflow_id,
                    status=state.status,
                    investigation_result=state.state_data,
                    hitl_required=state.hitl_required,
                    hitl_status=state.hitl_status.value if state.hitl_status else None,
                    hitl_payload=state.hitl_payload,
                    error=state.error,
                    step_count=state.step_count,
                    updated_at=state.updated_at,
                    completed_at=state.completed_at,
                )
            
            return True
            
        except Exception as e:
            logger.error("Failed to save workflow state", workflow_id=str(state.workflow_id), error=str(e))
            return False
    
    async def get_workflow_state(self, workflow_id: UUID) -> Optional[WorkflowState]:
        """Get workflow state from Redis or database"""
        try:
            # Try Redis first (fastest)
            state_data = await self.redis.get_workflow_state(str(workflow_id))
            if state_data:
                return WorkflowState(**state_data)
            
            # Fall back to database
            investigation = await self.db.get_investigation(workflow_id)
            if investigation:
                return WorkflowState(
                    workflow_id=investigation.workflow_id,
                    workflow_type=WorkflowType(investigation.workflow_type),
                    supplier_id=investigation.supplier_id,
                    status=investigation.status,
                    state_data=investigation.investigation_result,
                    hitl_required=investigation.hitl_required,
                    hitl_status=HITLStatus(investigation.hitl_status) if investigation.hitl_status else None,
                    hitl_payload=investigation.hitl_payload,
                    error=investigation.error,
                    step_count=investigation.step_count,
                    max_steps=investigation.max_steps,
                    created_at=investigation.created_at,
                    updated_at=investigation.updated_at,
                    completed_at=investigation.completed_at,
                )
            
            return None
            
        except Exception as e:
            logger.error("Failed to get workflow state", workflow_id=str(workflow_id), error=str(e))
            return None
    
    # --- Agent Communication ---
    
    async def send_agent_message(self, message: AgentMessage) -> bool:
        """Send message to agent via Redis pub/sub"""
        channel = f"agent:{message.to_agent.value}" if message.to_agent else "agent:broadcast"
        return await self.redis.publish(channel, message.model_dump(mode="json"))
    
    async def subscribe_agent(self, agent_role: str) -> "asyncio.Queue":
        """Subscribe to agent channel"""
        import asyncio
        channel = f"agent:{agent_role}"
        return await self.redis.subscribe(channel)
    
    # --- Session Management ---
    
    async def set_session(self, session_id: str, data: Dict[str, Any]) -> bool:
        """Set session data"""
        return await self.redis.cache_session_data(session_id, data)
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        return await self.redis.get_session_data(session_id)
    
    # --- Cost Control - Semantic Caching ---
    
    async def cache_llm_call(self, query: str, response: Dict[str, Any], model: str = "", supplier_id: UUID = None) -> bool:
        """Cache LLM response for semantic caching"""
        cache_key = hashlib.sha256(f"{supplier_id}:{model}:{query}".encode()).hexdigest()[:16]
        return await self.redis.cache_llm_response(cache_key, response)
    
    async def get_cached_llm_call(self, query: str, model: str = "", supplier_id: UUID = None) -> Optional[Dict[str, Any]]:
        """Get cached LLM response"""
        cache_key = hashlib.sha256(f"{supplier_id}:{model}:{query}".encode()).hexdigest()[:16]
        return await self.redis.get_cached_llm_response(cache_key)
    
    # --- Rate Limiting ---
    
    async def check_rate_limit(self, identifier: str, limit: int = 100, window: int = 60) -> Tuple[bool, int]:
        """Check rate limit"""
        return await self.redis.check_rate_limit(identifier, limit, window)
    
    # --- Metrics ---
    
    async def increment_metric(self, name: str, value: float = 1.0, labels: Dict[str, str] = None) -> bool:
        """Increment metric counter"""
        return await self.redis.increment_metric(name, value, labels)
    
    async def get_metric(self, name: str, labels: Dict[str, str] = None) -> float:
        """Get metric value"""
        return await self.redis.get_metric(name, labels)


# Global instance
_memory_manager: Optional[MemoryManager] = None


async def get_memory_manager(config: Dict[str, Any] = None) -> MemoryManager:
    """Get or create memory manager instance"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager(config)
        await _memory_manager.initialize()
    return _memory_manager


async def close_memory_manager() -> None:
    """Close memory manager"""
    global _memory_manager
    if _memory_manager:
        await _memory_manager.close()
        _memory_manager = None