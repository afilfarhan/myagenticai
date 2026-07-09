"""
Golden evaluation cases for SentinelChain
"""
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime

from app.models import RiskLevel, RiskCategory, EvidenceType


@dataclass
class ExpectedRiskFactor:
    """Expected risk factor for evaluation"""
    category: RiskCategory
    level: RiskLevel
    title_contains: str  # Substring that should be in title
    description_contains: str  # Substring that should be in description
    min_confidence: float = 0.5
    required_evidence_types: List[EvidenceType] = field(default_factory=list)


@dataclass
class ExpectedMitigation:
    """Expected mitigation action for evaluation"""
    risk_factor_title_contains: str
    title_contains: str
    priority: str  # HIGH, MEDIUM, LOW
    action_type: str


@dataclass
class ExpectedAlternative:
    """Expected alternative supplier"""
    name_contains: str
    country: str
    max_risk_score: float = 40.0


@dataclass
class ExpectedOutput:
    """Complete expected output for a case"""
    risk_factors: List[ExpectedRiskFactor] = field(default_factory=list)
    mitigations: List[ExpectedMitigation] = field(default_factory=list)
    alternatives: List[ExpectedAlternative] = field(default_factory=list)
    hitl_required: bool = False
    hitl_recommendation: str = "INVESTIGATE_FURTHER"


@dataclass
class EvaluationCase:
    """Single evaluation case with input and expected output"""
    case_id: str
    supplier_name: str
    supplier_country: str
    supplier_industry: str
    query: str
    evidence: List[Dict[str, Any]]  # Mock evidence for testing
    expected: ExpectedOutput
    metadata: Dict[str, Any] = field(default_factory=dict)


