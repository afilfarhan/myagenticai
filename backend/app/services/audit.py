"""
Audit Logging for SentinelChain - Compliance and Security Event Tracking
"""
import json
import structlog
from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, asdict
from uuid import UUID, uuid4

from app.services.database import get_database_service, DatabaseService
from app.memory import get_redis_manager

logger = structlog.get_logger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events"""
    # Authentication
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_LOGIN_FAILED = "user.login_failed"
    TOKEN_REFRESH = "token.refresh"
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"
    
    # Supplier Management
    SUPPLIER_CREATED = "supplier.created"
    SUPPLIER_UPDATED = "supplier.updated"
    SUPPLIER_DELETED = "supplier.deleted"
    SUPPLIER_VIEWED = "supplier.viewed"
    
    # Investigation
    INVESTIGATION_STARTED = "investigation.started"
    INVESTIGATION_COMPLETED = "investigation.completed"
    INVESTIGATION_CANCELLED = "investigation.cancelled"
    INVESTIGATION_VIEWED = "investigation.viewed"
    
    # HITL
    HITL_REQUIRED = "hitl.required"
    HITL_APPROVED = "hitl.approved"
    HITL_DENIED = "hitl.denied"
    HITL_ESCALATED = "hitl.escalated"
    HITL_TIMEOUT = "hitl.timeout"
    
    # Agent Actions
    AGENT_ACTION = "agent.action"
    EVIDENCE_GATHERED = "evidence.gathered"
    RISK_IDENTIFIED = "risk.identified"
    MITIGATION_PROPOSED = "mitigation.proposed"
    
    # Data Access
    DATA_EXPORT = "data.export"
    REPORT_GENERATED = "report.generated"
    
    # Security
    PERMISSION_DENIED = "security.permission_denied"
    RATE_LIMIT_EXCEEDED = "security.rate_limit_exceeded"
    SUSPICIOUS_ACTIVITY = "security.suspicious_activity"


class AuditSeverity(str, Enum):
    """Audit event severity"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event record"""
    event_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: str
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    outcome: Optional[str] = None  # success, failure, partial
    details: Dict[str, Any] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}
        if self.correlation_id is None:
            self.correlation_id = str(uuid4())


