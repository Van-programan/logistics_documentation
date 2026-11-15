from __future__ import annotations

import re
from dataclasses import dataclass

from src.preprocessing.terms.base import (
    AcceptanceEvent,
    ExtractedTerm,
    TermKind,
    TimeUnit,
)


@dataclass
class AcceptanceTerm:
    event: AcceptanceEvent
    offset: int
    unit: TimeUnit
    raw_text: str

    def to_extracted(self) -> ExtractedTerm:
        return ExtractedTerm(
            kind=TermKind.ACCEPTANCE,
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
    None: TimeUnit.WORKING,
}

_DOC_ANCHOR = (
    rf"(?:УПД|"
    rf"универсальн\w+{_W1}передаточн\w+{_W1}документ|"
    rf"товарн\w+{_W1}накладн\w+|"
    rf"товарно-?транспортн\w+{_W1}накладн\w+|"
    rf"накладн\w+|"
    rf"счет-?фактур\w+|счёт-?фактур\w+|"
    rf"акт{_W1}приемки|акт{_W1}приёмки)"
)


_ACCEPTANCE_PATTERNS: list[tuple[str, AcceptanceEvent]] = [
    (
        rf"(?:подписать|подписывает|обязан{_W1}подписать)"
        rf"{_GAP}{_DOC_ANCHOR}"
        rf"{_GAP}(?:в{_W1}течение|не{_W1}позднее|в{_W1}срок{_W1}до)"
        rf"{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>рабочих|календарных)?{_W1}дн\w*",
        AcceptanceEvent.DELIVERY_DATE,
    ),
    (
        rf"{_DOC_ANCHOR}"
        rf"{_GAP}(?:подписать|подписывается|подписывает|оформляется{_W1}подписанием)"
        rf"{_GAP}(?:в{_W1}течение|не{_W1}позднее|в{_W1}срок{_W1}до)"
        rf"{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>рабочих|календарных)?{_W1}дн\w*",
        AcceptanceEvent.DELIVERY_DATE,
    ),
    (
        rf"в{_W1}течение{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>рабочих|календарных)?{_W1}дн\w*"
        rf"{_GAP}(?:вернуть|возвратить|направить|передать){_GAP}"
        rf"(?:подписанн\w+{_W1})?{_DOC_ANCHOR}",
        AcceptanceEvent.SUPPLIER_SIGNED,
    ),
    (
        rf"(?:УПД|универсальн\w+{_W1}передаточн\w+{_W1}документ|"
        rf"товарн\w+{_W1}накладн\w+|товарно-?транспортн\w+{_W1}накладн\w+|накладн\w+)"
        rf"{_GAP}(?:от{_W1}Поставщика|подписанн\w+{_W1}Поставщиком|"
        rf"полученн\w+{_W1}от{_W1}Поставщика)"
        rf"{_GAP}(?:в{_W1}течение|не{_W1}позднее){_W1}(?P<days>\d+)"
        rf"{_W1}(?:\([^)]+\){_W1})?(?P<unit>рабочих|календарных)?{_W1}дн\w*"
        rf"{_GAP}(?:с{_W1}момента|после|с{_W1}даты){_W1}(?:получения|поступления|поставки)",
        AcceptanceEvent.SUPPLIER_SIGNED,
    ),
    (
        rf"срок{_W1}подписания{_GAP}{_DOC_ANCHOR}"
        rf"{_GAP}не{_W1}должен{_W1}превышать{_W1}(?P<days>\d+)"
        rf"{_W1}(?:\([^)]+\){_W1})?(?P<unit>рабочих|календарных)?{_W1}дн\w*",
        AcceptanceEvent.DELIVERY_DATE,
    ),
    (
        rf"в{_W1}срок{_W1}не{_W1}позднее{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>рабочих|календарных)?{_W1}дн\w*"
        rf"{_GAP}(?:с{_W1}даты|с{_W1}момента|после){_W1}получения{_W1}"
        rf"(?:Продукции|Товара){_W1}(?:Покупателем|Грузополучателем)"
        rf"{_GAP}(?:подписать|подписывает|принять|УПД|накладн\w+)",
        AcceptanceEvent.DELIVERY_DATE,
    ),
    (
        rf"(?:принять|принимает|обязан{_W1}принять){_GAP}"
        rf"(?:Товар|Продукцию)"
        rf"{_GAP}(?:в{_W1}течение|не{_W1}позднее){_W1}(?P<days>\d+)"
        rf"{_W1}(?:\([^)]+\){_W1})?(?P<unit>рабочих|календарных)?{_W1}дн\w*",
        AcceptanceEvent.DELIVERY_DATE,
    ),
    (
        rf"акт{_W1}(?:приемки|приёмки)"
        rf"{_GAP}(?:подписать|подписывается|оформляется)"
        rf"{_GAP}(?:в{_W1}течение|не{_W1}позднее){_W1}(?P<days>\d+)"
        rf"{_W1}(?:\([^)]+\){_W1})?(?P<unit>рабочих|календарных)?{_W1}дн\w*",
        AcceptanceEvent.DELIVERY_DATE,
    ),
    (
        rf"в{_W1}течение{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>рабочих|календарных)?{_W1}дн\w*"
        rf"{_GAP}(?:с{_W1}момента|после|с{_W1}даты){_W1}"
        rf"(?:поставки|получения|поступления){_GAP}"
        rf"(?:подписать|подписывает|подписывается|оформляет)"
        rf"{_GAP}{_DOC_ANCHOR}",
        AcceptanceEvent.DELIVERY_DATE,
    ),
    (
        rf"в{_W1}течение{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>рабочих|календарных)?{_W1}дн\w*"
        rf"{_GAP}(?:обеспечить|осуществить){_W1}(?:возврат|возвращение)"
        rf"{_GAP}(?:Поставщику{_W1})?(?:одного{_W1})?(?:подписанн\w+{_W1})?экземпляра",
        AcceptanceEvent.SUPPLIER_SIGNED,
    ),
    (
        rf"в{_W1}срок{_W1}не{_W1}позднее{_W1}(?P<days>\d+){_W1}(?:\([^)]+\){_W1})?"
        rf"(?P<unit>рабочих|календарных)?{_W1}дн\w*"
        rf"{_GAP}(?:направить|направляется|передать|передается|передаётся)"
        rf"{_GAP}(?:УПД|универсальн\w+|товарн\w+{_W1}накладн\w+|"
        rf"товарно-?транспортн\w+{_W1}накладн\w+|экземпляр|документ)",
        AcceptanceEvent.DELIVERY_DATE,
    ),
]


