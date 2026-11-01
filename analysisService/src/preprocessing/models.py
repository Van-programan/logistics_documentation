from __future__ import annotations

from dataclasses import dataclass, field
from src.preprocessing.delivery_term import DeliveryTerm

@dataclass
class RiskTriggerConfig:
    risk_type: str
    positive_triggers: list[str] = field(default_factory=list)
    positive_patterns: list[str] = field(default_factory=list)
    negative_patterns: list[str] = field(default_factory=list)
    context_before: int = 125
    context_after: int = 225
    is_absence_risk: bool = False
    max_fragments: int = 4


@dataclass
class TriggerMatch:
    phrase: str
    risk_type: str
    global_start: int
    global_end: int
    is_negative: bool = False


@dataclass
class CandidateFragment:
    risk_type: str
    global_start: int
    global_end: int
    text: str
    triggers: list[TriggerMatch] = field(default_factory=list)
    has_negative_context: bool = False
    delivery_terms: list[DeliveryTerm] = field(default_factory=list)
    rank: int = 0


@dataclass
class PreprocessingResult:
    fragments: list[CandidateFragment] = field(default_factory=list)
    triggers: list[TriggerMatch] = field(default_factory=list)
    risk_types_checked: list[str] = field(default_factory=list)
    risk_types_without_any_triggers: list[str] = field(default_factory=list)

    def fragments_for(self, risk_type: str) -> list[CandidateFragment]:
        return [f for f in self.fragments if f.risk_type == risk_type]