class AuditLogger:
    """
    Structured audit logger with multiple backends:
    - Structured logging (structlog)
    - Database (for compliance queries)
    - Redis (for real-time alerting)
    """
    
    def __init__(self, db: DatabaseService = None):
        self.db = db
        self.redis = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize backends"""
        if self._initialized:
            return
        
        self.db = self.db or get_database_service()
        self.redis = await get_redis_manager()
        self._initialized = True
    
    async def log(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity = AuditSeverity.INFO,
        user_id: str = None,
        tenant_id: str = None,
        resource_type: str = None,
        resource_id: str = None,
        action: str = None,
        outcome: str = "success",
        details: Dict[str, Any] = None,
        ip_address: str = None,
        user_agent: str = None,
        correlation_id: str = None
    ) -> AuditEvent:
        """Log an audit event"""
        await self.initialize()
        
        event = AuditEvent(
            event_id=str(uuid4()),
            event_type=event_type,
            severity=severity,
            timestamp=datetime.utcnow().isoformat(),
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            outcome=outcome,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id
        )
        
        # 1. Structured logging
        self._log_structured(event)
        
        # 2. Database persistence (async, non-blocking)
        asyncio.create_task(self._persist_to_db(event))
        
        # 3. Real-time alerting for critical events
        if severity in (AuditSeverity.ERROR, AuditSeverity.CRITICAL):
            await self._alert_realtime(event)
        
        # 4. Update metrics
        await self._update_metrics(event)
        
        return event
    
    def _log_structured(self, event: AuditEvent):
        """Log to structured logger"""
        log_data = asdict(event)
        # Remove sensitive fields from logs if needed
        if event.severity == AuditSeverity.CRITICAL:
            logger.error("AUDIT", **log_data)
        elif event.severity == AuditSeverity.ERROR:
            logger.error("AUDIT", **log_data)
        elif event.severity == AuditSeverity.WARNING:
            logger.warning("AUDIT", **log_data)
        else:
            logger.info("AUDIT", **log_data)
    
    async def _persist_to_db(self, event: AuditEvent):
        """Persist audit event to database"""
        try:
            # This would insert into audit_events table
            # await self.db.add_audit_event(event)
            pass
        except Exception as e:
            logger.error("Failed to persist audit event", error=str(e), event_id=event.event_id)
    
    async def _alert_realtime(self, event: AuditEvent):
        """Send real-time alert for critical events"""
        try:
            if self.redis and self.redis.is_connected():
                alert = {
                    "event_id": event.event_id,
                    "type": event.event_type.value,
                    "severity": event.severity.value,
                    "timestamp": event.timestamp,
                    "user_id": event.user_id,
                    "resource": f"{event.resource_type}:{event.resource_id}" if event.resource_type else None,
                    "details": event.details
                }
                await self.redis.publish("audit:alerts", alert)
        except Exception as e:
            logger.warning("Failed to send real-time alert", error=str(e))
    
    async def _update_metrics(self, event: AuditEvent):
        """Update audit metrics"""
        try:
            if self.redis and self.redis.is_connected():
                await self.redis.increment_metric(
                    "audit_events_total",
                    labels={
                        "type": event.event_type.value,
                        "severity": event.severity.value,
                        "outcome": event.outcome or "unknown"
                    }
                )
        except Exception as e:
            logger.warning("Failed to update audit metrics", error=str(e))
    
    # Convenience methods
    async def log_user_login(self, user_id: str, tenant_id: str, ip: str, success: bool, **kwargs):
        """Log user login attempt"""
        return await self.log(
            event_type=AuditEventType.USER_LOGIN if success else AuditEventType.USER_LOGIN_FAILED,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            user_id=user_id,
            tenant_id=tenant_id,
            action="login",
            outcome="success" if success else "failure",
            ip_address=ip,
            details=kwargs
        )
    
    async def log_supplier_action(
        self,
        event_type: AuditEventType,
        user_id: str,
        tenant_id: str,
        supplier_id: str,
        action: str,
        outcome: str = "success",
        **kwargs
    ):
        """Log supplier management action"""
        return await self.log(
            event_type=event_type,
            severity=AuditSeverity.INFO,
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type="supplier",
            resource_id=supplier_id,
            action=action,
            outcome=outcome,
            details=kwargs
        )
    
    async def log_investigation_action(
        self,
        event_type: AuditEventType,
        user_id: str,
        tenant_id: str,
        investigation_id: str,
        action: str,
        outcome: str = "success",
        **kwargs
    ):
        """Log investigation action"""
        return await self.log(
            event_type=event_type,
            severity=AuditSeverity.INFO,
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type="investigation",
            resource_id=investigation_id,
            action=action,
            outcome=outcome,
            details=kwargs
        )
    
    async def log_hitl_decision(
        self,
        user_id: str,
        tenant_id: str,
        investigation_id: str,
        decision: str,  # APPROVE, DENY, ESCALATE
        **kwargs
    ):
        """Log HITL decision"""
        event_map = {
            "APPROVE": AuditEventType.HITL_APPROVED,
            "DENY": AuditEventType.HITL_DENIED,
            "ESCALATE": AuditEventType.HITL_ESCALATED
        }
        
        return await self.log(
            event_type=event_map.get(decision, AuditEventType.HITL_REQUIRED),
            severity=AuditSeverity.INFO if decision == "APPROVE" else AuditSeverity.WARNING,
            user_id=user_id,
            tenant_id=tenant_id,
            resource_type="investigation",
            resource_id=investigation_id,
            action=f"hitl.{decision.lower()}",
            outcome="success",
            details={"decision": decision, **kwargs}
        )
    
    async def log_agent_action(
        self,
        workflow_id: str,
        agent_role: str,
        action: str,
        details: Dict[str, Any],
        outcome: str = "success"
    ):
        """Log agent action"""
        return await self.log(
            event_type=AuditEventType.AGENT_ACTION,
            severity=AuditSeverity.INFO,
            resource_type="workflow",
            resource_id=workflow_id,
            action=f"{agent_role}.{action}",
            outcome=outcome,
            details=details
        )
    
    async def log_security_event(
        self,
        event_type: AuditEventType,
        severity: AuditSeverity,
        user_id: str = None,
        tenant_id: str = None,
        ip_address: str = None,
        details: Dict[str, Any] = None
    ):
        """Log security event"""
        return await self.log(
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            tenant_id=tenant_id,
            ip_address=ip_address,
            action=event_type.value,
            outcome="failure",
            details=details
        )
    
    # Query methods
    async def query_events(
        self,
        tenant_id: str = None,
        user_id: str = None,
        event_type: AuditEventType = None,
        severity: AuditSeverity = None,
        start_time: datetime = None,
        end_time: datetime = None,
        resource_type: str = None,
        resource_id: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Query audit events with filters"""
        # Would query database with filters
        return []
    
    async def get_user_activity(
        self,
        user_id: str,
        tenant_id: str,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get recent activity for a user"""
        return []
    
    async def get_security_report(
        self,
        tenant_id: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Generate security audit report"""
        return {
            "total_events": 0,
            "by_severity": {},
            "by_type": {},
            "failed_logins": 0,
            "permission_denials": 0,
            "rate_limit_exceeded": 0
        }


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


async def get_audit_logger() -> AuditLogger:
    """Get or create audit logger instance"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
        await _audit_logger.initialize()
    return _audit_logger


# Middleware for automatic audit logging
class AuditMiddleware:
    """FastAPI middleware for automatic request/response auditing"""
    
    def __init__(self, app, excluded_paths: List[str] = None):
        self.app = app
        self.excluded_paths = excluded_paths or ["/health", "/metrics", "/docs", "/openapi.json"]
        self.audit_logger = None
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        path = scope.get("path", "")
        if any(path.startswith(excluded) for excluded in self.excluded_paths):
            await self.app(scope, receive, send)
            return
        
        # Initialize audit logger
        if self.audit_logger is None:
            self.audit_logger = await get_audit_logger()
        
        # Extract request info
        method = scope.get("method", "")
        client = scope.get("client")
        ip_address = client[0] if client else None
        headers = dict(scope.get("headers", []))
        user_agent = headers.get(b"user-agent", b"").decode()
        
        # Get user info from auth (if available)
        user_id = None
        tenant_id = None
        auth_header = headers.get(b"authorization", b"").decode()
        
        # Process request
        start_time = datetime.utcnow()
        response_status = None
        
        async def send_wrapper(message):
            nonlocal response_status
            if message["type"] == "http.response.start":
                response_status = message["status"]
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            response_status = 500
            raise
        finally:
            # Log the request
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            # Determine severity based on status
            if response_status >= 500:
                severity = AuditSeverity.ERROR
            elif response_status >= 400:
                severity = AuditSeverity.WARNING
            else:
                severity = AuditSeverity.INFO
            
            await self.audit_logger.log(
                event_type=AuditEventType.DATA_EXPORT if "export" in path else AuditEventType.DATA_EXPORT,
                severity=severity,
                user_id=user_id,
                tenant_id=tenant_id,
                action=f"{method} {path}",
                outcome="success" if response_status < 400 else "failure",
                ip_address=ip_address,
                user_agent=user_agent,
                details={
                    "method": method,
                    "path": path,
                    "status": response_status,
                    "duration_ms": duration_ms
                }
            )


# Correlation ID context
_correlation_id: Optional[str] = None


def get_correlation_id() -> str:
    """Get or generate correlation ID for request tracing"""
    global _correlation_id
    if _correlation_id is None:
        _correlation_id = str(uuid4())
    return _correlation_id


def set_correlation_id(correlation_id: str):
    """Set correlation ID for current context"""
    global _correlation_id
    _correlation_id = correlation_id


def clear_correlation_id():
    """Clear correlation ID"""
    global _correlation_id
    _correlation_id = None