from __future__ import annotations

from src.preprocessing.models import PreprocessingResult
from src.preprocessing.delivery_term import DeliveryTermKind


RISK_SPECS: dict[str, dict] = {
    "delivery_term_undefined": {
        "title": "Неопределённый срок поставки",
        "high": "Срок ОТСУТСТВУЕТ или РАЗМЫТ: 'в разумный срок', 'по заявке' без механизма, 'после оплаты' без числа дней.",
        "medium": "Срок привязан к событию, но БЕЗ единицы (дни/месяцы) ИЛИ противоречив.",
        "when_no_candidates": "Нет кандидатов → 'HIGH' (срок не определён).",
    },
    "acceptance_missing": {
        "title": "Отсутствие порядка приёмки",
        "high": "НЕТ порядка приёмки ИЛИ НЕТ сроков подписания УПД/накладной.",
        "medium": "Приёмка упомянута, но сроки размыты ИЛИ нет порядка для скрытых недостатков.",
        "when_no_candidates": "Нет кандидатов → 'HIGH' (порядок не описан).",
    },
    "liability_imbalance": {
        "title": "Неравенство ответственности сторон",
        "high": "Неустойка/штраф одной стороны в 2+ раза выше другой ИЛИ у одной стороны ответственности нет.",
        "medium": "Размеры различаются в 1.5–2 раза ИЛИ формулировки асимметричны без явного перекоса.",
        "when_no_candidates": "Нет кандидатов → 'MEDIUM' (ответственность не урегулирована).",
    },
    "quality_unconfirmed": {
        "title": "Неподтверждённое качество товара",
        "high": "НЕТ ни одной ссылки на ГОСТ/ТУ/сертификаты ИЛИ требования 'обычные требования' БЕЗ конкретики.",
        "medium": "Ссылки на ГОСТ/ТУ/сертификаты ЕСТЬ, но без номеров/конкретных стандартов.",
        "when_no_candidates": "Нет кандидатов → 'HIGH' (требований нет).",
    },
    "currency_risk": {
        "title": "Валютный риск",
        "high": "Цена в валюте/у.е. БЕЗ фиксации курса.",
        "medium": "Цена в валюте, но курс зафиксирован.",
        "when_no_candidates": "Нет кандидатов → 'NONE' (риска нет).",
    },
    "item_name_vague": {
        "title": "Некорректное наименование товара",
        "high": "Товар описан ТОЛЬКО общими словами БЕЗ артикула/модели/марки.",
        "medium": "Наименование есть, но неполное (есть модель, нет артикула/марки).",
        "when_no_candidates": "Нет кандидатов → 'HIGH'.",
    },
    "quantity_undefined": {
        "title": "Неопределённое количество товара",
        "high": "Количество НЕ указано ИЛИ размыто ('по заявке') БЕЗ механизма.",
        "medium": "Количество приблизительное с механизмом уточнения.",
        "when_no_candidates": "Нет кандидатов → 'HIGH'.",
    },
    "schedule_missing": {
        "title": "Отсутствие графика поставки",
        "high": "Поставка партиями, но НЕТ периодов/сроков каждой партии.",
        "medium": "График упомянут, но не детализирован.",
        "when_no_candidates": "Нет кандидатов → 'MEDIUM'.",
    },
    "auto_renewal": {
        "title": "Автоматическая пролонгация",
        "high": "Автопролонгация БЕЗ срока уведомления ИЛИ срок < 30 дней.",
        "medium": "Автопролонгация со сроком уведомления 30+ дней.",
        "when_no_candidates": "Нет кандидатов → 'NONE'.",
    },
}


_RESPONSE_FORMAT = r'''
{
  "risks": [
    {
      "risk_type": "<строка из справочника>",
      "severity": "HIGH" | "MEDIUM",
      "confidence": "HIGH" | "MEDIUM" | "LOW",
      "description": "<краткое описание: ЧТО нарушено. БЕЗ [N]>",
      "recommendation": "<что изменить в договоре. БЕЗ [N]>",
      "fragments": [
        {"candidate_index": <int>, "quote": "<дословная подстрока из TEXT>"}
      ]
    }
  ],
  "contract_delivery_terms": [
    {"kind": "relative", "event": "payment_date" | "invoice_date" | "contract_signing_date" | "spec_signing_date" | "acceptance_date", "offset": <int>, "unit": "working" | "calendar" | "banking" | "month"},
    {"kind": "fixed_date", "date": "YYYY-MM-DD"},
    {"kind": "fixed_period", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
  ]
}
'''