_FALSE_POSITIVE_KEYWORDS = [
    "претензи", "уведомить", "уведомлени", "возражени",
    "отказ", "требовани", "недостатк", "оплат",
    "подтверждени", "согласовани",
    "вызвать", "вызов", "акт об установленном", "неявки", "представител",
    "передать", "копию акта", "оригиналы", "письменной претензией",
    "предъявить", "предъявляются", "акт о браке", "акта о",
]

def extract_acceptance_terms(text: str) -> list[AcceptanceTerm]:
    terms: list[AcceptanceTerm] = []
    matched: list[tuple[int, int]] = []

    for pattern, event in _ACCEPTANCE_PATTERNS:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            if any(s <= m.start() and m.end() <= e for s, e in matched):
                continue

            raw_lower = m.group(0).lower()
            if any(kw in raw_lower for kw in _FALSE_POSITIVE_KEYWORDS):
                continue

            days = int(m.group("days"))
            if days > 90:
                continue

            unit_str = m.group("unit")
            unit = _UNIT_MAP.get(unit_str) if unit_str else TimeUnit.WORKING

            terms.append(AcceptanceTerm(
                event=event,
                offset=days,
                unit=unit,
                raw_text=m.group(0),
            ))
            matched.append((m.start(), m.end()))

    return terms