from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum


class DeliveryTermKind(str, Enum):
    FIXED_DATE = "fixed_date"
    FIXED_PERIOD = "fixed_period"
    RELATIVE = "relative"
    VAGUE = "vague"
    ABSENT = "absent"


class RelativeEvent(str, Enum):
    PAYMENT_DATE = "payment_date"
    INVOICE_DATE = "invoice_date"
    CONTRACT_SIGNING_DATE = "contract_signing_date"
    SPEC_SIGNING_DATE = "spec_signing_date"
    ACCEPTANCE_DATE = "acceptance_date"


class TimeUnit(str, Enum):
    CALENDAR = "calendar"
    WORKING = "working"
    BANKING = "banking"
    MONTH = "month"


@dataclass
class DeliveryTerm:
    kind: DeliveryTermKind
    raw_text: str

    fixed_date: date | None = None

    period_start: date | None = None
    period_end: date | None = None

    event: RelativeEvent | None = None
    offset: int | None = None
    unit: TimeUnit | None = None

    context: str | None = None

    def is_resolvable(self) -> bool:
        if self.kind == DeliveryTermKind.FIXED_DATE:
            return self.fixed_date is not None
        if self.kind == DeliveryTermKind.FIXED_PERIOD:
            return self.period_end is not None
        if self.kind == DeliveryTermKind.RELATIVE:
            return self.event is not None and self.offset is not None and self.unit is not None
        return False

    def resolve_deadline(
        self,
        event_dates: dict[RelativeEvent, date],
    ) -> date | None:
        if self.kind == DeliveryTermKind.FIXED_DATE:
            return self.fixed_date
        if self.kind == DeliveryTermKind.FIXED_PERIOD:
            return self.period_end
        if self.kind != DeliveryTermKind.RELATIVE:
            return None
        if self.event is None or self.offset is None or self.unit is None:
            return None

        event_date = event_dates.get(self.event)
        if event_date is None:
            return None

        if self.unit == TimeUnit.MONTH:
            return event_date + timedelta(days=30 * self.offset)
        if self.unit == TimeUnit.CALENDAR:
            return event_date + timedelta(days=self.offset)

        current = event_date
        added = 0
        while added < self.offset:
            current += timedelta(days=1)
            if current.weekday() < 5:
                added += 1
        return current


    def to_export_dict(self) -> dict:
        if self.kind == DeliveryTermKind.RELATIVE:
            return {
                "kind": "relative",
                "event": self.event.value if self.event else None,
                "offset": self.offset,
                "unit": self.unit.value if self.unit else None,
            }
        if self.kind == DeliveryTermKind.FIXED_DATE:
            return {
                "kind": "fixed_date",
                "date": self.fixed_date.isoformat() if self.fixed_date else None,
            }
        if self.kind == DeliveryTermKind.FIXED_PERIOD:
            return {
                "kind": "fixed_period",
                "start": self.period_start.isoformat() if self.period_start else None,
                "end": self.period_end.isoformat() if self.period_end else None,
            }
        if self.kind == DeliveryTermKind.VAGUE:
            return {"kind": "vague"}
        return {"kind": "absent"}

    @classmethod
    def from_export_dict(cls, data: dict) -> "DeliveryTerm | None":
        kind = data.get("kind")

        if kind == "relative":
            try:
                return cls(
                    kind=DeliveryTermKind.RELATIVE,
                    raw_text="[confirmed by LLM]",
                    event=RelativeEvent(data["event"]),
                    offset=int(data["offset"]),
                    unit=TimeUnit(data["unit"]),
                )
            except (KeyError, TypeError, ValueError):
                return None

        if kind == "fixed_date":
            d = _parse_iso_date(data.get("date"))
            if d is None:
                return None
            return cls(
                kind=DeliveryTermKind.FIXED_DATE,
                raw_text="[confirmed by LLM]",
                fixed_date=d,
            )

        if kind == "fixed_period":
            start = _parse_iso_date(data.get("start"))
            end = _parse_iso_date(data.get("end"))
            if end is None:
                return None
            return cls(
                kind=DeliveryTermKind.FIXED_PERIOD,
                raw_text="[confirmed by LLM]",
                period_start=start,
                period_end=end,
            )

        if kind == "vague":
            return cls(kind=DeliveryTermKind.VAGUE, raw_text="[confirmed by LLM]")

        return None


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None