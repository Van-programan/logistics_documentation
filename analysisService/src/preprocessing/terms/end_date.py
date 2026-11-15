from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from src.preprocessing.terms.base import (
    ExtractedTerm,
    TermKind,
    TimeUnit,
)


@dataclass
class EndDateTerm:
    fixed_date: date | None = None
    offset: int | None = None
    unit: TimeUnit | None = None
    raw_text: str = ""

    def to_extracted(self) -> ExtractedTerm:
        return ExtractedTerm(
            kind=TermKind.END_DATE,
            raw_text=self.raw_text,
            fixed_date=self.fixed_date,
            offset=self.offset,
            unit=self.unit,
            event="contract_signing_date" if self.offset else None,
        )


MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

_W = r"[\s\xa0\u2009\u202f]*"
_W1 = r"[\s\xa0\u2009\u202f]+"
_GAP = r"[\s\S]{0,200}?"


_FIXED_DATE_PATTERNS = [
    (
        rf"(?:действует|действительн\w+|заключен\w+){_GAP}"
        rf"(?:до|по){_W1}"
        rf"[«\"]?(?P<d>\d{{1,2}})[»\"]?{_W1}"
        rf"(?P<month>января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря){_W1}"
        rf"(?P<year>\d{{4}})"
    ),
    (
        rf"(?:действует|действительн\w+|заключен\w+){_GAP}"
        rf"(?:до|по){_W1}"
        rf"(?P<d>\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}})"
    ),
    (
        rf"срок{_W1}действия{_GAP}"
        rf"(?:до|по){_W1}"
        rf"(?P<d>\d{{1,2}}[./]\d{{1,2}}[./]\d{{2,4}})"
    ),
]


_DAYS_WORDS = {
    "один": 1, "одного": 1, "1": 1,
    "два": 2, "двух": 2, "2": 2,
    "три": 3, "трех": 3, "3": 3,
    "четыре": 4, "четырех": 4, "4": 4,
    "пять": 5, "пяти": 5, "5": 5,
}

_RELATIVE_PATTERNS = [
    (
        rf"(?:срок{_W1}действия){_GAP}"
        rf"(?:устанавливается|составляет|равен){_W1}"
        rf"(?:в|на)?{_W1}(?P<count>один|одного|1|два|двух|2|три|трех|3|четыре|четырех|4|пять|пяти|5)"
        rf"{_W1}(?P<unit>год(?:а)?|лет|месяц(?:ев|а)?)"
    ),
    (
        rf"(?:действует|заключен){_GAP}"
        rf"в{_W1}течение{_W1}(?P<count>\d+)"
        rf"{_W1}(?P<unit>год(?:а)?|лет|месяц(?:ев|а)?)"
    ),
    (
        rf"(?:заключен|действует){_W1}на{_W1}срок{_W1}"
        rf"(?P<count>\d+|один|два|три){_W1}"
        rf"(?P<unit>год(?:а)?|лет|месяц(?:ев|а)?)"
    ),
]


def extract_end_date(text: str) -> list[EndDateTerm]:
    for pattern in _FIXED_DATE_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue

        gd = m.groupdict()
        if "month" in gd and gd.get("month"):
            day = int(gd["d"])
            month = MONTHS_RU.get(gd["month"].lower())
            year = int(gd["year"])
            if not month:
                continue
            try:
                d = date(year, month, day)
            except ValueError:
                continue
        else:
            d = _parse_date(gd["d"])
            if d is None:
                continue

        return [EndDateTerm(fixed_date=d, raw_text=m.group(0))]

    for pattern in _RELATIVE_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            continue

        count_str = m.group("count").lower()
        count = int(count_str) if count_str.isdigit() else _DAYS_WORDS.get(count_str, 0)
        if count <= 0 or count > 100:
            continue

        unit_str = m.group("unit").lower()
        if unit_str.startswith("год") or unit_str == "лет":
            offset = count * 12
            unit = TimeUnit.MONTH
        else:
            offset = count
            unit = TimeUnit.MONTH

        return [EndDateTerm(
            offset=offset,
            unit=unit,
            raw_text=m.group(0),
        )]

    return []


def _parse_date(s: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None