from __future__ import annotations

import json

from src.preprocessing.models import PreprocessingResult
from src.preprocessing.delivery_term import DeliveryTermKind

RISK_SPECS: dict[str, dict] = {
    "delivery_term_undefined": {
        "title": "Неопределённый срок поставки",
        "high": "Срок отсутствует ИЛИ размыт ('в разумный срок', 'по заявке' без механизма).",
        "medium": "Срок привязан к событию, но без числа дней ИЛИ противоречив.",
        "absence_policy": "Нет кандидатов → вернуть 'HIGH' (срок не определён).",
    },
    "acceptance_missing": {
        "title": "Отсутствие порядка приёмки",
        "high": "Порядок приёмки НЕ описан И/ИЛИ НЕ указаны сроки подписания УПД/накладной.",
        "medium": "Приёмка упомянута, но сроки размыты или нет срока для скрытых недостатков.",
        "absence_policy": "Нет кандидатов → вернуть 'HIGH'.",
    },
    "liability_imbalance": {
        "title": "Неравенство ответственности сторон",
        "high": "Неустойка одной стороны в 2+ раза выше ИЛИ у одной стороны ответственности нет.",
        "medium": "Размеры различаются в 1.5–2 раза ИЛИ формулировки асимметричны без явного перекоса.",
        "absence_policy": "Нет кандидатов → вернуть 'MEDIUM' (ответственность не урегулирована).",
    },
    "quality_unconfirmed": {
        "title": "Неподтверждённое качество товара",
        "high": "НЕТ ссылок на ГОСТ/ТУ/сертификаты ИЛИ требования размыты.",
        "medium": "Ссылки на стандарты есть, но неполные (ГОСТ без номера, 'сертификат' без органа).",
        "absence_policy": "Нет кандидатов → вернуть 'HIGH'.",
    },
    "currency_risk": {
        "title": "Валютный риск",
        "high": "Цена в валюте/у.е. БЕЗ фиксации курса на дату платежа.",
        "medium": "Цена в валюте, но курс зафиксирован на конкретную дату.",
        "absence_policy": "Нет кандидатов → 'NONE' (риска нет).",
    },
    "item_name_vague": {
        "title": "Некорректное наименование товара",
        "high": "Товар описан ТОЛЬКО общими словами ('продукты', 'мебель') БЕЗ артикула/модели/марки.",
        "medium": "Наименование есть, но неполное (есть модель, нет артикула/марки).",
        "absence_policy": "Нет кандидатов → вернуть 'HIGH'.",
    },
    "quantity_undefined": {
        "title": "Неопределённое количество товара",
        "high": "Количество НЕ указано ИЛИ размыто ('по заявке') БЕЗ механизма.",
        "medium": "Количество приблизительное ('около', 'не более') с механизмом уточнения.",
        "absence_policy": "Нет кандидатов → вернуть 'HIGH'.",
    },
    "schedule_missing": {
        "title": "Отсутствие графика поставки",
        "high": "Поставка партиями, но НЕТ периодов/сроков каждой партии.",
        "medium": "График упомянут, но не детализирован (только квартал без разбивки).",
        "absence_policy": "Нет кандидатов → вернуть 'MEDIUM' (график не урегулирован).",
    },
    "auto_renewal": {
        "title": "Автоматическая пролонгация",
        "high": "Автопролонгация, срок уведомления < 30 дней ИЛИ отсутствует.",
        "medium": "Автопролонгация, срок уведомления 30+ дней.",
        "absence_policy": "Нет кандидатов → 'NONE' (риска нет).",
    },
}

_RESPONSE_FORMAT = r'''
{
  "risks": [
    {
      "risk_type": "<строка из справочника>",
      "severity": "HIGH" | "MEDIUM",
      "confidence": "HIGH" | "MEDIUM" | "LOW",
      "description": "<краткое описание>",
      "recommendation": "<рекомендация>",
      "fragments": [
        {"candidate_index": <int>, "quote": "<дословный фрагмент>"}
      ]
    }
  ],
  "contract_delivery_terms": [
    {"kind": "relative", "event": "payment_date" | "invoice_date" | "contract_signing_date" | "spec_signing_date" | "acceptance_date", "offset": <int>, "unit": "working" | "calendar" | "banking"},
    {"kind": "fixed_date", "date": "YYYY-MM-DD"},
    {"kind": "fixed_period", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
  ]
}
'''

