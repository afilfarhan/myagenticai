"""
Authentication module for SentinelChain API
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import UUID
import structlog

from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext

from app.services.config import get_config
from app.services.database import get_database_service, DatabaseService
from app.memory import get_redis_manager

logger = structlog.get_logger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# JWT Settings
config = get_config()
SECRET_KEY = config.auth.jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = config.auth.access_token_ttl_min
REFRESH_TOKEN_EXPIRE_DAYS = config.auth.refresh_token_ttl_days

# Security scheme
security = HTTPBearer(auto_error=False)


class TokenData:
    """Decoded token data"""
    def __init__(
        self, 
        user_id: str, 
        tenant_id: str, 
        tier: str, 
        scopes: List[str],
        token_type: str = "access"
    ):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.tier = tier
        self.scopes = scopes
        self.token_type = token_type


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(
    data: Dict[str, Any], 
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    data: Dict[str, Any], 
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """Extract token from Authorization header"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def get_current_user(
    token: str = Depends(get_current_token)
) -> TokenData:
    """Validate token and return user data"""
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    tier = payload.get("tier", "free")
    scopes = payload.get("scopes", [])
    
    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return TokenData(user_id, tenant_id, tier, scopes)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[TokenData]:
    """Get current user if authenticated, otherwise None"""
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials.credentials)
    except HTTPException:
        return None


# Rate Limiting
class RateLimiter:
    """Redis-based rate limiter with tier-based limits"""
    
    def __init__(self):
        self.redis = None
        self.limits = {
            "free": {"requests": 100, "window": 3600},      # 100/hr
            "pro": {"requests": 1000, "window": 3600},      # 1000/hr
            "enterprise": {"requests": 10000, "window": 3600}  # 10000/hr
        }
    
    async def initialize(self):
        self.redis = await get_redis_manager()
    
    async def check_rate_limit(
        self, 
        identifier: str, 
        tier: str = "free"
    ) -> tuple[bool, int, int]:
        """
        Check rate limit for identifier.
        Returns: (allowed, current_count, remaining)
        """
        if not self.redis:
            await self.initialize()
        
        limit_config = self.limits.get(tier, self.limits["free"])
        limit = limit_config["requests"]
        window = limit_config["window"]
        
        key = f"ratelimit:{tier}:{identifier}"
        
        try:
            current = await self.redis.check_rate_limit(key, limit, window)
            # check_rate_limit returns (allowed, count)
            allowed = current[0]
            count = current[1]
            remaining = max(0, limit - count)
            return allowed, count, remaining
        except Exception as e:
            logger.warning("Rate limit check failed", error=str(e))
            return True, 0, limit  # Allow on error
    
    async def get_rate_limit_info(
        self, 
        identifier: str, 
        tier: str = "free"
    ) -> Dict[str, Any]:
        """Get current rate limit status"""
        limit_config = self.limits.get(tier, self.limits["free"])
        allowed, count, remaining = await self.check_rate_limit(identifier, tier)
        
        return {
            "limit": limit_config["requests"],
            "window_seconds": limit_config["window"],
            "current": count,
            "remaining": remaining,
            "allowed": allowed,
            "reset_in": limit_config["window"]  # Approximate
        }


