from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum


class TermKind(str, Enum):
    DELIVERY = "delivery"
    ACCEPTANCE = "acceptance"
    RENEWAL = "renewal"
    CONTRACT_DATE = "contract_date"
    END_DATE = "end_date" 


class TimeUnit(str, Enum):
    CALENDAR = "calendar"
    WORKING = "working"
    BANKING = "banking"
    MONTH = "month"


class DeliverySubKind(str, Enum):
    FIXED_DATE = "fixed_date"
    FIXED_PERIOD = "fixed_period"
    RELATIVE = "relative"
    VAGUE = "vague"
    ABSENT = "absent"


class DeliveryEvent(str, Enum):
    PAYMENT_DATE = "payment_date"
    INVOICE_DATE = "invoice_date"
    CONTRACT_SIGNING_DATE = "contract_signing_date"
    SPEC_SIGNING_DATE = "spec_signing_date"
    ACCEPTANCE_DATE = "acceptance_date"


class AcceptanceEvent(str, Enum):
    SUPPLIER_SIGNED = "supplier_signed"
    DELIVERY_DATE = "delivery_date"


class RenewalEvent(str, Enum):
    CONTRACT_END = "contract_end"


@dataclass
class ExtractedTerm:
    kind: TermKind
    raw_text: str = ""
    sub_kind: DeliverySubKind | None = None
    event: str | None = None
    offset: int | None = None
    unit: TimeUnit | None = None
    fixed_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None

    def is_resolvable(self) -> bool:
        if self.kind == TermKind.CONTRACT_DATE:
            return self.fixed_date is not None
        if self.kind != TermKind.DELIVERY:
            return False
        if self.sub_kind == DeliverySubKind.FIXED_DATE:
            return self.fixed_date is not None
        if self.sub_kind == DeliverySubKind.FIXED_PERIOD:
            return self.period_end is not None
        if self.sub_kind == DeliverySubKind.RELATIVE:
            return (self.event is not None
                    and self.offset is not None
                    and self.unit is not None)
        return False


    def to_export_dict(self) -> dict:
        base: dict = {"kind": self.kind.value}
        if self.kind == TermKind.DELIVERY and self.sub_kind:
            base["sub_kind"] = self.sub_kind.value

        if self.fixed_date:
            base["date"] = self.fixed_date.isoformat()
        if self.period_start and self.period_end:
            base["start"] = self.period_start.isoformat()
            base["end"] = self.period_end.isoformat()
        if self.event and self.offset is not None and self.unit:
            base["event"] = self.event
            base["offset"] = self.offset
            base["unit"] = self.unit.value
        return base

    @classmethod
    def from_export_dict(cls, data: dict) -> "ExtractedTerm | None":
        try:
            kind = TermKind(data.get("kind"))
        except (ValueError, TypeError):
            return None

        if kind == TermKind.CONTRACT_DATE:
            d = _parse_iso_date(data.get("date"))
            if d is None:
                return None
            return cls(kind=kind, raw_text="[confirmed by LLM]", fixed_date=d)

        if kind == TermKind.DELIVERY:
            sub_kind_str = data.get("sub_kind", "relative")
            try:
                sub_kind = DeliverySubKind(sub_kind_str)
            except (ValueError, TypeError):
                return None

            if sub_kind == DeliverySubKind.FIXED_DATE:
                d = _parse_iso_date(data.get("date"))
                if d is None:
                    return None
                return cls(
                    kind=kind,
                    raw_text="[confirmed by LLM]",
                    sub_kind=sub_kind,
                    fixed_date=d,
                )

            if sub_kind == DeliverySubKind.FIXED_PERIOD:
                start = _parse_iso_date(data.get("start"))
                end = _parse_iso_date(data.get("end"))
                if end is None:
                    return None
                return cls(
                    kind=kind,
                    raw_text="[confirmed by LLM]",
                    sub_kind=sub_kind,
                    period_start=start,
                    period_end=end,
                )

            try:
                offset = int(data["offset"])
                unit = TimeUnit(data["unit"])
                event = data["event"]
            except (KeyError, ValueError, TypeError):
                return None

            valid_events = {e.value for e in DeliveryEvent}
            if event not in valid_events:
                return None

            return cls(
                kind=kind,
                raw_text="[confirmed by LLM]",
                sub_kind=DeliverySubKind.RELATIVE,
                event=event,
                offset=offset,
                unit=unit,
            )

        try:
            offset = int(data["offset"])
            unit = TimeUnit(data["unit"])
            event = data["event"]
        except (KeyError, ValueError, TypeError):
            return None

        valid_events = {
            TermKind.ACCEPTANCE: {e.value for e in AcceptanceEvent},
            TermKind.RENEWAL: {e.value for e in RenewalEvent},
        }.get(kind, set())

        if event not in valid_events:
            return None

        return cls(
            kind=kind,
            raw_text="[confirmed by LLM]",
            event=event,
            offset=offset,
            unit=unit,
        )


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_relative_deadline(event_date: date, offset: int, unit: TimeUnit) -> date:
    if unit == TimeUnit.MONTH:
        return event_date + timedelta(days=30 * offset)
    if unit == TimeUnit.CALENDAR:
        return event_date + timedelta(days=offset)
    current = event_date
    added = 0
    while added < offset:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current