_EXAMPLE_1 = r'''
{
  "risks": [
    {
      "risk_type": "delivery_term_undefined",
      "severity": "HIGH",
      "confidence": "HIGH",
      "description": "Срок поставки указан размыто",
      "recommendation": "Заменить на конкретный срок",
      "fragments": [{"candidate_index": 0, "quote": "в разумный срок"}]
    }
  ],
  "contract_delivery_terms": []
}
'''

_EXAMPLE_2 = r'''
{
  "risks": [],
  "contract_delivery_terms": [
    {"event": "payment_date", "offset": 10, "unit": "working"}
  ]
}
'''

_EXAMPLE_3 = r'''
{
  "risks": [
    {
      "risk_type": "delivery_term_undefined",
      "severity": "HIGH",
      "confidence": "HIGH",
      "description": "Срок привязан к оплате, но не указано число дней",
      "recommendation": "Указать конкретный срок: N рабочих/календарных дней с момента оплаты",
      "fragments": [{"candidate_index": 0, "quote": "после оплаты счёта"}]
    }
  ],
  "contract_delivery_terms": []
}
'''

_EXAMPLE_4 = r'''
{
  "risks": [],
  "contract_delivery_terms": [
    {"kind": "fixed_date", "date": "2026-02-15"}
  ]
}
'''

def build_system_prompt() -> str:
    risk_lines = []
    for risk_type, spec in RISK_SPECS.items():
        risk_lines.append(
            f"\n### {risk_type} — {spec['title']}\n"
            f"  HIGH: {spec['high']}\n"
            f"  MEDIUM: {spec['medium']}\n"
            f"  Без кандидатов: {spec['absence_policy']}"
        )

    risks_block = "\n".join(risk_lines)

    return (
        "Ты — юрист-аналитик, проверяющий договоры поставки на риски.\n"
        "Тебе дан набор кандидатов по КАЖДОМУ типу риска. Верни СТРОГО JSON.\n"
        "\n## КРИТИЧЕСКИЕ ПРАВИЛА\n\n"
        "1. **Цитата.** Для каждого подтверждённого риска найди ТОЧНЫЙ фрагмент "
        "ВНУТРИ кандидата и верни его **дословно** в поле `quote`. "
        "Скопируй символ в символ из `TEXT` кандидата — не перефразируй, "
        "не сокращай, не исправляй опечатки.\n\n"
        "2. **Absence-риски.** Если для `risk_type` кандидатов НЕТ — следуй "
        "`absence_policy`: HIGH → severity=HIGH, `fragments=[]`; "
        "MEDIUM → severity=MEDIUM, `fragments=[]`; "
        "NONE → НЕ включать риск в ответ.\n\n"
        "3. **Confidence.** HIGH — фрагмент явно подтверждает риск; "
        "MEDIUM — содержит намёк, требует интерпретации; "
        "LOW — косвенный (→ PENDING_CONFIRMATION, юрист проверит).\n\n"
        "4. **has_negative_context.** `True` — рядом есть маркер определённости "
        "(дата, число дней, фиксированный курс) — снижает вероятность риска. "
        "`False` — маркеров нет.\n\n"
        "5. **Сроки поставки (delivery_terms).** "
        "`fixed_date` / `fixed_period` — риск НИЗКИЙ, подтверди. "
        "`relative` — риск СРЕДНИЙ, подтверди (event, offset, unit). "
        "`vague` — риск ВЫСОКИЙ, верни `[]` (мониторинг невозможен). "
        "Если regex ошибся (поймал НДС/срок оплаты) — верни исправленную версию. "
        "Если срок не относится к поставке — не включай.\n\n"
        "6. **Мульти-риск.** Один кандидат может подтверждать НЕСКОЛЬКО типов рисков (это нужно "
        "учитывать и запоминать контекст) — верни отдельный объект для каждого `risk_type`.\n\n"
        "7. **Несколько кандидатов одного риска.** "
        "Один кандидат → один объект с одним `candidate_index`. "
        "Несколько подтверждают ОДИН риск → один объект с несколькими `fragments`. "
        "Разные кандидаты подтверждают РАЗНЫЕ риски одного `risk_type` → несколько объектов.\n"
        "\n## СПРАВОЧНИК РИСКОВ\n"
        + risks_block
        + "\n\n## ФОРМАТ ОТВЕТА\n\n"
        "JSON-объект (НЕ массив!). Содержит:\n"
        "- `risks` — массив подтверждённых рисков (может быть пустым);\n"
        "- `contract_delivery_terms` — массив ВСЕХ сроков поставки договора "
        "(независимо от рисков, для мониторинга).\n\n"
        + _RESPONSE_FORMAT
        + "\nПРАВИЛА:\n"
        "- Если рисков нет — `\"risks\": []`.\n"
        "- `fragments: []` только для absence-рисков.\n"
        "- `severity` не может быть \"NONE\".\n"
        "- `risk_type` — строго из справочника.\n"
        "- `contract_delivery_terms` — ВСЕ сроки поставки договора:\n"
        "  • `relative` — «10 рабочих дней с момента оплаты» → "
        "{\"kind\": \"relative\", \"event\": \"payment_date\", \"offset\": 10, \"unit\": \"working\"};\n"
        "  • `fixed_date` — «не позднее 15.02.2026» → "
        "{\"kind\": \"fixed_date\", \"date\": \"2026-02-15\"};\n"
        "  • `fixed_period` — «с 01.03 по 15.03» → "
        "{\"kind\": \"fixed_period\", \"start\": \"2026-03-01\", \"end\": \"2026-03-15\"};\n"
        "  • `vague` — НЕ включай (нельзя вычислить);\n"
        "  • срок оплаты (не поставки) — НЕ включай.\n"
        "\n## ПРИМЕРЫ\n\n"
        "### Пример 1: размытый срок — риск HIGH, сроков нет\n\n"
        "Вход: кандидат [0] \"Поставка осуществляется в разумный срок.\"\n\n"
        "Выход:\n"
        + _EXAMPLE_1
        + "\n### Пример 2: срок определён — рисков нет, но срок сохраняется и llm находит "
          "несостыковку в значении поля unit и исправляет\n\n"
        "Вход: кандидат [0] \"Поставка в течение 10 рабочих дней с момента оплаты.\"\n"
        "delivery_terms от regex: [{\"event\": \"payment_date\", "
        "\"offset\": 10, \"unit\": \"calendar\"}]\n\n"
        "Выход:\n"
        + _EXAMPLE_2
        + "\n### Пример 3: срок привязан к событию, но без числа дней — HIGH\n\n"
        "Вход: кандидат [0] \"Поставка осуществляется после оплаты счёта.\"\n\n"
        "Выход:\n"
        + _EXAMPLE_3
        + "\n### Пример 4: фиксированная дата поставки\n\n"
          "Вход: кандидат [0] \"Поставка не позднее 15.02.2026.\"\n\n"
          "Выход:\n"
        + _EXAMPLE_4 + "\n"
    )

