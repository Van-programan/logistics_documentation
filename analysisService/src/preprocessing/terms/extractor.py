from __future__ import annotations

from src.preprocessing.terms.acceptance import extract_acceptance_terms
from src.preprocessing.terms.base import ExtractedTerm
from src.preprocessing.terms.contract_date import extract_contract_date
from src.preprocessing.terms.delivery import extract_delivery_terms
from src.preprocessing.terms.end_date import extract_end_date
from src.preprocessing.terms.renewal import extract_renewal_terms


def extract_all_terms(text: str) -> list[ExtractedTerm]:
    terms: list[ExtractedTerm] = []
    for dt in extract_delivery_terms(text):
        terms.append(dt.to_extracted())
    for at in extract_acceptance_terms(text):
        terms.append(at.to_extracted())
    for rt in extract_renewal_terms(text):
        terms.append(rt.to_extracted())
    for ct in extract_contract_date(text):
        terms.append(ct.to_extracted())
    for et in extract_end_date(text):
        terms.append(et.to_extracted())
    return terms