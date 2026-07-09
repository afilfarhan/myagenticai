"""
Guardrails AI Integration for SentinelChain - Structured output validation and prompt injection detection
"""
import json
import re
from typing import Optional, Dict, Any, List
import structlog

logger = structlog.get_logger(__name__)


class GuardrailsValidator:
    """Guardrails AI validator for structured output and prompt injection detection"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.validation_strict = self.config.get("validation_strict", True)
        self._guard = None
        self._initialized = False
        
        # Prompt injection patterns
        self.injection_patterns = [
            r"ignore\s+(previous|all|above)\s+instructions",
            r"disregard\s+(previous|all|above)\s+instructions",
            r"forget\s+(previous|all|above)\s+instructions",
            r"you\s+are\s+now\s+(a|an)\s+\w+",
            r"act\s+as\s+(a|an)\s+\w+",
            r"pretend\s+to\s+be",
            r"simulate\s+(a|an)\s+\w+",
            r"roleplay\s+as",
            r"system\s*:\s*",
            r"assistant\s*:\s*",
            r"user\s*:\s*",
            r"```\s*system",
            r"```\s*user",
            r"###\s*system",
            r"###\s*user",
            r"<\|system\|>",
            r"<\|user\|>",
            r"<\|assistant\|>",
            r"\[INST\]",
            r"\[/INST\]",
            r"<<SYS>>",
            r"<</SYS>>",
            r"##\s*system\s*prompt",
            r"##\s*user\s*prompt",
            r"override\s+safety",
            r"bypass\s+(security|safety|filter)",
            r"jailbreak",
            r"DAN\s+mode",
            r"do\s+anything\s+now",
        ]
        self.injection_regex = re.compile("|".join(self.injection_patterns), re.IGNORECASE)
        
        # Risk factor JSON schema for validation
        self.risk_factor_schema = {
            "type": "object",
            "properties": {
                "risk_factors": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "pattern": "^rf-[0-9a-f-]+$"},
                            "category": {
                                "type": "string",
                                "enum": [
                                    "GEOPOLITICAL", "FINANCIAL", "ESG", "REGULATORY",
                                    "OPERATIONAL", "CYBER", "NATURAL_DISASTER", "SUPPLIER_VIABILITY"
                                ]
                            },
                            "level": {
                                "type": "string",
                                "enum": ["LOW", "MEDIUM", "HIGH", "SEVERE", "CRITICAL"]
                            },
                            "title": {"type": "string", "minLength": 1, "maxLength": 255},
                            "description": {"type": "string", "minLength": 1},
                            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                            "evidence_ids": {"type": "array", "items": {"type": "string"}},
                            "metadata": {"type": "object"}
                        },
                        "required": ["id", "category", "level", "title", "description", "confidence", "evidence_ids"]
                    }
                },
                "needs_more_evidence": {"type": "boolean"},
                "summary": {"type": "string"}
            },
            "required": ["risk_factors", "needs_more_evidence", "summary"]
        }
        
        # Mitigation action schema
        self.mitigation_schema = {
            "type": "object",
            "properties": {
                "mitigation_actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "pattern": "^ma-[0-9a-f-]+$"},
                            "risk_factor_id": {"type": "string"},
                            "title": {"type": "string", "minLength": 1, "maxLength": 255},
                            "description": {"type": "string"},
                            "action_type": {"type": "string"},
                            "estimated_cost_usd": {"type": ["number", "null"]},
                            "estimated_timeline_days": {"type": ["integer", "null"]},
                            "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                            "status": {"type": "string", "default": "PROPOSED"}
                        },
                        "required": ["id", "risk_factor_id", "title", "description", "action_type", "priority"]
                    }
                },
                "alternative_suppliers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "pattern": "^as-[0-9a-f-]+$"},
                            "original_supplier_id": {"type": "string"},
                            "name": {"type": "string"},
                            "country": {"type": "string"},
                            "risk_score": {"type": "number", "minimum": 0, "maximum": 100},
                            "cost_difference_pct": {"type": ["number", "null"]},
                            "lead_time_days": {"type": ["integer", "null"]},
                            "quality_rating": {"type": ["number", "null"]},
                            "certifications": {"type": "array", "items": {"type": "string"}}
                        },
                        "required": ["id", "original_supplier_id", "name", "country", "risk_score"]
                    }
                },
                "summary": {"type": "string"}
            },
            "required": ["mitigation_actions", "alternative_suppliers", "summary"]
        }
    
    async def initialize(self) -> bool:
        """Initialize Guardrails"""
        if not self.enabled:
            logger.info("Guardrails disabled")
            return True
        
        try:
            import guardrails as gd
            self._guard = gd
            self._initialized = True
            logger.info("Guardrails initialized")
            return True
        except ImportError:
            logger.warning("Guardrails AI not installed, using fallback validation")
            self._initialized = True
            return True
        except Exception as e:
            logger.error("Guardrails initialization failed", error=str(e))
            return False
    
    # --- Prompt Injection Detection ---
    
    def detect_prompt_injection(self, text: str) -> bool:
        """Detect potential prompt injection attempts"""
        if not text:
            return False
        
        # Check for injection patterns
        if self.injection_regex.search(text):
            logger.warning("Prompt injection detected", text_sample=text[:200])
            return True
        
        # Check for excessive special tokens
        special_token_count = len(re.findall(r'[<>|{}[\]]', text))
        if special_token_count > 20:
            logger.warning("Excessive special tokens", count=special_token_count)
            return True
        
        # Check for repeated words (possible manipulation)
        words = text.lower().split()
        if len(words) > 100:
            word_freq = {}
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1
            max_freq = max(word_freq.values())
            if max_freq > len(words) * 0.3:
                logger.warning("Repeated word pattern detected", max_freq=max_freq)
                return True
        
        return False
    
    # --- Structured Output Validation ---
    
    def validate_risk_output(self, raw_output: str) -> Dict[str, Any]:
        """Validate and parse Analyst agent risk factor output"""
        if not self.enabled or not self._initialized:
            return self._parse_json_fallback(raw_output)
        
        try:
            parsed = json.loads(raw_output)
            
            if self._validate_schema(parsed, self.risk_factor_schema):
                return parsed
            
            if self.validation_strict:
                raise ValueError("Output does not match risk factor schema")
            
            return self._extract_valid_risk_factors(parsed)
            
        except json.JSONDecodeError:
            extracted = self._extract_json(raw_output)
            if extracted:
                return self.validate_risk_output(extracted)
            
            if self.validation_strict:
                raise
            return self._create_fallback_risk_output(raw_output)
    
    def validate_mitigation_output(self, raw_output: str) -> Dict[str, Any]:
        """Validate and parse Mitigator agent output"""
        if not self.enabled or not self._initialized:
            return self._parse_json_fallback(raw_output)
        
        try:
            parsed = json.loads(raw_output)
            
            if self._validate_schema(parsed, self.mitigation_schema):
                return parsed
            
            if self.validation_strict:
                raise ValueError("Output does not match mitigation schema")
            
            return self._extract_valid_mitigations(parsed)
            
        except json.JSONDecodeError:
            extracted = self._extract_json(raw_output)
            if extracted:
                return self.validate_mitigation_output(extracted)
            
            if self.validation_strict:
                raise
            return self._create_fallback_mitigation_output(raw_output)
    
    def validate_compliance_output(self, raw_output: str) -> Dict[str, Any]:
        """Validate Auditor agent compliance output"""
        schema = {
            "type": "object",
            "properties": {
                "compliance_results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "framework": {"type": "string"},
                            "requirement": {"type": "string"},
                            "status": {"type": "string", "enum": ["COMPLIANT", "NON_COMPLIANT", "PARTIAL", "NOT_APPLICABLE"]},
                            "evidence": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                        },
                        "required": ["framework", "requirement", "status", "evidence", "confidence"]
                    }
                },
                "hitl_required": {"type": "boolean"},
                "hitl_recommendation": {"type": "string", "enum": ["FREEZE_PAYMENTS", "INVESTIGATE_FURTHER", "ESCALATE"]}
            },
            "required": ["compliance_results", "hitl_required", "hitl_recommendation"]
        }
        
        if not self.enabled or not self._initialized:
            return self._parse_json_fallback(raw_output)
        
        try:
            parsed = json.loads(raw_output)
            if self._validate_schema(parsed, schema):
                return parsed
            if self.validation_strict:
                raise ValueError("Compliance output validation failed")
            return self._extract_valid_compliance(parsed)
        except json.JSONDecodeError:
            extracted = self._extract_json(raw_output)
            if extracted:
                return self.validate_compliance_output(extracted)
            if self.validation_strict:
                raise
            return {"compliance_results": [], "hitl_required": False, "hitl_recommendation": "INVESTIGATE_FURTHER"}
    
    # --- Helper methods ---
    
    def _validate_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """Simple schema validation"""
        try:
            import jsonschema
            jsonschema.validate(data, schema)
            return True
        except Exception:
            return False
    
    def _extract_json(self, text: str) -> Optional[str]:
        """Extract JSON from text"""
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return match.group()
        return None
    
    def _parse_json_fallback(self, text: str) -> Dict[str, Any]:
        """Fallback JSON parsing without guardrails"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            extracted = self._extract_json(text)
            if extracted:
                return json.loads(extracted)
            return {}
    
    def _extract_valid_risk_factors(self, data: Dict) -> Dict[str, Any]:
        """Extract valid risk factors from partial data"""
        risk_factors = []
        if isinstance(data.get("risk_factors"), list):
            for rf in data["risk_factors"]:
                if isinstance(rf, dict) and all(k in rf for k in ["category", "level", "title", "description", "confidence"]):
                    rf.setdefault("id", f"rf-{uuid4().hex[:8]}")
                    rf.setdefault("evidence_ids", [])
                    rf.setdefault("metadata", {})
                    risk_factors.append(rf)
        
        return {
            "risk_factors": risk_factors,
            "needs_more_evidence": data.get("needs_more_evidence", len(risk_factors) == 0),
            "summary": data.get("summary", "Partial extraction from malformed output")
        }
    
    def _extract_valid_mitigations(self, data: Dict) -> Dict[str, Any]:
        """Extract valid mitigations from partial data"""
        actions = []
        if isinstance(data.get("mitigation_actions"), list):
            for ma in data["mitigation_actions"]:
                if isinstance(ma, dict) and all(k in ma for k in ["risk_factor_id", "title", "description", "action_type", "priority"]):
                    ma.setdefault("id", f"ma-{uuid4().hex[:8]}")
                    ma.setdefault("estimated_cost_usd", None)
                    ma.setdefault("estimated_timeline_days", None)
                    ma.setdefault("status", "PROPOSED")
                    actions.append(ma)
        
        alternatives = []
        if isinstance(data.get("alternative_suppliers"), list):
            for alt in data["alternative_suppliers"]:
                if isinstance(alt, dict) and all(k in alt for k in ["original_supplier_id", "name", "country", "risk_score"]):
                    alt.setdefault("id", f"as-{uuid4().hex[:8]}")
                    alt.setdefault("cost_difference_pct", None)
                    alt.setdefault("lead_time_days", None)
                    alt.setdefault("quality_rating", None)
                    alt.setdefault("certifications", [])
                    alternatives.append(alt)
        
        return {
            "mitigation_actions": actions,
            "alternative_suppliers": alternatives,
            "summary": data.get("summary", "Partial extraction from malformed output")
        }
    
    def _extract_valid_compliance(self, data: Dict) -> Dict[str, Any]:
        """Extract valid compliance results"""
        results = []
        if isinstance(data.get("compliance_results"), list):
            for cr in data["compliance_results"]:
                if isinstance(cr, dict) and all(k in cr for k in ["framework", "requirement", "status", "evidence", "confidence"]):
                    results.append(cr)
        
        return {
            "compliance_results": results,
            "hitl_required": data.get("hitl_required", len(results) > 0),
            "hitl_recommendation": data.get("hitl_recommendation", "INVESTIGATE_FURTHER")
        }
    
    def _create_fallback_risk_output(self, raw: str) -> Dict[str, Any]:
        """Create minimal valid output from unparseable text"""
        return {
            "risk_factors": [{
                "id": f"rf-{uuid4().hex[:8]}",
                "category": "OPERATIONAL",
                "level": "MEDIUM",
                "title": "Analysis incomplete - parsing failed",
                "description": "LLM output could not be parsed as structured risk factors",
                "confidence": 0.1,
                "evidence_ids": [],
                "metadata": {"parse_error": True, "raw_output": raw[:500]}
            }],
            "needs_more_evidence": True,
            "summary": "Output validation failed - manual review required"
        }
    
    def _create_fallback_mitigation_output(self, raw: str) -> Dict[str, Any]:
        """Create minimal valid mitigation output"""
        return {
            "mitigation_actions": [{
                "id": f"ma-{uuid4().hex[:8]}",
                "risk_factor_id": "unknown",
                "title": "Manual review required",
                "description": "LLM output could not be parsed for mitigation actions",
                "action_type": "MANUAL_REVIEW",
                "estimated_cost_usd": None,
                "estimated_timeline_days": None,
                "priority": 3,
                "status": "PROPOSED"
            }],
            "alternative_suppliers": [],
            "summary": "Output validation failed - manual review required"
        }
    
    # --- Input Sanitization ---
    
    def sanitize_input(self, text: str, max_length: int = 10000) -> str:
        """Sanitize user input before sending to LLM"""
        if not text:
            return ""
        
        text = text[:max_length]
        text = self.injection_regex.sub("[FILTERED]", text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text


# Global instance
_guardrails: Optional[GuardrailsValidator] = None


async def get_guardrails(config: Dict[str, Any] = None) -> GuardrailsValidator:
    """Get or create guardrails validator"""
    global _guardrails
    if _guardrails is None:
        _guardrails = GuardrailsValidator(config)
        await _guardrails.initialize()
    return _guardrails


from uuid import uuid4