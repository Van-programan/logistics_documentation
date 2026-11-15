from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from src.preprocessing.terms.base import ExtractedTerm, TermKind


@dataclass
class ContractDateTerm:
    fixed_date: date
    raw_text: str

    def to_extracted(self) -> ExtractedTerm:
        return ExtractedTerm(
            kind=TermKind.CONTRACT_DATE,
            raw_text=self.raw_text,
            fixed_date=self.fixed_date,
        )


MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
    "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}


_CONTRACT_DATE_PATTERNS = [
    r"(?:Договор|ДОГОВОР)\s*№?\s*\d+\s*от\s*(?P<d>\d{1,2}[./]\d{1,2}[./]\d{2,4})",
    r"(?:г\.\s*[А-ЯЁ][а-яё]+[\s,]+)?[«\"]?(?P<d>\d{1,2})[»\"]?\s+"
    r"(?P<month>января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
    r"(?P<year>\d{4})",
]


def extract_contract_date(text: str) -> list[ContractDateTerm]:
    head = text[:1000]

    for pattern in _CONTRACT_DATE_PATTERNS:
        m = re.search(pattern, head, flags=re.IGNORECASE)
        if not m:
            continue

        if m.groupdict().get("month"):
            day = int(m.group("d"))
            month = MONTHS_RU.get(m.group("month").lower())
            year = int(m.group("year"))
            if not month:
                continue
            try:
                d = date(year, month, day)
            except ValueError:
                continue
        else:
            d = _parse_date(m.group("d"))
            if d is None:
                continue

        return [ContractDateTerm(fixed_date=d, raw_text=m.group(0))]

    return []


def _parse_date(s: str) -> date | None:
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None