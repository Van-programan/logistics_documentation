from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum


class DeliveryTermKind(str, Enum):
    FIXED_DATE = "fixed_date"      # «не позднее 15.02.2026»
    FIXED_PERIOD = "fixed_period"  # «с 01.03.2026 по 15.03.2026»
    RELATIVE = "relative"          # «10 рабочих дней с момента оплаты»
    VAGUE = "vague"                # «в разумный срок» — данных нет
    ABSENT = "absent"              # срок не указан вообще


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
    """Один срок поставки, извлечённый из текста.

    На один фрагмент может приходиться несколько сроков
    (разные партии, способы доставки и т.д.).
    """
    kind: DeliveryTermKind
    raw_text: str

    # FIXED_DATE
    fixed_date: date | None = None

    # FIXED_PERIOD
    period_start: date | None = None
    period_end: date | None = None

    # RELATIVE
    event: RelativeEvent | None = None
    offset: int | None = None
    unit: TimeUnit | None = None

    # Контекст (для будущего): «самовывоз» / «доставка поставщиком» / «партия №1»
    context: str | None = None

    def is_resolvable(self) -> bool:
        """Можно ли вычислить дату дедлайна без ввода юриста."""
        if self.kind == DeliveryTermKind.FIXED_DATE:
            return self.fixed_date is not None
        if self.kind == DeliveryTermKind.FIXED_PERIOD:
            return self.period_end is not None
        return False

    def resolve_deadline(
        self,
        event_dates: dict[RelativeEvent, date],
    ) -> date | None:
        """Вычисляет дату дедлайна, если известны даты событий.

        Для production: праздники РФ (библиотека `holidays`) и
        точные месяцы (dateutil.relativedelta).
        """
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

        # WORKING / BANKING — пропускаем субботу и воскресенье
        current = event_date
        added = 0
        while added < self.offset:
            current += timedelta(days=1)
            if current.weekday() < 5:
                added += 1
        return current