def _term_to_json(t) -> dict:
    base = {"kind": t.kind.value, "raw_text": t.raw_text}
    if t.kind == DeliveryTermKind.RELATIVE:
        base["event"] = t.event.value if t.event else None
        base["offset"] = t.offset
        base["unit"] = t.unit.value if t.unit else None
    elif t.kind == DeliveryTermKind.FIXED_DATE:
        base["date"] = t.fixed_date.isoformat() if t.fixed_date else None
    elif t.kind == DeliveryTermKind.FIXED_PERIOD:
        base["start"] = t.period_start.isoformat() if t.period_start else None
        base["end"] = t.period_end.isoformat() if t.period_end else None
    return base

def build_user_prompt(result: PreprocessingResult) -> str:
    sections: list[str] = []
    total_candidates = 0

    for risk_type in result.risk_types_checked:
        candidates = result.fragments_for(risk_type)

        sections.append(
            f"\n-----\n"
            f"RISK_TYPE: {risk_type}\n"
            f"CANDIDATES: {len(candidates)}\n"
        )

        if not candidates:
            absence = risk_type in result.risk_types_without_any_triggers
            sections.append(
                f"\n(кандидатов нет"
                + (" — absence-риск, примени absence_policy" if absence else "")
                + ")\n"
            )
            continue

        for i, frag in enumerate(candidates):
            total_candidates += 1

            terms_json = []
            for i, frag in enumerate(candidates):
                total_candidates += 1

                terms_json = [_term_to_json(t) for t in frag.delivery_terms]

            lines = [
                f"\n--- CANDIDATE [{i}] ---",
                f"has_negative_context: {frag.has_negative_context}",
            ]
            if terms_json:
                lines.append(f"delivery_terms: {json.dumps(terms_json, ensure_ascii=False)}")
            lines.append(f"TEXT:\n{frag.text}")
            lines.append(f"--- END CANDIDATE---\n")

            sections.append("\n".join(lines))

    header = (
        f"Проанализируй кандидатов по каждому риску и верни JSON-объект с risks "
        f"и contract_delivery_terms.\n"
        f"Если для риска нет кандидатов — примени absence_policy из system-промпта."
    )

    return header + "\n" + "\n".join(sections)