# Golden evaluation cases - comprehensive coverage
golden_cases: List[EvaluationCase] = [
    # Case 1: Financial distress - Taiwan semiconductor
    EvaluationCase(
        case_id="golden-001",
        supplier_name="TechCorp Taiwan",
        supplier_country="TW",
        supplier_industry="Semiconductors",
        query="Investigate financial stability of TechCorp Taiwan over last 6 months",
        evidence=[
            {
                "type": "FINANCIAL_REPORT",
                "source": "exa",
                "title": "TechCorp Taiwan 10-Q Q3 2024",
                "content": "TechCorp Taiwan reported 40% drop in cash reserves from $2.1B to $1.26B. Operating cash flow negative at -$340M. Debt-to-equity ratio increased from 0.8 to 1.4. Revenue declined 15% YoY.",
                "url": "https://sec.gov/techcorp/10q-2024-q3",
                "credibility_score": 0.9,
                "relevance_score": 0.95
            },
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "TechCorp Taiwan delays supplier payments",
                "content": "Multiple Tier-2 suppliers report payment delays of 60-90 days. Company negotiating debt restructuring with creditors.",
                "url": "https://reuters.com/techcorp-payment-delays",
                "credibility_score": 0.8,
                "relevance_score": 0.85
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.FINANCIAL,
                    level=RiskLevel.HIGH,
                    title_contains="cash reserves",
                    description_contains="40% drop",
                    min_confidence=0.8,
                    required_evidence_types=[EvidenceType.FINANCIAL_REPORT]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.FINANCIAL,
                    level=RiskLevel.HIGH,
                    title_contains="debt",
                    description_contains="debt-to-equity",
                    min_confidence=0.75,
                    required_evidence_types=[EvidenceType.FINANCIAL_REPORT]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.OPERATIONAL,
                    level=RiskLevel.MEDIUM,
                    title_contains="supplier payment",
                    description_contains="payment delays",
                    min_confidence=0.7,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                )
            ],
            mitigations=[
                ExpectedMitigation(
                    risk_factor_title_contains="cash reserves",
                    title_contains="emergency credit line",
                    priority="HIGH",
                    action_type="FINANCIAL_SUPPORT"
                ),
                ExpectedMitigation(
                    risk_factor_title_contains="supplier payment",
                    title_contains="payment terms renegotiation",
                    priority="MEDIUM",
                    action_type="CONTRACT_RENEGOTIATION"
                )
            ],
            alternatives=[
                ExpectedAlternative(
                    name_contains="TSMC",
                    country="TW",
                    max_risk_score=25.0
                ),
                ExpectedAlternative(
                    name_contains="ASE",
                    country="TW",
                    max_risk_score=30.0
                )
            ],
            hitl_required=False,
            hitl_recommendation="INVESTIGATE_FURTHER"
        ),
        metadata={"category": "financial_distress", "tier": "TIER_1"}
    ),
    
    # Case 2: Sanctions violation - German automotive
    EvaluationCase(
        case_id="golden-002",
        supplier_name="EuroParts GmbH",
        supplier_country="DE",
        supplier_industry="Automotive",
        query="Check sanctions compliance for EuroParts GmbH",
        evidence=[
            {
                "type": "SANCTIONS_LIST",
                "source": "apify",
                "title": "EU Sanctions List - New Entry",
                "content": "Entity 'SteelWorks Russia' added to EU sanctions list 2024-01-15. Reason: Military equipment supply to sanctioned regime.",
                "url": "https://eur-lex.europa.eu/sanctions/steelworks-russia",
                "credibility_score": 0.95,
                "relevance_score": 0.9
            },
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "EuroParts GmbH subcontractor linked to sanctioned entity",
                "content": "Investigation reveals EuroParts GmbH uses SteelWorks Russia as Tier-3 subcontractor for raw steel. Contract value: €12M annually.",
                "url": "https://dw.com/europarts-sanctions-link",
                "credibility_score": 0.85,
                "relevance_score": 0.9
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.REGULATORY,
                    level=RiskLevel.SEVERE,
                    title_contains="sanctions",
                    description_contains="sanctioned entity",
                    min_confidence=0.9,
                    required_evidence_types=[EvidenceType.SANCTIONS_LIST, EvidenceType.NEWS_ARTICLE]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.REGULATORY,
                    level=RiskLevel.HIGH,
                    title_contains="subcontractor",
                    description_contains="Tier-3",
                    min_confidence=0.8,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                )
            ],
            mitigations=[
                ExpectedMitigation(
                    risk_factor_title_contains="sanctions",
                    title_contains="immediate contract termination",
                    priority="HIGH",
                    action_type="CONTRACT_TERMINATION"
                ),
                ExpectedMitigation(
                    risk_factor_title_contains="sanctions",
                    title_contains="alternative steel sourcing",
                    priority="HIGH",
                    action_type="ALTERNATIVE_SOURCING"
                )
            ],
            alternatives=[
                ExpectedAlternative(
                    name_contains="ThyssenKrupp",
                    country="DE",
                    max_risk_score=20.0
                ),
                ExpectedAlternative(
                    name_contains="Salzgitter",
                    country="DE",
                    max_risk_score=25.0
                )
            ],
            hitl_required=True,
            hitl_recommendation="FREEZE_PAYMENTS"
        ),
        metadata={"category": "sanctions_violation", "tier": "TIER_1"}
    ),
    
    # Case 3: ESG violation - Chinese electronics
    EvaluationCase(
        case_id="golden-003",
        supplier_name="Axia Manufacturing",
        supplier_country="CN",
        supplier_industry="Electronics",
        query="ESG compliance audit for Axia Manufacturing",
        evidence=[
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "Axia Manufacturing cited for water pollution",
                "content": "Local environmental agency fined Axia Manufacturing ¥5M for discharging untreated wastewater into Yangtze tributary. Third violation in 18 months.",
                "url": "https://scmp.com/axia-pollution-fine",
                "credibility_score": 0.85,
                "relevance_score": 0.9
            },
            {
                "type": "GOVERNMENT_REGISTRY",
                "source": "apify",
                "title": "China MEE Violation Record - Axia Manufacturing",
                "content": "Violation ID: CN-MEE-2024-003421. Penalty: ¥5,000,000. Corrective action deadline: 2024-03-15. Status: OVERDUE.",
                "url": "https://mee.gov.cn/violations/003421",
                "credibility_score": 0.95,
                "relevance_score": 0.95
            },
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "Labor dispute at Axia Manufacturing Shenzhen plant",
                "content": "Workers protest 12-hour shifts without overtime pay. Local labor bureau investigation ongoing. 200+ workers affected.",
                "url": "https://globaltimes.cn/axia-labor-dispute",
                "credibility_score": 0.75,
                "relevance_score": 0.8
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.ESG,
                    level=RiskLevel.HIGH,
                    title_contains="water pollution",
                    description_contains="untreated wastewater",
                    min_confidence=0.85,
                    required_evidence_types=[EvidenceType.GOVERNMENT_REGISTRY, EvidenceType.NEWS_ARTICLE]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.ESG,
                    level=RiskLevel.HIGH,
                    title_contains="labor",
                    description_contains="12-hour shifts",
                    min_confidence=0.7,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.REGULATORY,
                    level=RiskLevel.MEDIUM,
                    title_contains="corrective action",
                    description_contains="OVERDUE",
                    min_confidence=0.9,
                    required_evidence_types=[EvidenceType.GOVERNMENT_REGISTRY]
                )
            ],
            mitigations=[
                ExpectedMitigation(
                    risk_factor_title_contains="water pollution",
                    title_contains="environmental remediation plan",
                    priority="HIGH",
                    action_type="COMPLIANCE_ACTION"
                ),
                ExpectedMitigation(
                    risk_factor_title_contains="labor",
                    title_contains="labor standards audit",
                    priority="HIGH",
                    action_type="AUDIT"
                )
            ],
            alternatives=[
                ExpectedAlternative(
                    name_contains="Foxconn",
                    country="TW",
                    max_risk_score=35.0
                ),
                ExpectedAlternative(
                    name_contains="Pegatron",
                    country="TW",
                    max_risk_score=35.0
                )
            ],
            hitl_required=True,
            hitl_recommendation="INVESTIGATE_FURTHER"
        ),
        metadata={"category": "esg_violation", "tier": "TIER_2"}
    ),

    # Case 4: Geopolitical risk - Port strike
    EvaluationCase(
        case_id="golden-004",
        supplier_name="Northern Logistics",
        supplier_country="US",
        supplier_industry="Logistics",
        query="Assess port strike impact on Northern Logistics shipping routes",
        evidence=[
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "West Coast port strike enters third week",
                "content": "ILWU strike at LA/Long Beach ports continues. 40+ container ships anchored. Estimated $2.1B daily economic impact. No resolution in sight.",
                "url": "https://wsj.com/port-strike-week3",
                "credibility_score": 0.9,
                "relevance_score": 0.95
            },
            {
                "type": "SATELLITE_IMAGERY",
                "source": "e2b",
                "title": "Port congestion analysis - LA/Long Beach",
                "content": "Satellite imagery shows 47 container ships at anchor (vs 8 normal). Average wait time: 14.2 days. Throughput down 68%.",
                "url": "https://planet.com/ports/la-longbeach-2024",
                "credibility_score": 0.9,
                "relevance_score": 0.9
            },
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "Northern Logistics reroutes through Panama Canal",
                "content": "Northern Logistics announced rerouting 60% of Asia-US cargo through Panama Canal. Additional transit time: 10-14 days. Cost increase: 35%.",
                "url": "https://freightwaves.com/northern-logistics-reroute",
                "credibility_score": 0.85,
                "relevance_score": 0.9
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.GEOPOLITICAL,
                    level=RiskLevel.HIGH,
                    title_contains="port strike",
                    description_contains="LA/Long Beach",
                    min_confidence=0.9,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.OPERATIONAL,
                    level=RiskLevel.HIGH,
                    title_contains="shipping delay",
                    description_contains="14.2 days",
                    min_confidence=0.85,
                    required_evidence_types=[EvidenceType.SATELLITE_IMAGERY]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.FINANCIAL,
                    level=RiskLevel.MEDIUM,
                    title_contains="cost increase",
                    description_contains="35%",
                    min_confidence=0.8,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                )
            ],
            mitigations=[
                ExpectedMitigation(
                    risk_factor_title_contains="port strike",
                    title_contains="alternative port contracts",
                    priority="HIGH",
                    action_type="CONTRACT_NEGOTIATION"
                ),
                ExpectedMitigation(
                    risk_factor_title_contains="shipping delay",
                    title_contains="inventory buffer increase",
                    priority="MEDIUM",
                    action_type="INVENTORY_MANAGEMENT"
                )
            ],
            alternatives=[
                ExpectedAlternative(
                    name_contains="C.H. Robinson",
                    country="US",
                    max_risk_score=30.0
                ),
                ExpectedAlternative(
                    name_contains="Expeditors",
                    country="US",
                    max_risk_score=28.0
                )
            ],
            hitl_required=False,
            hitl_recommendation="INVESTIGATE_FURTHER"
        ),
        metadata={"category": "geopolitical", "tier": "TIER_3"}
    ),

    # Case 5: Cyber risk - US tech supplier
    EvaluationCase(
        case_id="golden-005",
        supplier_name="DataFlow Systems",
        supplier_country="US",
        supplier_industry="Technology",
        query="Investigate cybersecurity posture of DataFlow Systems",
        evidence=[
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "DataFlow Systems discloses data breach",
                "content": "DataFlow Systems filed SEC 8-K disclosing unauthorized access to customer database. 2.3M records exposed including PII. Breach detected 2024-02-15, occurred 2023-11-01.",
                "url": "https://sec.gov/dataflow-8k-2024",
                "credibility_score": 0.95,
                "relevance_score": 0.95
            },
            {
                "type": "GOVERNMENT_REGISTRY",
                "source": "apify",
                "title": "CISA KEV - DataFlow Systems vulnerability",
                "content": "CVE-2023-48795 (SSH transport confusion) exploited in DataFlow Systems VPN. Added to CISA Known Exploited Vulnerabilities catalog 2024-01-20.",
                "url": "https://cisa.gov/kev/dataflow-2024",
                "credibility_score": 0.95,
                "relevance_score": 0.9
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.CYBER,
                    level=RiskLevel.SEVERE,
                    title_contains="data breach",
                    description_contains="2.3M records",
                    min_confidence=0.95,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.CYBER,
                    level=RiskLevel.HIGH,
                    title_contains="vulnerability",
                    description_contains="CVE-2023-48795",
                    min_confidence=0.9,
                    required_evidence_types=[EvidenceType.GOVERNMENT_REGISTRY]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.REGULATORY,
                    level=RiskLevel.HIGH,
                    title_contains="SEC disclosure",
                    description_contains="8-K",
                    min_confidence=0.9,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                )
            ],
            mitigations=[
                ExpectedMitigation(
                    risk_factor_title_contains="data breach",
                    title_contains="incident response engagement",
                    priority="HIGH",
                    action_type="INCIDENT_RESPONSE"
                ),
                ExpectedMitigation(
                    risk_factor_title_contains="vulnerability",
                    title_contains="emergency patching",
                    priority="HIGH",
                    action_type="VULNERABILITY_REMEDIATION"
                )
            ],
            alternatives=[
                ExpectedAlternative(
                    name_contains="Snowflake",
                    country="US",
                    max_risk_score=25.0
                ),
                ExpectedAlternative(
                    name_contains="Databricks",
                    country="US",
                    max_risk_score=28.0
                )
            ],
            hitl_required=True,
            hitl_recommendation="FREEZE_PAYMENTS"
        ),
        metadata={"category": "cyber", "tier": "TIER_1"}
    ),

    # Case 6: Low risk - stable supplier
    EvaluationCase(
        case_id="golden-006",
        supplier_name="Northern Logistics",
        supplier_country="US",
        supplier_industry="Logistics",
        query="Routine compliance check for Northern Logistics",
        evidence=[
            {
                "type": "FINANCIAL_REPORT",
                "source": "exa",
                "title": "Northern Logistics 10-K 2023",
                "content": "Revenue $4.2B (+5% YoY). Operating margin 12.3%. Cash reserves $850M. Debt-to-equity 0.3. No covenant violations.",
                "url": "https://sec.gov/northern-logistics/10k-2023",
                "credibility_score": 0.9,
                "relevance_score": 0.8
            },
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "Northern Logistics recognized for sustainability",
                "content": "Company awarded EPA SmartWay Excellence Award for 5th consecutive year. Fleet emissions reduced 22% since 2020.",
                "url": "https://epa.gov/smartway/northern-logistics",
                "credibility_score": 0.85,
                "relevance_score": 0.7
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.FINANCIAL,
                    level=RiskLevel.LOW,
                    title_contains="financial health",
                    description_contains="strong cash position",
                    min_confidence=0.8,
                    required_evidence_types=[EvidenceType.FINANCIAL_REPORT]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.ESG,
                    level=RiskLevel.LOW,
                    title_contains="sustainability",
                    description_contains="emissions reduced",
                    min_confidence=0.7,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                )
            ],
            mitigations=[],
            alternatives=[],
            hitl_required=False,
            hitl_recommendation="INVESTIGATE_FURTHER"
        ),
        metadata={"category": "low_risk", "tier": "TIER_3"}
    ),

    # Case 7: Operational risk - Factory fire
    EvaluationCase(
        case_id="golden-007",
        supplier_name="Axia Manufacturing",
        supplier_country="CN",
        supplier_industry="Electronics",
        query="Assess impact of factory fire at Axia Manufacturing",
        evidence=[
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "Fire at Axia Manufacturing Shenzhen plant",
                "content": "Major fire at Axia Manufacturing PCB assembly plant in Shenzhen. 3 production lines destroyed. Estimated 3-month recovery. No injuries reported.",
                "url": "https://reuters.com/axia-fire-shenzhen",
                "credibility_score": 0.9,
                "relevance_score": 0.95
            },
            {
                "type": "SATELLITE_IMAGERY",
                "source": "e2b",
                "title": "Fire damage assessment - Axia Shenzhen",
                "content": "Satellite imagery confirms 60% of Building 3 destroyed. Adjacent buildings smoke damaged. Thermal anomalies detected for 48 hours post-fire.",
                "url": "https://planet.com/fire/axia-shenzhen-2024",
                "credibility_score": 0.85,
                "relevance_score": 0.9
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.OPERATIONAL,
                    level=RiskLevel.HIGH,
                    title_contains="factory fire",
                    description_contains="3 production lines destroyed",
                    min_confidence=0.9,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE, EvidenceType.SATELLITE_IMAGERY]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.FINANCIAL,
                    level=RiskLevel.MEDIUM,
                    title_contains="revenue impact",
                    description_contains="3-month recovery",
                    min_confidence=0.8,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE]
                )
            ],
            mitigations=[
                ExpectedMitigation(
                    risk_factor_title_contains="factory fire",
                    title_contains="alternate production capacity",
                    priority="HIGH",
                    action_type="CONTINGENCY_PLANNING"
                ),
                ExpectedMitigation(
                    risk_factor_title_contains="factory fire",
                    title_contains="insurance claim acceleration",
                    priority="HIGH",
                    action_type="FINANCIAL_RECOVERY"
                )
            ],
            alternatives=[
                ExpectedAlternative(
                    name_contains="Flex",
                    country="SG",
                    max_risk_score=30.0
                ),
                ExpectedAlternative(
                    name_contains="Jabil",
                    country="US",
                    max_risk_score=32.0
                )
            ],
            hitl_required=False,
            hitl_recommendation="INVESTIGATE_FURTHER"
        ),
        metadata={"category": "operational", "tier": "TIER_2"}
    ),

    # Case 8: Reputational risk - Forced labor allegations
    EvaluationCase(
        case_id="golden-008",
        supplier_name="EuroParts GmbH",
        supplier_country="DE",
        supplier_industry="Automotive",
        query="Investigate forced labor allegations in EuroParts GmbH supply chain",
        evidence=[
            {
                "type": "NEWS_ARTICLE",
                "source": "tavily",
                "title": "NGO report links EuroParts to forced labor in Xinjiang",
                "content": "Human Rights Watch report alleges EuroParts GmbH Tier-2 supplier uses forced labor in Xinjiang cotton processing. EuroParts denies, launches audit.",
                "url": "https://hrw.org/europarts-forced-labor",
                "credibility_score": 0.8,
                "relevance_score": 0.85
            },
            {
                "type": "GOVERNMENT_REGISTRY",
                "source": "apify",
                "title": "German BAFA investigation - EuroParts GmbH",
                "content": "BAFA (Federal Office for Economic Affairs and Export Control) opened investigation into EuroParts GmbH supply chain due diligence under LkSG. Case ID: DE-BAFA-2024-01892.",
                "url": "https://bafa.de/investigations/01892",
                "credibility_score": 0.95,
                "relevance_score": 0.9
            }
        ],
        expected=ExpectedOutput(
            risk_factors=[
                ExpectedRiskFactor(
                    category=RiskCategory.ESG,
                    level=RiskLevel.SEVERE,
                    title_contains="forced labor",
                    description_contains="Xinjiang",
                    min_confidence=0.8,
                    required_evidence_types=[EvidenceType.NEWS_ARTICLE, EvidenceType.GOVERNMENT_REGISTRY]
                ),
                ExpectedRiskFactor(
                    category=RiskCategory.REGULATORY,
                    level=RiskLevel.HIGH,
                    title_contains="LkSG investigation",
                    description_contains="due diligence",
                    min_confidence=0.9,
                    required_evidence_types=[EvidenceType.GOVERNMENT_REGISTRY]
                )
            ],
            mitigations=[
                ExpectedMitigation(
                    risk_factor_title_contains="forced labor",
                    title_contains="immediate supplier audit",
                    priority="HIGH",
                    action_type="AUDIT"
                ),
                ExpectedMitigation(
                    risk_factor_title_contains="forced labor",
                    title_contains="supply chain mapping",
                    priority="HIGH",
                    action_type="SUPPLY_CHAIN_TRANSPARENCY"
                )
            ],
            alternatives=[
                ExpectedAlternative(
                    name_contains="Continental",
                    country="DE",
                    max_risk_score=25.0
                ),
                ExpectedAlternative(
                    name_contains="Bosch",
                    country="DE",
                    max_risk_score=20.0
                )
            ],
            hitl_required=True,
            hitl_recommendation="ESCALATE"
        ),
        metadata={"category": "reputational", "tier": "TIER_1"}
    ),
]


def get_cases_by_category(category: str) -> List[EvaluationCase]:
    """Filter cases by category"""
    return [c for c in golden_cases if c.metadata.get("category") == category]


def get_cases_by_tier(tier: str) -> List[EvaluationCase]:
    """Filter cases by supplier tier"""
    return [c for c in golden_cases if c.metadata.get("tier") == tier]