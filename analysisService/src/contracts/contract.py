from __future__ import annotations

from dataclasses import dataclass, field

from src.preprocessing.terms.base import ExtractedTerm


@dataclass
class RiskFragment:
    global_start: int
    global_end: int
    text: str


@dataclass
class Risk:
    risk_type: str
    severity: str
    confidence: str
    description: str
    recommendation: str
    fragments: list[RiskFragment] = field(default_factory=list)
    status: str = "ACTIVE"

    @property
    def requires_manual_review(self) -> bool:
        return self.confidence == "LOW" or self.status == "PENDING_CONFIRMATION"


@dataclass
class Contract:
    contract_id: str
    full_text: str

    risks: list[Risk] = field(default_factory=list)
    terms: list[ExtractedTerm] = field(default_factory=list)

    contract_date: str | None = None
    end_date: str | None = None

    attachments_ok: bool = True
    missing_attachments: list[str] = field(default_factory=list)

    @property
    def has_risks(self) -> bool:
        return len(self.risks) > 0

    @property
    def high_risks(self) -> list[Risk]:
        return [r for r in self.risks if r.severity == "HIGH"]

    @property
    def pending_risks(self) -> list[Risk]:
        return [r for r in self.risks if r.requires_manual_review]