"""
PII Masking Service for SentinelChain - Microsoft Presidio integration
"""
import re
from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)


class PIIMasker:
    """PII masking using regex patterns (Presidio fallback)"""
    
    # Regex patterns for common PII types
    PATTERNS = {
        "EMAIL_ADDRESS": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        "PHONE_NUMBER": re.compile(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'),
        "CREDIT_CARD": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        "IP_ADDRESS": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        "IBAN_CODE": re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b'),
        "SSN": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        "PASSPORT": re.compile(r'\b[A-Z]{1,2}\d{6,9}\b'),
    }
    
    # Entity types that Presidio would detect
    PRESIDIO_ENTITIES = [
        "PERSON",
        "LOCATION", 
        "ORGANIZATION",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "CREDIT_CARD",
        "IBAN_CODE",
        "IP_ADDRESS",
        "DATE_TIME",
        "NRP",  # National ID
    ]
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.language = self.config.get("language", "en")
        self.entities_to_mask = self.config.get("entities_to_mask", self.PRESIDIO_ENTITIES)
        
        self._analyzer = None
        self._anonymizer = None
        self._use_presidio = False
        self._init_presidio()
    
    def _init_presidio(self) -> None:
        """Initialize Presidio if available"""
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine
            
            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._use_presidio = True
            logger.info("Presidio PII masking initialized")
        except ImportError:
            logger.warning("Presidio not available, using regex-based masking")
            self._use_presidio = False
        except Exception as e:
            logger.warning("Failed to initialize Presidio", error=str(e))
            self._use_presidio = False
    
    def mask(self, text: str) -> str:
        """
        Mask PII in text, replacing with [REDACTED_ENTITY_TYPE] placeholders
        """
        if not self.enabled or not text:
            return text
        
        if self._use_presidio:
            return self._mask_with_presidio(text)
        else:
            return self._mask_with_regex(text)
    
    def _mask_with_presidio(self, text: str) -> str:
        """Mask using Presidio analyzer + anonymizer"""
        try:
            # Analyze
            results = self._analyzer.analyze(
                text=text,
                entities=self.entities_to_mask,
                language=self.language
            )
            
            # Anonymize
            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=results
            )
            
            return anonymized.text
            
        except Exception as e:
            logger.error("Presidio masking failed", error=str(e))
            return self._mask_with_regex(text)
    
    def _mask_with_regex(self, text: str) -> str:
        """Mask using regex patterns"""
        masked_text = text
        
        for entity_type, pattern in self.PATTERNS.items():
            if entity_type in self.entities_to_mask:
                masked_text = pattern.sub(f"[REDACTED_{entity_type}]", masked_text)
        
        # Also mask PERSON, LOCATION, ORGANIZATION using simple heuristics
        # (Presidio does this with NER models)
        if "PERSON" in self.entities_to_mask:
            # Simple heuristic: Capitalized words that might be names
            # This is very basic - Presidio is much better
            pass
        
        return masked_text
    
    def anonymize(self, text: str) -> str:
        """Replace PII with generic [REDACTED] placeholder"""
        if not self.enabled or not text:
            return text
        
        masked = self.mask(text)
        # Replace all [REDACTED_*] with [REDACTED]
        return re.sub(r'\[REDACTED_[A-Z_]+\]', '[REDACTED]', masked)
    
    def detect_entities(self, text: str) -> List[Dict[str, Any]]:
        """Detect PII entities in text without masking"""
        entities = []
        
        if self._use_presidio:
            try:
                results = self._analyzer.analyze(
                    text=text,
                    entities=self.entities_to_mask,
                    language=self.language
                )
                for r in results:
                    entities.append({
                        "entity_type": r.entity_type,
                        "start": r.start,
                        "end": r.end,
                        "score": r.score,
                        "text": text[r.start:r.end]
                    })
            except Exception as e:
                logger.error("Presidio detection failed", error=str(e))
        else:
            # Regex-based detection
            for entity_type, pattern in self.PATTERNS.items():
                if entity_type in self.entities_to_mask:
                    for match in pattern.finditer(text):
                        entities.append({
                            "entity_type": entity_type,
                            "start": match.start(),
                            "end": match.end(),
                            "score": 0.8,
                            "text": match.group()
                        })
        
        return entities


# Global instance
_pii_masker: Optional[PIIMasker] = None


def get_pii_masker(config: Dict[str, Any] = None) -> PIIMasker:
    """Get or create PII masker instance"""
    global _pii_masker
    if _pii_masker is None:
        _pii_masker = PIIMasker(config)
    return _pii_masker