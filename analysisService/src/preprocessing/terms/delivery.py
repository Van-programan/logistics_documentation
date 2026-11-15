from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from src.preprocessing.terms.base import DeliveryEvent, DeliverySubKind, ExtractedTerm, TermKind, TimeUnit


@dataclass
class DeliveryTerm:
    kind: DeliverySubKind
    raw_text: str

    fixed_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None

    event: DeliveryEvent | None = None
    offset: int | None = None
    unit: TimeUnit | None = None

    context: str | None = None

    def to_extracted(self) -> ExtractedTerm:
        return ExtractedTerm(
            kind=TermKind.DELIVERY,
            raw_text=self.raw_text,
            sub_kind=self.kind,
            event=self.event.value if self.event else None,
            offset=self.offset,
            unit=self.unit,
            fixed_date=self.fixed_date,
            period_start=self.period_start,
            period_end=self.period_end,
        )

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

_UNIT_MAP: dict[str | None, TimeUnit] = {
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
_GAP_NUM_UNIT = r"(?:(?!%|(?:\d+\s*дн))[\s\S]){0,30}?"
_DAYS_PREFIX = rf"(?:в{_W1}течение|не{_W1}позднее|в{_W1}срок|через)"
_UNIT_GROUP = rf"(?:(?P<unit>рабочих|календарных|банковских){_W1})?"
_UNIT_FROM_RAW_RE = re.compile(
    r"\b(рабочих|рабочий|календарных|календарный|банковских|банковский)\b",
    flags=re.IGNORECASE,
)


def _unit_from_raw(raw: str, fallback: TimeUnit) -> TimeUnit:
    m = _UNIT_FROM_RAW_RE.search(raw)
    if m:
        return _UNIT_MAP.get(m.group(1).lower(), fallback)
    return fallback


def _is_suspicious_term(m: re.Match, days: int) -> bool:
    if days > 365:
        return True
    try:
        prefix = m.group(0)[: m.start("days") - m.start()]
    except (IndexError, ValueError):
        prefix = ""
    if "%" in prefix:
        return True
    if m.group("unit") is None and days > 60:
        return True
    return False


def extract_delivery_terms(text: str) -> list[DeliveryTerm]:
    terms: list[DeliveryTerm] = []
    terms.extend(_extract_fixed_dates(text))
    terms.extend(_extract_periods(text))
    terms.extend(_extract_relative(text))
    terms.extend(_extract_vague(text))
    return terms


_FIXED_DATE_PATTERNS = [
    rf"(?:не{_W1}позднее|в{_W1}срок{_W1}до|в{_W1}срок){_W1}(?P<d>\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}})",
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
                kind=DeliverySubKind.FIXED_DATE,
                raw_text=raw,
                fixed_date=d,
            ))
    return terms


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
            kind=DeliverySubKind.FIXED_PERIOD,
            raw_text=m.group(0),
            period_start=start,
            period_end=end,
        ))
    return terms


_DAYS_UNIT = (
    rf"{_DAYS_PREFIX}{_W1}(?P<days>\d+){_GAP_NUM_UNIT}"
    rf"{_UNIT_GROUP}"
    rf"дн\w*"
)

_RELATIVE_PATTERNS: list[tuple[str, DeliveryEvent]] = [
    (rf"{_DAYS_UNIT}{_GAP_SMALL}(?:с{_W1}момента|после|со{_W1}дня){_W1}(?:пред)?оплаты",
     DeliveryEvent.PAYMENT_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}(?:с{_W1}момента|после|со{_W1}дня){_W1}(?:поступления|зачисления){_W1}денежных{_W1}средств",
     DeliveryEvent.PAYMENT_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}с{_W1}даты{_W1}(?:поступления|зачисления){_W1}денежных{_W1}средств",
     DeliveryEvent.PAYMENT_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}с{_W1}даты{_W1}(?:пред)?оплаты",
     DeliveryEvent.PAYMENT_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}с{_W1}даты{_W1}выставления{_W1}сч[её]та",
     DeliveryEvent.INVOICE_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}(?:с{_W1}момента|после){_W1}выставления{_W1}сч[её]та",
     DeliveryEvent.INVOICE_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}с{_W1}(?:момента|даты){_W1}подписания{_W1}договора",
     DeliveryEvent.CONTRACT_SIGNING_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}с{_W1}(?:момента|даты){_W1}подписания{_W1}(?:спецификации|заявки)",
     DeliveryEvent.SPEC_SIGNING_DATE),
    (rf"{_DAYS_UNIT}{_GAP_SMALL}с{_W1}(?:момента|даты){_W1}(?:приемки|приёмки){_W1}(?:предыдущей{_W1})?партии",
     DeliveryEvent.ACCEPTANCE_DATE),
]


def _extract_relative(text: str) -> list[DeliveryTerm]:
    terms: list[DeliveryTerm] = []
    matched_spans: list[tuple[int, int]] = []

    for pattern, event in _RELATIVE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if any(s <= m.start() and m.end() <= e for s, e in matched_spans):
                continue
            days = int(m.group("days"))
            if _is_suspicious_term(m, days):
                continue
            raw = m.group(0)
            fallback = _UNIT_MAP.get(m.group("unit"), TimeUnit.CALENDAR)
            unit = _unit_from_raw(raw, fallback) if m.group("unit") is None else fallback

            terms.append(DeliveryTerm(
                kind=DeliverySubKind.RELATIVE,
                raw_text=raw,
                event=event,
                offset=days,
                unit=unit,
            ))
            matched_spans.append((m.start(), m.end()))

    return terms


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
                kind=DeliverySubKind.VAGUE,
                raw_text=m.group(0),
            ))
    return terms


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