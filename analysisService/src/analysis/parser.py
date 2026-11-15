from __future__ import annotations

import json
import re
from datetime import date, timedelta

from src.contracts.contract import Contract, Risk, RiskFragment
from src.preprocessing.models import CandidateFragment
from src.preprocessing.terms.base import ExtractedTerm, TermKind, TimeUnit
from src.preprocessing.terms.contract_date import extract_contract_date
from src.preprocessing.terms.end_date import extract_end_date


def parse_llm_response(raw: str, full_text: str, contract_id: str, candidates_by_risk: dict[str, list[CandidateFragment]],
    attachments_ok: bool, missing_attachments: list[str]) -> Contract:

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM вернула невалидный JSON: {e}\n{raw[:500]}"
        ) from e

    risks: list[Risk] = []
    seen_risk_keys: set[tuple] = set()

    for item in data.get("risks", []):
        risk = _build_risk(item, candidates_by_risk, full_text)
        if risk is None:
            continue

        risk_key = (
            risk.risk_type,
            risk.severity,
            risk.description.strip().lower()[:100],
        )
        if risk_key in seen_risk_keys:
            continue
        seen_risk_keys.add(risk_key)
        risks.append(risk)

    terms: list[ExtractedTerm] = []
    seen_term_keys: set[tuple] = set()

    for t in data.get("contract_terms", []):
        term = ExtractedTerm.from_export_dict(t)
        if term is None:
            continue
        if term.kind.value == "contract_date":
            continue

        term_key = _term_dedup_key(term)
        if term_key in seen_term_keys:
            continue
        seen_term_keys.add(term_key)
        terms.append(term)

    acceptance_terms = [t for t in terms if t.kind == TermKind.ACCEPTANCE]
    if len(acceptance_terms) > 1:
        preferred = next(
            (t for t in acceptance_terms if t.event == "supplier_signed"),
            acceptance_terms[0],
        )
        terms = [
            t for t in terms
            if t.kind != TermKind.ACCEPTANCE or t is preferred
        ]

    contract_date_obj = _extract_contract_date_obj(full_text)
    end_date_obj = _extract_end_date_obj(full_text, contract_date_obj)

    contract = Contract(
        contract_id=contract_id,
        full_text=full_text,
        risks=risks,
        terms=terms,
        contract_date=contract_date_obj.isoformat() if contract_date_obj else None,
        end_date=end_date_obj.isoformat() if end_date_obj else None,
        attachments_ok=attachments_ok,
        missing_attachments=missing_attachments,
    )

    _post_validate_risks(contract, full_text)

    return contract


def _extract_contract_date_obj(full_text: str) -> date | None:
    terms = extract_contract_date(full_text)
    return terms[0].fixed_date if terms else None


def _extract_end_date_obj(full_text: str, contract_date_obj: date | None) -> date | None:
    terms = extract_end_date(full_text)
    if not terms:
        return None

    et = terms[0]

    if et.fixed_date:
        return et.fixed_date

    if not (et.offset and et.unit):
        return None

    if contract_date_obj is None:
        return None

    if et.unit == TimeUnit.MONTH:
        return _add_months(contract_date_obj, et.offset)
    if et.unit == TimeUnit.CALENDAR:
        return contract_date_obj + timedelta(days=et.offset)

    return None


def _build_risk(item: dict, candidates_by_risk: dict[str, list[CandidateFragment]], full_text: str) -> Risk | None:

    risk_type = item.get("risk_type")
    if not risk_type:
        return None

    severity = item.get("severity", "MEDIUM")
    candidates = candidates_by_risk.get(risk_type, [])

    fragments: list[RiskFragment] = []
    seen_frag_keys: set[tuple[int, int]] = set()

    for f in item.get("fragments", []):
        idx = f.get("candidate_index", -1)
        quote = f.get("quote", "")
        if not (0 <= idx < len(candidates)):
            continue

        cand = candidates[idx]
        local_start, local_end, exact = _resolve_quote(cand.text, quote)
        global_start = cand.global_start + local_start
        global_end = cand.global_start + local_end

        frag_key = (global_start, global_end)
        if frag_key in seen_frag_keys:
            continue
        seen_frag_keys.add(frag_key)

        fragments.append(RiskFragment(
            global_start=global_start,
            global_end=global_end,
            text=full_text[global_start:global_end],
        ))

    confidence = item.get("confidence", "MEDIUM")
    status = "PENDING_CONFIRMATION" if confidence == "LOW" else "ACTIVE"

    return Risk(
        risk_type=risk_type,
        severity=severity,
        confidence=confidence,
        description=item.get("description", ""),
        recommendation=item.get("recommendation", ""),
        fragments=fragments,
        status=status,
    )