# Global rate limiter
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> RateLimiter:
    """Get or create rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
        await _rate_limiter.initialize()
    return _rate_limiter


# Dependency for rate limiting
async def rate_limit_dependency(
    request: Request,
    current_user: TokenData = Depends(get_current_user)
):
    """Rate limit check dependency"""
    rate_limiter = await get_rate_limiter()
    
    # Use user ID as identifier
    identifier = f"user:{current_user.user_id}"
    tier = current_user.tier
    
    allowed, count, remaining = await rate_limiter.check_rate_limit(identifier, tier)
    
    if not allowed:
        info = await rate_limiter.get_rate_limit_info(identifier, tier)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset_in"]),
                "Retry-After": str(info["reset_in"])
            }
        )
    
    # Add rate limit headers to response (via request state)
    request.state.rate_limit = {
        "limit": count + remaining,
        "remaining": remaining,
        "reset": remaining  # Simplified
    }


# Permission/Authorization
class Permission:
    """Permission constants"""
    # Supplier permissions
    SUPPLIER_READ = "supplier:read"
    SUPPLIER_WRITE = "supplier:write"
    SUPPLIER_DELETE = "supplier:delete"
    
    # Investigation permissions
    INVESTIGATION_READ = "investigation:read"
    INVESTIGATION_WRITE = "investigation:write"
    INVESTIGATION_HITL = "investigation:hitl"
    
    # Admin permissions
    ADMIN_USERS = "admin:users"
    ADMIN_TENANTS = "admin:tenants"
    ADMIN_CONFIG = "admin:config"
    ADMIN_AUDIT = "admin:audit"
    
    # API permissions
    API_ACCESS = "api:access"


TIER_PERMISSIONS = {
    "free": [
        Permission.SUPPLIER_READ,
        Permission.INVESTIGATION_READ,
        Permission.API_ACCESS
    ],
    "pro": [
        Permission.SUPPLIER_READ,
        Permission.SUPPLIER_WRITE,
        Permission.INVESTIGATION_READ,
        Permission.INVESTIGATION_WRITE,
        Permission.INVESTIGATION_HITL,
        Permission.API_ACCESS
    ],
    "enterprise": [
        Permission.SUPPLIER_READ,
        Permission.SUPPLIER_WRITE,
        Permission.SUPPLIER_DELETE,
        Permission.INVESTIGATION_READ,
        Permission.INVESTIGATION_WRITE,
        Permission.INVESTIGATION_HITL,
        Permission.ADMIN_USERS,
        Permission.ADMIN_TENANTS,
        Permission.ADMIN_CONFIG,
        Permission.ADMIN_AUDIT,
        Permission.API_ACCESS
    ]
}


def require_permission(permission: str):
    """Dependency to require a specific permission"""
    async def permission_checker(current_user: TokenData = Depends(get_current_user)):
        user_permissions = TIER_PERMISSIONS.get(current_user.tier, [])
        if permission not in user_permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}"
            )
        return current_user
    return permission_checker


def require_any_permission(*permissions: str):
    """Dependency to require any of the given permissions"""
    async def permission_checker(current_user: TokenData = Depends(get_current_user)):
        user_permissions = TIER_PERMISSIONS.get(current_user.tier, [])
        if not any(p in user_permissions for p in permissions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of permissions required: {', '.join(permissions)}"
            )
        return current_user
    return permission_checker


def require_tier(*tiers: str):
    """Dependency to require specific tier(s)"""
    async def tier_checker(current_user: TokenData = Depends(get_current_user)):
        if current_user.tier not in tiers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required tier: {', '.join(tiers)}"
            )
        return current_user
    return tier_checker


def require_scopes(*scopes: str):
    """Dependency to require specific scopes"""
    async def scope_checker(current_user: TokenData = Depends(get_current_user)):
        user_scopes = set(current_user.scopes)
        required_scopes = set(scopes)
        if not required_scopes.issubset(user_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required scopes: {', '.join(scopes)}"
            )
        return current_user
    return scope_checker


# Token refresh
async def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Refresh access token using refresh token"""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None
    
    # Create new access token
    new_token_data = {
        "sub": payload.get("sub"),
        "tenant_id": payload.get("tenant_id"),
        "tier": payload.get("tier", "free"),
        "scopes": payload.get("scopes", [])
    }
    
    return create_access_token(new_token_data)


# API Key authentication (for service-to-service)
class APIKeyAuth:
    """API Key authentication for service accounts"""
    
    def __init__(self):
        self.valid_keys: Dict[str, Dict[str, Any]] = {}
    
    async def validate_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Validate API key and return key info"""
        if not api_key:
            return None
        
        # Hash the key for storage comparison
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # In production, lookup from database
        # For now, check in-memory
        return self.valid_keys.get(key_hash)
    
    def generate_key(self, tenant_id: str, scopes: List[str] = None) -> tuple[str, str]:
        """Generate new API key. Returns (key, key_id)"""
        key_id = secrets.token_urlsafe(16)
        key_secret = secrets.token_urlsafe(32)
        api_key = f"sk_{key_id}_{key_secret}"
        
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        self.valid_keys[key_hash] = {
            "key_id": key_id,
            "tenant_id": tenant_id,
            "scopes": scopes or [Permission.API_ACCESS],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None
        }
        
        return api_key, key_id


# Global API key auth
_api_key_auth: Optional[APIKeyAuth] = None


def get_api_key_auth() -> APIKeyAuth:
    global _api_key_auth
    if _api_key_auth is None:
        _api_key_auth = APIKeyAuth()
    return _api_key_auth


async def get_api_key_user(
    api_key: str = Depends(lambda r: r.headers.get("X-API-Key"))
) -> Optional[TokenData]:
    """Authenticate via API key"""
    if not api_key:
        return None
    
    auth = get_api_key_auth()
    key_info = await auth.validate_key(api_key)
    
    if not key_info:
        return None
    
    # Update last used
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    if key_hash in auth.valid_keys:
        auth.valid_keys[key_hash]["last_used"] = datetime.utcnow().isoformat()
    
    return TokenData(
        user_id=f"service:{key_info['key_id']}",
        tenant_id=key_info["tenant_id"],
        tier="enterprise",  # Service accounts get enterprise tier
        scopes=key_info["scopes"]
    )


# Combined auth dependency (Bearer token OR API key)
async def get_authenticated_user(
    token_user: Optional[TokenData] = Depends(get_current_user_optional),
    api_key_user: Optional[TokenData] = Depends(get_api_key_user)
) -> TokenData:
    """Get authenticated user from either bearer token or API key"""
    if token_user:
        return token_user
    if api_key_user:
        return api_key_user
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"}
    )