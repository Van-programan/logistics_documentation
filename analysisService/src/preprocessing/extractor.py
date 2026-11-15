from __future__ import annotations

import re

from src.parsing.result_model import ParsedDocument
from src.preprocessing.models import (
    CandidateFragment,
    PreprocessingResult,
    TriggerMatch,
)
from src.preprocessing.triggers import RISK_TRIGGERS, RiskTriggerConfig


def preprocess(doc: ParsedDocument, configs: list[RiskTriggerConfig] | None = None) -> PreprocessingResult:
    configs = configs or RISK_TRIGGERS
    full_text = doc.full_text

    result = PreprocessingResult()

    for cfg in configs:
        result.risk_types_checked.append(cfg.risk_type)

        positive_matches: list[TriggerMatch] = []
        for phrase in cfg.positive_triggers:
            for m_start, m_end in _find_phrase_matches(full_text, phrase):
                positive_matches.append(TriggerMatch(
                    phrase=phrase,
                    risk_type=cfg.risk_type,
                    global_start=m_start,
                    global_end=m_end,
                    is_negative=False,
                ))

        for pattern in cfg.positive_patterns:
            for m in re.finditer(pattern, full_text, flags=re.IGNORECASE):
                positive_matches.append(TriggerMatch(
                    phrase=m.group(0),
                    risk_type=cfg.risk_type,
                    global_start=m.start(),
                    global_end=m.end(),
                    is_negative=False,
                ))

        negative_matches: list[TriggerMatch] = []
        for pattern in cfg.negative_patterns:
            for m in re.finditer(pattern, full_text, flags=re.IGNORECASE):
                negative_matches.append(TriggerMatch(
                    phrase=m.group(0),
                    risk_type=cfg.risk_type,
                    global_start=m.start(),
                    global_end=m.end(),
                    is_negative=True,
                ))

        result.triggers.extend(positive_matches)
        result.triggers.extend(negative_matches)

        if not positive_matches:
            if cfg.is_absence_risk:
                result.risk_types_without_any_triggers.append(cfg.risk_type)
            continue

        windows = _build_windows(full_text, positive_matches, cfg)
        merged = _merge_windows(windows)

        fragments: list[CandidateFragment] = []
        for start, end, triggers in merged:
            has_neg = any(
                neg.global_start < end and neg.global_end > start
                for neg in negative_matches
            )
            window_text = full_text[start:end]

            frag = CandidateFragment(
                risk_type=cfg.risk_type,
                global_start=start,
                global_end=end,
                text=window_text,
                triggers=triggers,
                has_negative_context=has_neg,
            )
            fragments.append(frag)

        for frag in fragments:
            frag.rank = (
                len(frag.triggers) * 10
                + (0 if frag.has_negative_context else 5)
                - (0 if not frag.has_negative_context else 3)
            )
            if cfg.risk_type == "acceptance_missing" and _has_acceptance_term(frag.text):
                frag.rank += 20
            if cfg.risk_type == "auto_renewal" and _has_renewal_term(frag.text):
                frag.rank += 20

        fragments.sort(key=lambda f: f.rank, reverse=True)
        fragments = fragments[:cfg.max_fragments]

        result.fragments.extend(fragments)

    _force_add_table_to_risks(doc, result)
    _deduplicate_fragments(result)

    return result


_TABLE_RISKS = {"quantity_undefined", "item_name_vague", "schedule_missing"}


def _force_add_table_to_risks(doc: ParsedDocument, result: PreprocessingResult) -> None:
    pipe_idx = _find_product_table(doc.full_text)
    if pipe_idx < 0:
        return

    start = max(0, pipe_idx - 300)
    end = min(len(doc.full_text), pipe_idx + 3000)
    chunk = doc.full_text[start:end]
    if not chunk.strip():
        return
    if not _is_product_table(chunk):
        return

    for risk_type in _TABLE_RISKS:
        existing = result.fragments_for(risk_type)
        if any("|" in f.text and _is_product_table(f.text) for f in existing):
            continue

        already_added = any(
            f.risk_type == risk_type
            and f.global_start == start
            and f.global_end == end
            for f in result.fragments
        )
        if already_added:
            continue

        result.fragments.append(CandidateFragment(
            risk_type=risk_type,
            global_start=start,
            global_end=end,
            text=chunk,
            triggers=[],
            has_negative_context=False,
        ))


def _find_product_table(full_text: str) -> int:
    for m in re.finditer(r"\|", full_text):
        idx = m.start()
        snippet = full_text[max(0, idx - 500):idx + 500]
        if _is_product_table(snippet):
            return idx
    return -1


def _is_product_table(text: str) -> bool:
    if "|" not in text:
        return False

    lower = text.lower()

    req_markers = ["инн", "кпп", "бик", "р/с", "к/с", "юридический адрес", "м.п.", "огрн"]
    req_count = sum(1 for m in req_markers if m in lower)
    if req_count >= 2:
        return False

    product_markers = [
        r"\d+\s*(?:шт|штук|ед|м|кг|руб)",
        r"кол-?во",
        r"цена",
        r"стоимость",
        r"наименование",
        r"артикул",
        r"ед\.?\s*изм",
    ]
    return any(re.search(p, lower) for p in product_markers)


def _deduplicate_fragments(result: PreprocessingResult) -> None:
    seen: set[tuple[str, int, int]] = set()
    unique: list[CandidateFragment] = []
    for frag in result.fragments:
        key = (frag.risk_type, frag.global_start, frag.global_end)
        if key in seen:
            continue
        seen.add(key)
        unique.append(frag)
    result.fragments = unique


def _find_phrase_matches(text: str, phrase: str) -> list[tuple[int, int]]:
    parts = phrase.split()
    if not parts:
        return []
    pattern = r"[\s\xa0\u2009\u202f]+".join(re.escape(p) for p in parts)
    return [
        (m.start(), m.end())
        for m in re.finditer(pattern, text, flags=re.IGNORECASE)
    ]


def _build_windows(text, matches, cfg):
    windows = []
    for m in matches:
        start = max(0, m.global_start - cfg.context_before)
        end = min(len(text), m.global_end + cfg.context_after)
        start = _snap_word_start(text, start)
        end = _snap_word_end(text, end)
        windows.append((start, end, m))
    return windows


def _merge_windows(windows):
    if not windows:
        return []
    windows.sort(key=lambda w: w[0])
    merged = []
    current_start, current_end, first_trigger = windows[0]
    current_triggers = [first_trigger]
    for start, end, trigger in windows[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            current_triggers.append(trigger)
        else:
            merged.append((current_start, current_end, current_triggers))
            current_start, current_end = start, end
            current_triggers = [trigger]
    merged.append((current_start, current_end, current_triggers))
    return merged


def _snap_word_start(text, pos):
    if pos <= 0:
        return 0
    while pos > 0 and pos < len(text) and text[pos - 1].isalnum() and text[pos].isalnum():
        pos -= 1
    return pos


def _snap_word_end(text, pos):
    if pos >= len(text):
        return len(text)
    while pos < len(text) and text[pos].isalnum():
        pos += 1
    return pos

def _has_acceptance_term(text: str) -> bool:
    from src.preprocessing.terms.acceptance import extract_acceptance_terms
    return len(extract_acceptance_terms(text)) > 0

def _has_renewal_term(text: str) -> bool:
    from src.preprocessing.terms.renewal import extract_renewal_terms
    return len(extract_renewal_terms(text)) > 0