def _resolve_quote(candidate_text: str, quote: str) -> tuple[int, int, bool]:
    if not quote:
        return 0, len(candidate_text), False

    pos = candidate_text.find(quote)
    if pos != -1:
        return pos, pos + len(quote), True

    norm_text, index_map = _normalize_with_map(candidate_text)
    norm_quote = _normalize_spaces(quote)

    pos = norm_text.find(norm_quote)
    if pos != -1:
        start = index_map[pos]
        end_idx = pos + len(norm_quote) - 1
        if end_idx < len(index_map):
            end = index_map[end_idx] + 1
        else:
            end = len(candidate_text)
        return start, end, False

    if len(norm_quote) > 30:
        head = norm_quote[:30]
        tail = norm_quote[-30:]
        m_head = norm_text.find(head)
        if m_head != -1:
            m_tail = norm_text.find(tail, m_head)
            if m_tail != -1:
                start = index_map[m_head]
                end_idx = m_tail + len(tail) - 1
                if end_idx < len(index_map):
                    end = index_map[end_idx] + 1
                else:
                    end = len(candidate_text)
                return start, end, False

    return 0, len(candidate_text), False


def _normalize_spaces(text: str) -> str:
    return re.sub(r"[\s\xa0\u2009\u202f]+", " ", text).strip()


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    result = []
    index_map = []
    prev_was_space = False

    for i, ch in enumerate(text):
        if ch.isspace() or ch in "\xa0\u2009\u202f":
            if prev_was_space:
                continue
            result.append(" ")
            index_map.append(i)
            prev_was_space = True
        else:
            result.append(ch)
            index_map.append(i)
            prev_was_space = False

    return "".join(result), index_map


def _term_dedup_key(t: ExtractedTerm) -> tuple:
    return (
        t.kind.value,
        t.sub_kind.value if t.sub_kind else None,
        t.event,
        t.offset,
        t.unit.value if t.unit else None,
        t.fixed_date.isoformat() if t.fixed_date else None,
        t.period_start.isoformat() if t.period_start else None,
        t.period_end.isoformat() if t.period_end else None,
    )


def _post_validate_risks(contract: Contract, full_text: str) -> None:
    has_acceptance = any(t.kind == TermKind.ACCEPTANCE for t in contract.terms)
    has_delivery = any(t.kind == TermKind.DELIVERY for t in contract.terms)
    has_renewal = any(t.kind == TermKind.RENEWAL for t in contract.terms)

    has_product_table = _has_product_table(full_text)

    req_markers = ["инн", "кпп", "бик", "р/с", "к/с", "юридический адрес", "м.п."]

    filtered: list[Risk] = []
    for r in contract.risks:
        if any( any(m in f.text.lower() for m in req_markers) for f in r.fragments):
            continue

        if has_product_table and r.risk_type in ("quantity_undefined", "item_name_vague"):
            continue

        if r.risk_type == "acceptance_missing" and has_acceptance:
            desc_lower = r.description.lower()
            if "скрыт" not in desc_lower and "недостатк" not in desc_lower:
                continue
            if r.severity == "HIGH":
                r.severity = "MEDIUM"

        if r.risk_type == "delivery_term_undefined" and has_delivery:
            if r.severity == "HIGH":
                r.severity = "MEDIUM"

        if r.risk_type == "auto_renewal" and has_renewal:
            if r.severity == "HIGH":
                r.severity = "MEDIUM"

        filtered.append(r)

    contract.risks = filtered


def _has_product_table(full_text: str) -> bool:
    for m in re.finditer(r"\|", full_text):
        snippet = full_text[max(0, m.start() - 500):m.start() + 500]
        lower = snippet.lower()

        req_markers = ["инн", "кпп", "бик", "р/с", "к/с", "юридический адрес", "м.п."]
        if sum(1 for m in req_markers if m in lower) >= 2:
            continue

        product_markers = [
            r"\d+\s*(?:шт|штук|ед|м|кг|руб)",
            r"кол-?во",
            r"цена",
            r"стоимость",
            r"наименование",
            r"артикул",
            r"ед\.?\s*изм",
        ]
        if any(re.search(p, lower) for p in product_markers):
            return True

    return False


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - date(year, month, 1)).days