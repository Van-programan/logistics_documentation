from __future__ import annotations

import re
from datetime import date, datetime

from src.preprocessing.delivery_term import (
    DeliveryTerm,
    DeliveryTermKind,
    RelativeEvent,
    TimeUnit,
)


MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

UNIT_MAP: dict[str | None, TimeUnit] = {
    "рабочих": TimeUnit.WORKING,
    "рабочий": TimeUnit.WORKING,
    "календарных": TimeUnit.CALENDAR,
    "календарный": TimeUnit.CALENDAR,
    "банковских": TimeUnit.BANKING,
    "банковский": TimeUnit.BANKING,
    None: TimeUnit.CALENDAR,
}

_W = r"[\s\xa0\u2009\u202f]*"
_W1 = r"[\s\xa0\u2009\u202f]+"
_GAP = r"[\s\S]{0,80}?"
_GAP_SMALL = r"[\s\S]{0,20}?"

def extract_delivery_terms(text: str) -> list[DeliveryTerm]:
    """Извлекает все сроки поставки из текста."""
    terms: list[DeliveryTerm] = []
    terms.extend(_extract_fixed_dates(text))
    terms.extend(_extract_periods(text))
    terms.extend(_extract_relative(text))
    terms.extend(_extract_vague(text))
    return terms


# ---------- FIXED DATES ----------

_FIXED_DATE_PATTERNS = [
    # «не позднее 15.02.2026», «в срок до 15.02.2026»
    rf"(?:не{_W1}позднее|в{_W1}срок{_W1}до|в{_W1}срок){_W1}(?P<d>\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}})",
    # «15 февраля 2026 г.»
    rf"(?P<d>\d{{1,2}}{_W1}(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря){_W1}\d{{4}})",
]


def _extract_fixed_dates(text: str) -> list[DeliveryTerm]:
    terms: list[DeliveryTerm] = []
    seen: set[date] = set()
    for pattern in _FIXED_DATE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = m.group(0)
            d = _parse_date(m.group("d"))
            if d is None or d in seen:
                continue
            seen.add(d)
            terms.append(DeliveryTerm(
                kind=DeliveryTermKind.FIXED_DATE,
                raw_text=raw,
                fixed_date=d,
            ))
    return terms


# ---------- FIXED PERIODS ----------

_PERIOD_PATTERN = (
    rf"с{_W1}(?P<start>\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}}){_W1}по{_W1}"
    rf"(?P<end>\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}})"
)


def _extract_periods(text: str) -> list[DeliveryTerm]:
    terms: list[DeliveryTerm] = []
    for m in re.finditer(_PERIOD_PATTERN, text, flags=re.IGNORECASE):
        start = _parse_date(m.group("start"))
        end = _parse_date(m.group("end"))
        if start is None or end is None:
            continue
        terms.append(DeliveryTerm(
            kind=DeliveryTermKind.FIXED_PERIOD,
            raw_text=m.group(0),
            period_start=start,
            period_end=end,
        ))
    return terms


# ---------- RELATIVE ----------