# ============================================================
# ПРИМЕРЫ
# ============================================================

_EXAMPLE_DELIVERY_TERM = r'''
{
  "risks": [{
    "risk_type": "delivery_term_undefined",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Срок поставки указан размыто, без конкретной даты или числа дней",
    "recommendation": "Заменить на конкретный срок: N дней с события ИЛИ конкретная дата",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_ACCEPTANCE = r'''
{
  "risks": [{
    "risk_type": "acceptance_missing",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Порядок приёмки товара не описан, сроки подписания УПД отсутствуют",
    "recommendation": "Добавить порядок приёмки: срок проверки, форма акта, срок подписания УПД",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_LIABILITY = r'''
{
  "risks": [{
    "risk_type": "liability_imbalance",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Размер неустойки для одной стороны значительно выше, чем для другой",
    "recommendation": "Уравнять размеры неустоек для обеих сторон",
    "fragments": [
      {"candidate_index": 0, "quote": "<цитата про неустойку стороны 1>"},
      {"candidate_index": 0, "quote": "<цитата про неустойку стороны 2>"}
    ]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_QUALITY = r'''
{
  "risks": [{
    "risk_type": "quality_unconfirmed",
    "severity": "MEDIUM",
    "confidence": "HIGH",
    "description": "Ссылка на стандарты качества есть, но без номеров и конкретных требований",
    "recommendation": "Указать номера ГОСТ/ТУ и конкретные требования к качеству",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_CURRENCY = r'''
{
  "risks": [{
    "risk_type": "currency_risk",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Цена указана в валюте/у.е. без фиксации курса на дату платежа",
    "recommendation": "Зафиксировать курс на дату платежа ИЛИ указать цену в рублях",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_ITEM_NAME = r'''
{
  "risks": [{
    "risk_type": "item_name_vague",
    "severity": "MEDIUM",
    "confidence": "HIGH",
    "description": "Наименование товара указано неполно: есть модель, но нет артикула/марки",
    "recommendation": "Добавить артикул/марку/сорт для однозначной идентификации товара",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_QUANTITY = r'''
{
  "risks": [{
    "risk_type": "quantity_undefined",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Количество товара указано размыто, без механизма определения",
    "recommendation": "Указать точное количество ИЛИ механизм его определения",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_SCHEDULE = r'''
{
  "risks": [{
    "risk_type": "schedule_missing",
    "severity": "MEDIUM",
    "confidence": "HIGH",
    "description": "График поставки упомянут, но не детализирован по партиям",
    "recommendation": "Указать периоды/сроки для каждой партии поставки",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


_EXAMPLE_AUTO_RENEWAL = r'''
{
  "risks": [{
    "risk_type": "auto_renewal",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Договор пролонгируется автоматически, срок уведомления об отказе не определён",
    "recommendation": "Указать срок уведомления (не менее 30 дней) и порядок отказа",
    "fragments": [{"candidate_index": 0, "quote": "<точная цитата из текста>"}]
  }],
  "contract_delivery_terms": []
}
'''


# ============================================================
# SYSTEM PROMPT
# ============================================================

def build_system_prompt() -> str:
    risk_lines = []
    for risk_type, spec in RISK_SPECS.items():
        risk_lines.append(
            f"\n### {risk_type} — {spec['title']}\n"
            f"  HIGH: {spec['high']}\n"
            f"  MEDIUM: {spec['medium']}\n"
            f"  ТОЛЬКО ЕСЛИ CANDIDATES: 0: {spec['when_no_candidates']}"
        )

    risks_block = "\n".join(risk_lines)

    return (
        "Ты — старший юрист-аналитик с 20-летним опытом проверки договоров поставки.\n"
        "Твоя задача — проанализировать кандидатов по каждому риску и вернуть СТРОГО JSON.\n"
        "\n## ГЛАВНОЕ ПРАВИЛО\n\n"
        "Ты анализируешь **ПРИЗНАКИ** риска (размытость, отсутствие, асимметрия, "
        "неполнота), а НЕ ищешь конкретные формулировки из примеров ниже. "
        "Примеры показывают только ФОРМАТ ответа — формулировки в твоём документе "
        "будут другими. Цитаты в примерах — это `<placeholder>`, ты должен подставить "
        "реальную цитату из кандидата.\n"
        "\n## ЗАДАЧА (ПОШАГОВО)\n\n"
        "Для КАЖДОГО риска из справочника:\n"
        "  1. Прочитай ВСЕ `CANDIDATE` по этому риску.\n"
        "  2. **ПРОЧИТАЙ ВСЕ `contract_delivery_terms` и ВСЕХ кандидатов ДРУГИХ "
        "рисков** — иногда контекст в другом блоке опровергает риск.\n"
        "  3. Определи, есть ли ПРИЗНАК риска по HIGH/MEDIUM.\n"
        "  4. Проверь ПРАВИЛА 0, 1.1, 1.2, 2.1, 7.1, 7.2 (ниже).\n"
        "  5. Если ДА — верни объект риска с дословной цитатой.\n"
        "  6. Если НЕТ — не включай в `risks`.\n"
        "  7. Если `CANDIDATES: 0` — примени 'ТОЛЬКО ЕСЛИ CANDIDATES: 0'.\n\n"
        "**Не пропускай риск ради 'чистого' ответа.** Лучше вернуть и ошибиться, "
        "чем пропустить реальный риск.\n"
        "\n## КРИТИЧЕСКИЕ ПРАВИЛА\n\n"
        "0. **КРОСС-СЕКЦИОННЫЙ АНАЛИЗ.** Информация о риске может быть "
        "в кандидатах **ДРУГОГО** `risk_type`. Примеры связей:\n"
        "   • `quantity_undefined` — количество может быть в кандидате "
        "`item_name_vague` (Спецификация, таблица с числами);\n"
        "   • `item_name_vague` — наименование может быть в кандидате "
        "`quantity_undefined` или `schedule_missing` (График поставки);\n"
        "   • `schedule_missing` — график может быть в кандидате "
        "`delivery_term_undefined`;\n"
        "   • `delivery_term_undefined` — срок может быть в "
        "`contract_delivery_terms` (если там уже есть срок — риск снят).\n"
        "   **Перед выводом HIGH/MEDIUM по любому риску — просмотри ВСЕ секции "
        "`RISK_TYPE` в user-промпте, а не только текущую.** Если в другой секции "
        "есть опровергающая информация — риск НЕ подтверждается.\n\n"
        "1. **Цитата дословно.** `quote` — точная подстрока из `TEXT`. Не перефразируй.\n\n"
        "1.1. **ЦИТАТА ПОЛНАЯ.** Если в TEXT есть «за N дней», «в течение N дней», "
        "«не менее N дней» — включи это в цитату ЦЕЛИКОМ. НЕ обрывай на полуслове. "
        "Для вывода читай ВЕСЬ TEXT кандидата, а не только цитату.\n\n"
        "1.2. **ЦИТАТА ПОДТВЕРЖДАЕТ ВЫВОД.** Юрист, прочитав цитату, должен СРАЗУ "
        "понять, почему это риск. Если цитата ОПРОВЕРГАЕТ риск (говорит "
        "«требования есть», «срок установлен») — НЕ возвращай риск.\n\n"
        "2. **Один риск — один объект.** Несколько независимых нарушений одного "
        "`risk_type` — несколько объектов.\n\n"
        "2.1. **АБСОЛЮТНЫЙ ЗАПРЕТ: `quantity_undefined` И `item_name_vague` ПРИ НАЛИЧИИ ТАБЛИЦЫ.**\n"
        "\n"
        "     ЭТО НЕ РЕКОМЕНДАЦИЯ, А ЖЁСТКОЕ ПРАВИЛО.\n"
        "\n"
        "     ШАГ 1. Перед выводом `quantity_undefined` или `item_name_vague` — "
        "ОБЯЗАТЕЛЬНО просмотри ВСЕ секции `RISK_TYPE` в user-промпте.\n"
        "\n"
        "     ШАГ 2. Найди ЛЮБОЙ кандидат, в котором есть ХОТЯ БЫ ОДИН из признаков:\n"
        "     - символ `|` (вертикальная черта — разделитель колонок таблицы), ИЛИ\n"
        "     - слова `Кол-во`, `Количество`, `Наименование`, `Ед. изм.`, `шт.`, `руб.`, ИЛИ\n"
        "     - числа с единицами измерения (`<число> шт.`, `<число> м`, `<число> кг`, `<число> руб.`), ИЛИ\n"
        "     - конкретные модели/артикулы/марки (буквенно-цифровые обозначения "
        "или полные названия с характеристиками).\n"
        "\n"
        "     ШАГ 3. Если нашёл ХОТЯ БЫ ОДИН такой кандидат:\n"
        "     - `quantity_undefined` → **НЕ ВКЛЮЧАЙ в `risks`** (верни `[]` для этого типа).\n"
        "     - `item_name_vague` → **НЕ ВКЛЮЧАЙ в `risks`** (верни `[]` для этого типа).\n"
        "\n"
        "     ШАГ 4. Это правило **ПЕРЕОПРЕДЕЛЯЕТ** любые другие правила severity/confidence.\n"
        "     Даже если кажется, что «механизм определения не указан» — "
        "**при наличии таблицы с конкретными данными риск НЕ подтверждается.**\n"
        "\n"
        "     ОБОСНОВАНИЕ: если в договоре есть таблица с конкретными количествами "
        "и наименованиями — значит, эти данные ОПРЕДЕЛЕНЫ. Риск «не указано» "
        "не может быть HIGH, потому что противоречит факту наличия таблицы.\n\n"
        "3. **Несколько фрагментов одного риска.** Если 2+ кандидата подтверждают "
        "ОДИН риск — один объект с несколькими `fragments`.\n\n"
        "4. **Severity.** HIGH — отсутствует/явно нарушено. MEDIUM — есть, но размыто.\n\n"
        "5. **Confidence.** HIGH — явно. MEDIUM — требует интерпретации. LOW — косвенно.\n\n"
        "6. **has_negative_context.** `True` — рядом маркер определённости, снижает риск.\n\n"
        "7. **Сроки в кандидате (delivery_terms).** `kind=relative` с event+offset+unit "
        "— срок ОПРЕДЕЛЁН, НЕ риск. `kind=vague` — риск HIGH. Если regex ошибся "
        "(например, `unit=calendar`, а в тексте «рабочих дней») — исправь в "
        "`contract_delivery_terms`.\n\n"
        "7.1. **ЗАПРЕТ ПРОТИВОРЕЧИЙ.** Если в `contract_delivery_terms` УЖЕ есть "
        "`relative` с event+offset+unit ИЛИ `fixed_date`/`fixed_period` — "
        "НЕ возвращай `delivery_term_undefined` со severity=HIGH. "
        "Максимум — MEDIUM (если есть противоречие в тексте), либо не возвращай вовсе.\n\n"
        "7.2. **СВЕРКА С `contract_delivery_terms`.** Если в `contract_delivery_terms` "
        "уже есть `relative` с event+offset+unit ИЛИ `fixed_date` — "
        "`delivery_term_undefined` НЕ может быть HIGH. Максимум MEDIUM.\n\n"
        "8. **`contract_delivery_terms` — УНИКАЛЬНЫЕ сроки ПОСТАВКИ.**\n"
        "   • `relative` с event+offset+unit (`working`|`calendar`|`banking`|`month`);\n"
        "   • `fixed_date` с датой;\n"
        "   • `fixed_period` с start+end.\n"
        "   НЕ включай: `unit=\"minute\"/\"hour\"`, срок оплаты, `vague`, ДУБЛИ.\n"
        "   **Проверь:** нет двух элементов с одинаковыми (event, offset, unit).\n\n"
        "9. **Никаких `[N]` в тексте.** В `description`/`recommendation` НЕ упоминай "
        "`candidate_index`, `[0]`, `кандидат N`.\n\n"
        "10. **Если рисков нет совсем** — верни `\"risks\": []`. Это НОРМАЛЬНО, если "
        "все кандидаты описывают корректные условия. Но проверь КАЖДОГО кандидата "
        "по признакам из справочника.\n"
        "\n## СПРАВОЧНИК РИСКОВ\n"
        + risks_block
        + "\n\n## ФОРМАТ ОТВЕТА\n\n"
        "JSON-объект. Содержит `risks` (массив, может быть пустым) и "
        "`contract_delivery_terms` (массив уникальных сроков поставки).\n\n"
        + _RESPONSE_FORMAT
        + "\n## ПРИМЕРЫ (по одному на каждый риск)\n\n"
        "### `delivery_term_undefined` — размытый срок\n"
        "Вход: кандидат содержит 'в разумный срок' / 'по заявке' / 'по мере необходимости'.\n"
        "Выход:\n" + _EXAMPLE_DELIVERY_TERM
        + "\n### `acceptance_missing` — нет порядка приёмки\n"
        "Вход: кандидат — раздел про приёмку без сроков и формы акта.\n"
        "Выход:\n" + _EXAMPLE_ACCEPTANCE
        + "\n### `liability_imbalance` — асимметрия неустоек\n"
        "Вход: кандидат содержит неустойки для обеих сторон с разными размерами.\n"
        "Выход:\n" + _EXAMPLE_LIABILITY
        + "\n### `quality_unconfirmed` — неполные требования к качеству\n"
        "Вход: кандидат содержит 'соответствие ГОСТ' без номера/конкретики.\n"
        "Выход:\n" + _EXAMPLE_QUALITY
        + "\n### `currency_risk` — цена в валюте без фиксации курса\n"
        "Вход: кандидат содержит 'у.е.' / 'долларах' / 'по курсу' без фиксации.\n"
        "Выход:\n" + _EXAMPLE_CURRENCY
        + "\n### `item_name_vague` — неполное наименование товара\n"
        "Вход: кандидат содержит общее наименование товара ('продукты', 'оборудование', "
        "модель без артикула).\n"
        "Выход:\n" + _EXAMPLE_ITEM_NAME
        + "\n### `quantity_undefined` — размытое количество\n"
        "Вход: кандидат содержит 'по заявке' / 'по потребности' про количество.\n"
        "Выход:\n" + _EXAMPLE_QUANTITY
        + "\n### `schedule_missing` — график упомянут, но не детализирован\n"
        "Вход: кандидат содержит 'график поставки' без периодов для партий.\n"
        "Выход:\n" + _EXAMPLE_SCHEDULE
        + "\n### `auto_renewal` — автопролонгация\n"
        "Вход: кандидат содержит 'считается пролонгированным' / 'автоматически продлевается'.\n"
        "Выход:\n" + _EXAMPLE_AUTO_RENEWAL
    )

def _term_to_text(t) -> str:
    if t.kind == DeliveryTermKind.RELATIVE:
        return (f"kind=relative, event={t.event.value if t.event else '?'}, "
                f"offset={t.offset}, unit={t.unit.value if t.unit else '?'}")
    if t.kind == DeliveryTermKind.FIXED_DATE:
        return f"kind=fixed_date, date={t.fixed_date}"
    if t.kind == DeliveryTermKind.FIXED_PERIOD:
        return f"kind=fixed_period, start={t.period_start}, end={t.period_end}"
    return f"kind={t.kind.value}"


def build_user_prompt(result: PreprocessingResult) -> str:
    sections: list[str] = []
    total_candidates = 0
    total_risks_with_candidates = 0

    for risk_type in result.risk_types_checked:
        candidates = result.fragments_for(risk_type)

        if candidates:
            total_risks_with_candidates += 1
            sections.append(
                f"\n=====\n"
                f"RISK_TYPE: {risk_type}\n"
                f"CANDIDATES: {len(candidates)} — ЕСТЬ кандидаты, проверь признаки риска\n"
            )
        else:
            absence = risk_type in result.risk_types_without_any_triggers
            marker = " — absence-риск, примени 'ТОЛЬКО ЕСЛИ CANDIDATES: 0'" if absence else ""
            sections.append(
                f"\n=====\n"
                f"RISK_TYPE: {risk_type}\n"
                f"CANDIDATES: 0{marker}\n"
            )
            continue

        for i, frag in enumerate(candidates):
            total_candidates += 1
            lines = [
                f"\n--- CANDIDATE [{i}] ---",
                f"has_negative_context: {frag.has_negative_context}",
            ]
            if frag.delivery_terms:
                terms_lines = [_term_to_text(t) for t in frag.delivery_terms]
                lines.append("delivery_terms (от regex):")
                for tl in terms_lines:
                    lines.append(f"  • {tl}")
            lines.append(f"TEXT:\n{frag.text}")
            lines.append(f"--- END CANDIDATE [{i}] ---\n")
            sections.append("\n".join(lines))

    header = (
        f"Проанализируй кандидатов. Всего рисков: {len(result.risk_types_checked)}, "
        f"с кандидатами: {total_risks_with_candidates}, "
        f"кандидатов: {total_candidates}.\n"
        f"Для CANDIDATES: 0 примени 'ТОЛЬКО ЕСЛИ CANDIDATES: 0'.\n"
        f"`contract_delivery_terms` — БЕЗ ДУБЛЕЙ, только сроки поставки.\n"
        f"ПРАВИЛО 2.1: если видишь таблицу — quantity_undefined / item_name_vague НЕ риск.\n"
        f"Анализируй ПРИЗНАКИ риска, не ищи формулировки из примеров."
    )

    return header + "\n" + "\n".join(sections)