"""
Pinecone Vector Store for SentinelChain - Long-term memory and semantic search
"""
import hashlib
from typing import Optional, List, Dict, Any
from uuid import UUID
import structlog

logger = structlog.get_logger(__name__)


class VectorStore:
    """Pinecone vector store for supplier profiles, evidence, and risk assessments"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.api_key = self.config.get("api_key")
        self.index_name = self.config.get("index_name", "sentinelchain-suppliers")
        self.environment = self.config.get("environment", "us-east-1")
        self.dimension = self.config.get("dimension", 1536)
        self.metric = self.config.get("metric", "cosine")
        
        self._client = None
        self._index = None
        self._connected = False
        self._use_mock = False
    
    async def initialize(self) -> bool:
        """Initialize Pinecone connection"""
        try:
            if not self.api_key:
                logger.warning("No Pinecone API key, using mock vector store")
                self._use_mock = True
                self._connected = True
                return True
            
            from pinecone import Pinecone
            self._client = Pinecone(api_key=self.api_key)
            
            # Check if index exists, create if needed
            if self.index_name not in self._client.list_indexes().names():
                logger.info("Creating Pinecone index", name=self.index_name)
                self._client.create_index(
                    name=self.index_name,
                    dimension=self.dimension,
                    metric=self.metric,
                    spec={"serverless": {"cloud": "aws", "region": self.environment}}
                )
            
            self._index = self._client.Index(self.index_name)
            self._connected = True
            logger.info("Pinecone connected", index=self.index_name)
            return True
            
        except Exception as e:
            logger.warning("Pinecone connection failed, using mock", error=str(e))
            self._use_mock = True
            self._connected = True
            return True
    
    async def close(self) -> None:
        """Close connections"""
        if self._client:
            # Pinecone client doesn't need explicit close
            self._client = None
        self._index = None
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    # --- Mock storage for development ---
    _mock_vectors: Dict[str, Dict[str, Any]] = {}
    
    def _make_id(self, prefix: str, identifier: str) -> str:
        """Create consistent vector ID"""
        return f"{prefix}:{identifier}"
    
    async def upsert_supplier_profile(
        self, 
        supplier_id: UUID, 
        embedding: List[float], 
        metadata: Dict[str, Any]
    ) -> bool:
        """Upsert supplier profile with embedding"""
        try:
            vector_id = self._make_id("supplier", str(supplier_id))
            
            # Add type to metadata
            metadata = {**metadata, "type": "supplier_profile", "supplier_id": str(supplier_id)}
            
            if self._use_mock:
                self._mock_vectors[vector_id] = {
                    "id": vector_id,
                    "vector": embedding,
                    "metadata": metadata
                }
                return True
            
            await self._index.upsert(
                vectors=[{
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata
                }]
            )
            return True
            
        except Exception as e:
            logger.error("Failed to upsert supplier profile", supplier_id=str(supplier_id), error=str(e))
            return False
    
    async def upsert_evidence(
        self, 
        evidence_id: UUID, 
        embedding: List[float], 
        metadata: Dict[str, Any]
    ) -> bool:
        """Upsert evidence with embedding"""
        try:
            vector_id = self._make_id("evidence", str(evidence_id))
            metadata = {**metadata, "type": "evidence", "evidence_id": str(evidence_id)}
            
            if self._use_mock:
                self._mock_vectors[vector_id] = {
                    "id": vector_id,
                    "vector": embedding,
                    "metadata": metadata
                }
                return True
            
            await self._index.upsert(
                vectors=[{
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata
                }]
            )
            return True
            
        except Exception as e:
            logger.error("Failed to upsert evidence", evidence_id=str(evidence_id), error=str(e))
            return False
    
    async def upsert_risk_assessment(
        self, 
        risk_factor_id: UUID, 
        embedding: List[float], 
        metadata: Dict[str, Any]
    ) -> bool:
        """Upsert risk assessment with embedding"""
        try:
            vector_id = self._make_id("risk", str(risk_factor_id))
            metadata = {**metadata, "type": "risk_assessment", "risk_factor_id": str(risk_factor_id)}
            
            if self._use_mock:
                self._mock_vectors[vector_id] = {
                    "id": vector_id,
                    "vector": embedding,
                    "metadata": metadata
                }
                return True
            
            await self._index.upsert(
                vectors=[{
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata
                }]
            )
            return True
            
        except Exception as e:
            logger.error("Failed to upsert risk assessment", risk_factor_id=str(risk_factor_id), error=str(e))
            return False
    
    async def search_similar_suppliers(
        self, 
        query_embedding: List[float], 
        top_k: int = 10,
        filter_dict: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """Search for similar suppliers"""
        try:
            # Build filter
            filter_conditions = {"type": "supplier_profile"}
            if filter_dict:
                filter_conditions.update(filter_dict)
            
            if self._use_mock:
                # Simple mock search - return first few suppliers
                results = []
                for vec_id, vec_data in self._mock_vectors.items():
                    if vec_data["metadata"].get("type") == "supplier_profile":
                        # Check filter
                        match = True
                        for k, v in filter_conditions.items():
                            if vec_data["metadata"].get(k) != v:
                                match = False
                                break
                        if match:
                            results.append({
                                "id": vec_data["metadata"]["supplier_id"],
                                "score": 0.85,  # Mock score
                                "metadata": vec_data["metadata"]
                            })
                return results[:top_k]
            
            results = await self._index.query(
                vector=query_embedding,
                top_k=top_k,
                filter=filter_conditions,
                include_metadata=True
            )
            
            return [
                {
                    "id": match["metadata"]["supplier_id"],
                    "score": match["score"],
                    "metadata": match["metadata"]
                }
                for match in results.matches
            ]
            
        except Exception as e:
            logger.error("Failed to search similar suppliers", error=str(e))
            return []
    
    async def search_evidence(
        self, 
        query_embedding: List[float], 
        supplier_id: UUID = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for relevant evidence"""
        try:
            filter_conditions = {"type": "evidence"}
            if supplier_id:
                filter_conditions["supplier_id"] = str(supplier_id)
            
            if self._use_mock:
                results = []
                for vec_id, vec_data in self._mock_vectors.items():
                    if vec_data["metadata"].get("type") == "evidence":
                        if not supplier_id or vec_data["metadata"].get("supplier_id") == str(supplier_id):
                            results.append({
                                "id": vec_data["metadata"]["evidence_id"],
                                "score": 0.8,
                                "metadata": vec_data["metadata"]
                            })
                return results[:top_k]
            
            results = await self._index.query(
                vector=query_embedding,
                top_k=top_k,
                filter=filter_conditions,
                include_metadata=True
            )
            
            return [
                {
                    "id": match["metadata"]["evidence_id"],
                    "score": match["score"],
                    "metadata": match["metadata"]
                }
                for match in results.matches
            ]
            
        except Exception as e:
            logger.error("Failed to search evidence", error=str(e))
            return []
    
    async def search_risk_assessments(
        self, 
        query_embedding: List[float], 
        supplier_id: UUID = None,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for similar historical risk assessments"""
        try:
            filter_conditions = {"type": "risk_assessment"}
            if supplier_id:
                filter_conditions["supplier_id"] = str(supplier_id)
            
            if self._use_mock:
                results = []
                for vec_id, vec_data in self._mock_vectors.items():
                    if vec_data["metadata"].get("type") == "risk_assessment":
                        if not supplier_id or vec_data["metadata"].get("supplier_id") == str(supplier_id):
                            results.append({
                                "id": vec_data["metadata"]["risk_factor_id"],
                                "score": 0.75,
                                "metadata": vec_data["metadata"]
                            })
                return results[:top_k]
            
            results = await self._index.query(
                vector=query_embedding,
                top_k=top_k,
                filter=filter_conditions,
                include_metadata=True
            )
            
            return [
                {
                    "id": match["metadata"]["risk_factor_id"],
                    "score": match["score"],
                    "metadata": match["metadata"]
                }
                for match in results.matches
            ]
            
        except Exception as e:
            logger.error("Failed to search risk assessments", error=str(e))
            return []
    
    async def delete_supplier(self, supplier_id: UUID) -> bool:
        """Delete all vectors for a supplier"""
        try:
            vector_ids = [
                self._make_id("supplier", str(supplier_id)),
            ]
            
            # Also delete related evidence and risk assessments
            if not self._use_mock:
                # Query for related vectors
                results = await self._index.query(
                    vector=[0.0] * self.dimension,  # dummy vector
                    top_k=10000,
                    filter={"supplier_id": str(supplier_id)},
                    include_metadata=True
                )
                vector_ids.extend([match["id"] for match in results.matches])
                
                await self._index.delete(ids=vector_ids)
            else:
                # Mock cleanup
                keys_to_delete = [k for k in self._mock_vectors.keys() 
                                if self._mock_vectors[k]["metadata"].get("supplier_id") == str(supplier_id)]
                for k in keys_to_delete:
                    del self._mock_vectors[k]
            
            return True
            
        except Exception as e:
            logger.error("Failed to delete supplier vectors", supplier_id=str(supplier_id), error=str(e))
            return False
    
    async def get_index_stats(self) -> Dict[str, Any]:
        """Get index statistics"""
        if self._use_mock:
            supplier_count = sum(1 for v in self._mock_vectors.values() 
                               if v["metadata"].get("type") == "supplier_profile")
            evidence_count = sum(1 for v in self._mock_vectors.values() 
                               if v["metadata"].get("type") == "evidence")
            risk_count = sum(1 for v in self._mock_vectors.values() 
                           if v["metadata"].get("type") == "risk_assessment")
            return {
                "total_vectors": len(self._mock_vectors),
                "supplier_profiles": supplier_count,
                "evidence": evidence_count,
                "risk_assessments": risk_count,
                "mock": True
            }
        
        try:
            stats = await self._index.describe_index_stats()
            return {
                "total_vectors": stats.total_vector_count,
                "dimension": stats.dimension,
                "index_fullness": stats.index_fullness,
                "mock": False
            }
        except Exception as e:
            logger.error("Failed to get index stats", error=str(e))
            return {}


# Global instance
_vector_store: Optional[VectorStore] = None


async def get_vector_store(config: Dict[str, Any] = None) -> VectorStore:
    """Get or create vector store instance"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(config)
        await _vector_store.initialize()
    return _vector_store


async def close_vector_store() -> None:
    """Close vector store"""
    global _vector_store
    if _vector_store:
        await _vector_store.close()
        _vector_store = None