_RELATIVE_PATTERNS: list[tuple[str, RelativeEvent]] = [
    # «в течение N [рабочих] дней … с момента оплаты»
    (
        rf"в{_W1}течение{_W1}(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"(?:с{_W1}момента|после|со{_W1}дня){_W1}(?:пред)?оплаты",
        RelativeEvent.PAYMENT_DATE,
    ),
    # «через N дней … после оплаты»
    (
        rf"через{_W1}(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"(?:с{_W1}момента|после|со{_W1}дня){_W1}(?:пред)?оплаты",
        RelativeEvent.PAYMENT_DATE,
    ),
    # «в течение N дней … с момента поступления денежных средств»
    (
        rf"в{_W1}течение{_W1}(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"(?:с{_W1}момента|после|со{_W1}дня){_W1}(?:поступления|зачисления){_W1}денежных{_W1}средств",
        RelativeEvent.PAYMENT_DATE,
    ),
    # «не позднее N дней … с момента поступления денежных средств»
    (
        rf"не{_W1}позднее{_W1}(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"(?:с{_W1}момента|после|со{_W1}дня){_W1}(?:поступления|зачисления){_W1}денежных{_W1}средств",
        RelativeEvent.PAYMENT_DATE,
    ),
    # «N дней … с даты поступления денежных средств»
    (
        rf"(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"с{_W1}даты{_W1}(?:поступления|зачисления){_W1}денежных{_W1}средств",
        RelativeEvent.PAYMENT_DATE,
    ),
    # «не позднее N дней … с момента оплаты»
    (
        rf"не{_W1}позднее{_W1}(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"(?:с{_W1}момента|после|со{_W1}дня){_W1}(?:пред)?оплаты",
        RelativeEvent.PAYMENT_DATE,
    ),
    # «N дней … с даты оплаты»
    (
        rf"(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"с{_W1}даты{_W1}(?:пред)?оплаты",
        RelativeEvent.PAYMENT_DATE,
    ),
    # «N дней … с даты выставления счёта»
    (
        rf"(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"с{_W1}даты{_W1}выставления{_W1}сч[её]та",
        RelativeEvent.INVOICE_DATE,
    ),
    # «в течение N дней … с момента выставления счёта»
    (
        rf"в{_W1}течение{_W1}(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"(?:с{_W1}момента|после){_W1}выставления{_W1}сч[её]та",
        RelativeEvent.INVOICE_DATE,
    ),
    # «N дней … с момента подписания договора»
    (
        rf"(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"с{_W1}(?:момента|даты){_W1}подписания{_W1}договора",
        RelativeEvent.CONTRACT_SIGNING_DATE,
    ),
    # «N дней … с момента подписания спецификации/заявки»
    (
        rf"(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"с{_W1}(?:момента|даты){_W1}подписания{_W1}(?:спецификации|заявки)",
        RelativeEvent.SPEC_SIGNING_DATE,
    ),
    # «N дней … с момента приёмки предыдущей партии»
    (
        rf"(?P<days>\d+){_GAP_SMALL}"
        rf"(?P<unit>рабочих|календарных|банковских)?{_GAP_SMALL}дн\w*"
        rf"{_GAP_SMALL}"
        rf"с{_W1}(?:момента|даты){_W1}(?:приемки|приёмки){_W1}(?:предыдущей{_W1})?партии",
        RelativeEvent.ACCEPTANCE_DATE,
    ),
]


def _extract_relative(text: str) -> list[DeliveryTerm]:
    terms: list[DeliveryTerm] = []
    matched_spans: list[tuple[int, int]] = []

    for pattern, event in _RELATIVE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if any(s <= m.start() and m.end() <= e for s, e in matched_spans):
                continue
            days = int(m.group("days"))
            unit = UNIT_MAP.get(m.group("unit"))
            terms.append(DeliveryTerm(
                kind=DeliveryTermKind.RELATIVE,
                raw_text=m.group(0),
                event=event,
                offset=days,
                unit=unit,
            ))
            matched_spans.append((m.start(), m.end()))

    return terms


# ---------- VAGUE ----------

_VAGUE_PATTERNS = [
    rf"в{_W1}разумн\w+{_W1}срок",
    rf"в{_W1}разумные{_W1}сроки",
    rf"по{_W1}мере{_W1}необходимости",
    rf"по{_W1}первому{_W1}требованию",
    rf"по{_W1}мере{_W1}готовности",
    rf"по{_W1}мере{_W1}поступления",
    rf"без{_W1}указания{_W1}конкретной{_W1}даты",
]


def _extract_vague(text: str) -> list[DeliveryTerm]:
    terms: list[DeliveryTerm] = []
    seen_spans: set[tuple[int, int]] = set()
    for pattern in _VAGUE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            key = (m.start(), m.end())
            if key in seen_spans:
                continue
            seen_spans.add(key)
            terms.append(DeliveryTerm(
                kind=DeliveryTermKind.VAGUE,
                raw_text=m.group(0),
            ))
    return terms


# ---------- PARSING ----------

def _parse_date(s: str) -> date | None:
    s = s.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    m = re.match(r"(\d{1,2})\s+([а-яё]+)\s+(\d{4})", s, flags=re.IGNORECASE)
    if m:
        day, month_name, year = m.groups()
        month = MONTHS_RU.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None
    return None