from __future__ import annotations

import re
from dataclasses import dataclass

from src.preprocessing.terms.base import (
    ExtractedTerm,
    RenewalEvent,
    TermKind,
    TimeUnit,
)


@dataclass
class RenewalTerm:
    event: RenewalEvent
    offset: int
    unit: TimeUnit
    raw_text: str

    def to_extracted(self) -> ExtractedTerm:
        return ExtractedTerm(
            kind=TermKind.RENEWAL,
            raw_text=self.raw_text,
            event=self.event.value,
            offset=self.offset,
            unit=self.unit,
        )


_W1 = r"[\s\xa0\u2009\u202f]+"
_GAP = r"[\s\S]{0,120}?"

_UNIT_MAP: dict[str | None, TimeUnit] = {
    "рабочих": TimeUnit.WORKING,
    "рабочий": TimeUnit.WORKING,
    "календарных": TimeUnit.CALENDAR,
    "календарный": TimeUnit.CALENDAR,
    "месяц": TimeUnit.MONTH,
    "месяцев": TimeUnit.MONTH,
    "месяца": TimeUnit.MONTH,
    "год": TimeUnit.MONTH,
    "года": TimeUnit.MONTH,
    None: TimeUnit.CALENDAR,
}


_RENEWAL_PATTERNS: list[tuple[str, TimeUnit]] = [
    (
        rf"за{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>календарных|рабочих|месяц(?:ев|а)?)?"
        rf"(?:{_W1}дн\w*)?{_W1}до{_W1}(?:истечения|окончания)"
        rf"(?:{_W1}(?:срока{_W1})?(?:действия|договора))?",
        TimeUnit.CALENDAR,
    ),
    (
        rf"за{_W1}(?P<days>один|одного|1|два|двух|2|три|трех|3|четыре|четырех|4|"
        rf"пять|пяти|5|шесть|шести|6|семь|семи|7|восемь|восьми|8|"
        rf"девять|девяти|9|десять|десяти|10|одиннадцать|двенадцать)"
        rf"{_W1}(?P<unit>месяц(?:ев|а)?|год(?:а)?)"
        rf"{_W1}до{_W1}(?:окончания|истечения)",
        TimeUnit.MONTH,
    ),
    (
        rf"(?:уведомить|уведомит|уведомлять|уведомляет){_GAP}"
        rf"за{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>календарных|рабочих|месяц(?:ев|а)?)?"
        rf"(?:{_W1}дн\w*)?{_W1}до{_W1}(?:истечения|окончания)",
        TimeUnit.CALENDAR,
    ),
    (
        rf"не{_W1}позднее{_W1}чем{_W1}за{_W1}(?P<days>\d+)"
        rf"{_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>календарных|рабочих|месяц(?:ев|а)?)?"
        rf"(?:{_W1}дн\w*)?{_W1}до{_W1}(?:истечения|окончания)",
        TimeUnit.CALENDAR,
    ),
]


_DAYS_WORDS = {
    "один": 1, "одного": 1, "два": 2, "двух": 2,
    "три": 3, "трех": 3, "четыре": 4, "четырех": 4,
    "пять": 5, "пяти": 5, "шесть": 6, "шести": 6,
    "семь": 7, "семи": 7, "восемь": 8, "восьми": 8,
    "девять": 9, "девяти": 9, "десять": 10, "десяти": 10,
}


def extract_renewal_terms(text: str) -> list[RenewalTerm]:
    terms: list[RenewalTerm] = []
    matched: list[tuple[int, int]] = []

    for pattern, default_unit in _RENEWAL_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if any(s <= m.start() and m.end() <= e for s, e in matched):
                continue

            days_raw = m.group("days")
            if days_raw.isdigit():
                days = int(days_raw)
            else:
                days = _DAYS_WORDS.get(days_raw.lower(), 0)

            if days <= 0 or days > 365:
                continue

            unit_str = m.group("unit") if "unit" in m.groupdict() else None
            unit = _UNIT_MAP.get(unit_str) if unit_str else default_unit

            if unit_str and unit_str.lower() in ("год", "года"):
                days = 12
                unit = TimeUnit.MONTH

            terms.append(RenewalTerm(
                event=RenewalEvent.CONTRACT_END,
                offset=days,
                unit=unit,
                raw_text=m.group(0),
            ))
            matched.append((m.start(), m.end()))

    return terms