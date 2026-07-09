"""
Embedding Service for SentinelChain - Generate embeddings for suppliers, queries, risk descriptions
"""
import hashlib
from typing import List, Optional, Dict, Any
import structlog
import asyncio

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Service for generating text embeddings"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.provider = self.config.get("provider", "sentence_transformers")
        self.model_name = self.config.get("model", "all-MiniLM-L6-v2")
        self.dimension = self.config.get("dimension", 384)
        
        self._model = None
        self._client = None
        self._initialized = False
        self._use_local = False
    
    async def initialize(self) -> bool:
        """Initialize embedding model"""
        try:
            if self.provider == "sentence_transformers":
                await self._init_sentence_transformers()
            elif self.provider == "openai":
                await self._init_openai()
            elif self.provider == "bedrock":
                await self._init_bedrock()
            else:
                logger.error("Unknown embedding provider", provider=self.provider)
                return False
            
            self._initialized = True
            logger.info("Embedding service initialized", provider=self.provider, model=self.model_name, dimension=self.dimension)
            return True
            
        except Exception as e:
            logger.error("Failed to initialize embedding service", error=str(e))
            return False
    
    async def _init_sentence_transformers(self) -> None:
        """Initialize sentence-transformers model (local)"""
        from sentence_transformers import SentenceTransformer
        
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            None, 
            lambda: SentenceTransformer(self.model_name)
        )
        self.dimension = self._model.get_sentence_embedding_dimension()
        self._use_local = True
    
    async def _init_openai(self) -> None:
        """Initialize OpenAI embeddings"""
        import os
        from openai import AsyncOpenAI
        
        api_key = os.getenv("OPENAI_API_KEY") or self.config.get("api_key")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        
        self._client = AsyncOpenAI(api_key=api_key)
        
        # Set dimension based on model
        if "3-small" in self.model_name:
            self.dimension = 1536
        elif "3-large" in self.model_name:
            self.dimension = 3072
        else:
            self.dimension = 1536
    
    async def _init_bedrock(self) -> None:
        """Initialize AWS Bedrock embeddings (Titan)"""
        import boto3
        
        region = self.config.get("region", "us-east-1")
        self._bedrock_client = boto3.client("bedrock-runtime", region_name=region)
        self.model_name = self.config.get("model", "amazon.titan-embed-text-v1")
        self.dimension = 1536
    
    async def embed(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        embeddings = await self.embed_batch([text])
        return embeddings[0] if embeddings else []
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        if not self._initialized:
            await self.initialize()
        
        if not texts:
            return []
        
        try:
            if self.provider == "sentence_transformers" and self._use_local:
                return await self._embed_local(texts)
            elif self.provider == "openai":
                return await self._embed_openai(texts)
            elif self.provider == "bedrock":
                return await self._embed_bedrock(texts)
            else:
                raise ValueError(f"Unknown provider: {self.provider}")
                
        except Exception as e:
            logger.error("Embedding failed", provider=self.provider, error=str(e))
            # Return zero vectors as fallback
            return [[0.0] * self.dimension for _ in texts]
    
    async def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using local sentence-transformers"""
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._model.encode(texts, convert_to_tensor=False, show_progress_bar=False)
        )
        return embeddings.tolist()
    
    async def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using OpenAI API"""
        response = await self._client.embeddings.create(
            model=self.model_name,
            input=texts,
            encoding_format="float"
        )
        return [item.embedding for item in response.data]
    
    async def _embed_bedrock(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using AWS Bedrock"""
        import json
        
        embeddings = []
        for text in texts:
            body = json.dumps({"inputText": text})
            response = self._bedrock_client.invoke_model(
                modelId=self.model_name,
                body=body
            )
            result = json.loads(response["body"].read())
            embeddings.append(result["embedding"])
        return embeddings
    
    async def close(self) -> None:
        """Cleanup"""
        self._model = None
        self._client = None
        self._initialized = False
    
    def get_dimension(self) -> int:
        """Get embedding dimension"""
        return self.dimension


class MockEmbeddingService(EmbeddingService):
    """Mock embedding service for development/testing without API keys"""
    
    def __init__(self, dimension: int = 384):
        super().__init__({"provider": "mock", "dimension": dimension})
        self.dimension = dimension
        self._initialized = True
    
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate deterministic mock embeddings based on text hash"""
        embeddings = []
        for text in texts:
            # Create deterministic "embedding" from text hash
            hash_obj = hashlib.md5(text.encode())
            hash_bytes = hash_obj.digest()
            
            embedding = []
            for i in range(0, min(len(hash_bytes), self.dimension // 4)):
                # Use 4 bytes per dimension
                val = int.from_bytes(hash_bytes[i*4:(i+1)*4], 'little', signed=False)
                embedding.append((val / 2**32) * 2 - 1)  # Normalize to [-1, 1]
            
            # Pad or truncate to dimension
            while len(embedding) < self.dimension:
                embedding.append(0.0)
            embedding = embedding[:self.dimension]
            
            embeddings.append(embedding)
        
        return embeddings
    
    async def close(self) -> None:
        pass


# Global instance
_embedding_service: Optional[EmbeddingService] = None


async def get_embedding_service(config: Dict[str, Any] = None) -> EmbeddingService:
    """Get or create embedding service instance"""
    global _embedding_service
    if _embedding_service is None:
        # Use mock if no API keys available
        use_mock = False
        if config:
            use_mock = config.get("use_mock", False)
        else:
            import os
            if not os.getenv("OPENAI_API_KEY") and not os.getenv("AWS_ACCESS_KEY_ID"):
                use_mock = True
        
        if use_mock:
            _embedding_service = MockEmbeddingService(dimension=384)
        else:
            _embedding_service = EmbeddingService(config)
        
        await _embedding_service.initialize()
    
    return _embedding_service


async def close_embedding_service() -> None:
    """Close embedding service"""
    global _embedding_service
    if _embedding_service:
        await _embedding_service.close()
        _embedding_service = None