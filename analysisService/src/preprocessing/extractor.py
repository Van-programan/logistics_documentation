from __future__ import annotations

import re

from src.parsing.result_model import ParsedDocument
from src.preprocessing.models import (
    CandidateFragment,
    PreprocessingResult,
    TriggerMatch,
)
from src.preprocessing.terms_extractor import extract_delivery_terms
from src.preprocessing.triggers import RISK_TRIGGERS, RiskTriggerConfig


def preprocess(
    doc: ParsedDocument,
    configs: list[RiskTriggerConfig] | None = None,
) -> PreprocessingResult:
    configs = configs or RISK_TRIGGERS
    full_text = doc.full_text

    result = PreprocessingResult()

    for cfg in configs:
        result.risk_types_checked.append(cfg.risk_type)

        # 1. Позитивные триггеры (подстроки, whitespace-толерантные)
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

        # 2. Позитивные триггеры (regex)
        for pattern in cfg.positive_patterns:
            for m in re.finditer(pattern, full_text, flags=re.IGNORECASE):
                positive_matches.append(TriggerMatch(
                    phrase=m.group(0),
                    risk_type=cfg.risk_type,
                    global_start=m.start(),
                    global_end=m.end(),
                    is_negative=False,
                ))

        # 3. Негативные триггеры (regex)
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

        # 4. Окна и их слияние
        windows = _build_windows(full_text, positive_matches, cfg)
        merged = _merge_windows(windows)

        # 5. Для каждого окна — извлекаем сроки + создаём фрагмент
        fragments: list[CandidateFragment] = []
        for start, end, triggers in merged:
            has_neg = any(
                neg.global_start < end and neg.global_end > start
                for neg in negative_matches
            )
            window_text = full_text[start:end]
            delivery_terms = extract_delivery_terms(window_text)

            frag = CandidateFragment(
                risk_type=cfg.risk_type,
                global_start=start,
                global_end=end,
                text=window_text,
                triggers=triggers,
                has_negative_context=has_neg,
                delivery_terms=delivery_terms,
            )
            fragments.append(frag)

        # 6. Ранжирование
        for frag in fragments:
            frag.rank = (
                len(frag.triggers) * 10
                + (0 if frag.has_negative_context else 5)
                - (0 if not frag.has_negative_context else 3)
                + len(frag.delivery_terms) * 3
            )

        fragments.sort(key=lambda f: f.rank, reverse=True)
        fragments = fragments[:cfg.max_fragments]

        result.fragments.extend(fragments)

    return result


def _find_phrase_matches(text: str, phrase: str) -> list[tuple[int, int]]:
    """Ищет фразу, игнорируя различия в пробелах и переносах.

    «с момента оплаты» найдёт и «с момента оплаты»,
    и «с \\nмомента оплаты», и «с\\xa0момента оплаты».

    Возвращает список пар (start, end) в координатах `text`.
    """
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