from __future__ import annotations

from src.preprocessing.models import PreprocessingResult
from src.preprocessing.terms.base import TermKind
from src.preprocessing.terms.extractor import extract_all_terms


_TABLE_SIGNS = (
    "|",
    "Кол-во",
    "Количество",
    "Наименование",
    "Ед. изм.",
    "шт.",
    "руб.",
)


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
        "when_no_candidates": "Нет кандидатов → 'NONE' (парсер проверит наличие товарной таблицы).",
    },
    "quantity_undefined": {
        "title": "Неопределённое количество товара",
        "high": "Количество НЕ указано ИЛИ размыто ('по заявке') БЕЗ механизма.",
        "medium": "Количество приблизительное с механизмом уточнения.",
        "when_no_candidates": "Нет кандидатов → 'NONE' (парсер проверит наличие товарной таблицы).",
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
      "description": "<ЧТО нарушено. Перефразируй своими словами. НЕ упоминай candidate_index или [N]>",
      "recommendation": "<что изменить в договоре. БЕЗ [N]>",
      "fragments": [
        {"candidate_index": <int>, "quote": "<ДОСЛОВНАЯ подстрока из TEXT кандидата>"}
      ]
    }
  ],
  "contract_terms": [
    {"kind": "delivery", "sub_kind": "relative", "event": "payment_date" | "invoice_date" | "contract_signing_date" | "spec_signing_date" | "acceptance_date", "offset": <int>, "unit": "working" | "calendar" | "banking" | "month"},
    {"kind": "delivery", "sub_kind": "fixed_date", "date": "YYYY-MM-DD"},
    {"kind": "delivery", "sub_kind": "fixed_period", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    {"kind": "acceptance", "event": "supplier_signed" | "delivery_date", "offset": <int>, "unit": "working" | "calendar"},
    {"kind": "renewal", "event": "contract_end", "offset": <int>, "unit": "working" | "calendar" | "month"}
  ]
}
'''


_EXAMPLE_RISK_ONLY = r'''
{
  "risks": [{
    "risk_type": "delivery_term_undefined",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Срок поставки указан размыто, без конкретной даты или числа дней",
    "recommendation": "Заменить на конкретный срок: N дней с события или конкретная дата",
    "fragments": [{"candidate_index": 0, "quote": "в разумный срок"}]
  }],
  "contract_terms": []
}
'''


_EXAMPLE_RISK_WITH_TERMS = r'''
{
  "risks": [{
    "risk_type": "liability_imbalance",
    "severity": "HIGH",
    "confidence": "HIGH",
    "description": "Неустойка покупателя 1% в день, поставщика — 0,1% в день: асимметрия в 10 раз",
    "recommendation": "Уравнять размеры неустоек для обеих сторон",
    "fragments": [
      {"candidate_index": 0, "quote": "Поставщик вправе потребовать от Покупателя уплаты пени в размере 1 %"},
      {"candidate_index": 0, "quote": "Покупатель вправе потребовать от Поставщика уплаты пени в размере 0,1%"}
    ]
  }],
  "contract_terms": [
    {"kind": "delivery", "sub_kind": "relative", "event": "payment_date", "offset": 10, "unit": "working"},
    {"kind": "acceptance", "event": "supplier_signed", "offset": 5, "unit": "working"},
    {"kind": "renewal", "event": "contract_end", "offset": 30, "unit": "calendar"}
  ]
}
'''


_EXAMPLE_NO_RISK_WITH_TERMS = r'''
{
  "risks": [],
  "contract_terms": [
    {"kind": "delivery", "sub_kind": "fixed_date", "date": "2026-03-15"}
  ]
}
'''


_EXAMPLE_MULTI_RISK = r'''
{
  "risks": [
    {
      "risk_type": "delivery_term_undefined",
      "severity": "HIGH",
      "confidence": "HIGH",
      "description": "Срок поставки отсутствует, указано только 'по заявке'",
      "recommendation": "Указать конкретный срок в днях с момента заявки",
      "fragments": [{"candidate_index": 0, "quote": "по заявке Покупателя"}]
    },
    {
      "risk_type": "quantity_undefined",
      "severity": "HIGH",
      "confidence": "HIGH",
      "description": "Количество определяется заявками без фиксации",
      "recommendation": "Указать механизм фиксации количества в спецификации",
      "fragments": [{"candidate_index": 1, "quote": "Покупатель самостоятельно определяет количество"}]
    }
  ],
  "contract_terms": []
}
'''

_EXAMPLE_MEDIUM_LOW_FIXED = r'''
{
  "risks": [{
    "risk_type": "quality_unconfirmed",
    "severity": "MEDIUM",
    "confidence": "LOW",
    "description": "Ссылка на ГОСТ есть, но без номера и конкретных требований",
    "recommendation": "Указать номер ГОСТ/ТУ и конкретные требования к качеству",
    "fragments": [{"candidate_index": 0, "quote": "соответствие ГОСТ"}]
  }],
  "contract_terms": [
    {"kind": "delivery", "sub_kind": "fixed_date", "date": "2026-03-15"},
    {"kind": "delivery", "sub_kind": "fixed_date", "date": "2026-04-30"}
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
            f"  ТОЛЬКО ЕСЛИ CANDIDATES: 0: {spec['when_no_candidates']}"
        )

    risks_block = "\n".join(risk_lines)

    return (
        "Ты — старший юрист-аналитик с 20-летним опытом проверки договоров поставки.\n"
        "Твоя задача — проанализировать кандидатов по каждому риску и вернуть СТРОГО JSON.\n"
        "\n## ГЛАВНОЕ ПРАВИЛО\n\n"
        "Ты анализируешь ПРИЗНАКИ риска (размытость, отсутствие, асимметрия, "
        "неполнота), а НЕ ищешь конкретные формулировки из примеров ниже. "
        "Примеры показывают только ФОРМАТ ответа. Цитаты в примерах — "
        "иллюстративные, не копируй их в свой ответ.\n"
        "\n## ЗАДАЧА (ПОШАГОВО)\n\n"
        "Для КАЖДОГО риска из справочника:\n"
        "  1. Прочитай СВОДКУ в начале user-промпта (карта документа).\n"
        "  2. Прочитай ВСЕ CANDIDATE по этому риску.\n"
        "  3. Прочитай секцию CONTRACT_TERMS.\n"
        "  4. Определи, есть ли ПРИЗНАК риска по HIGH/MEDIUM.\n"
        "  5. Проверь ПРАВИЛА 1.1, 1.2, 7 (ниже).\n"
        "  6. Если ДА — верни объект риска с дословной цитатой.\n"
        "  7. Если НЕТ — не включай в risks.\n"
        "  8. Если CANDIDATES: 0 — примени 'ТОЛЬКО ЕСЛИ CANDIDATES: 0'.\n\n"
        "Не пропускай риск ради 'чистого' ответа. Лучше вернуть и ошибиться, "
        "чем пропустить реальный риск. При этом не выдумывай риски ради заполнения — "
        "пустой risks: [] это ожидаемый результат для качественного договора.\n"
        "\n## КРИТИЧЕСКИЕ ПРАВИЛА\n\n"
        "1. Цитата дословно. quote — точная подстрока из TEXT. Не перефразируй.\n\n"
        "1.1. ЦИТАТА ПОЛНАЯ. Если в TEXT есть «за N дней», «в течение N дней», "
        "«не менее N дней» — включи это в цитату ЦЕЛИКОМ. НЕ обрывай на полуслове.\n\n"
        "1.2. ЦИТАТА ПОДТВЕРЖДАЕТ ВЫВОД. Юрист, прочитав цитату, должен СРАЗУ "
        "понять, почему это риск. Если цитата ОПРОВЕРГАЕТ риск (говорит "
        "«требования есть», «срок установлен») — НЕ возвращай риск.\n\n"
        "2. Один риск — один объект. Несколько независимых нарушений одного "
        "risk_type — несколько объектов.\n\n"
        "2.2. Для acceptance_missing: УПД, товарная накладная, ТТН, акт приёмки — "
        "считаются одним документом. Если срок подписания указан для любого из них — "
        "риск снят.\n\n"
        "3. Несколько фрагментов одного риска. Если 2+ кандидата подтверждают "
        "ОДИН риск — один объект с несколькими fragments. Если риск один "
        "(например, размытый срок) — фрагмент один.\n\n"
        "3.1. Один кандидат может подтверждать НЕСКОЛЬКО типов рисков. "
        "Верни отдельный объект для каждого risk_type. candidate_index может "
        "повторяться в разных объектах.\n\n"
        "4. Severity (насколько плохо). HIGH — отсутствует/явно нарушено. "
        "MEDIUM — есть, но размыто.\n\n"
        "4.1. Confidence (насколько уверен). HIGH — явно. MEDIUM — требует "
        "интерпретации. LOW — косвенно.\n\n"
        "5. has_negative_context. True — рядом маркер определённости, снижает риск.\n\n"
        "6. description vs quote. description — твой вывод (перефразируй). "
        "quote — дословно из TEXT. Не смешивай.\n\n"
        "7. СВЕРКА С contract_terms (сроки поставки). Если в contract_terms "
        "УЖЕ есть delivery с sub_kind=relative (event+offset+unit) ИЛИ "
        "fixed_date/fixed_period — delivery_term_undefined НЕ может быть HIGH. "
        "Максимум MEDIUM (если есть противоречие в тексте), либо не возвращай вовсе.\n\n"
        "7.1. ПРОТИВОРЕЧИЕ СРОКОВ. Это когда два срока претендуют на ОДИН "
        "результат: например, «10 раб. дней с оплаты» И «до 15.03.2026», причём "
        "10 раб. дней наступит ПОЗЖЕ 15.03.2026. Тогда верни "
        "delivery_term_undefined: MEDIUM с обоими фрагментами и "
        "description: «Противоречие сроков». Если fixed_date — «крайний срок» "
        "(не позднее), а relative — «типичный», это НЕ противоречие.\n\n"
        "8. CONTRACT_TERMS. Подтверди/исправь/добавь/удали сроки из секции "
        "CONTRACT_TERMS user-промпта. Форматы — в схеме ответа.\n"
        "8.1. НЕ включай: unit=minute/hour, ДУБЛИ, срок оплаты (это не срок поставки).\n"
        "8.2. Если CONTRACT_TERMS пуст, но в кандидатах есть срок — добавь его. "
        "Не копируй [] из примеров.\n\n"
        "9. when_no_candidates: NONE — НЕ включай риск в risks, даже если "
        "CANDIDATES: 0. Это значит «не проверялось», а не «риска нет».\n\n"
        "\n## СПРАВОЧНИК РИСКОВ\n"
        + risks_block
        + "\n\n## ФОРМАТ ОТВЕТА\n\n"
        "JSON-объект. Содержит risks (массив, может быть пустым) и "
        "contract_terms (массив сроков для мониторинга).\n\n"
        + _RESPONSE_FORMAT
        + "\n## ПРИМЕРЫ (4 шт., покрывают все сценарии)\n\n"
        "### Пример 1: только риск, без сроков. ОДИН фрагмент\n"
        "Вход: кандидат содержит размытый срок.\n"
        "Выход:\n" + _EXAMPLE_RISK_ONLY
        + "\n### Пример 2: риск + сроки в contract_terms. ДВА фрагмента\n"
        "Вход: кандидат содержит неустойки для обеих сторон; в CONTRACT_TERMS есть "
        "delivery, acceptance, renewal.\n"
        "ВАЖНО: 2 фрагмента здесь потому, что две СТОРОНЫ (поставщик и покупатель) — "
        "это ОДИН риск с двумя доказательствами. Если риск один (например, размытый "
        "срок) — фрагмент один (см. Пример 1). Также: liability_imbalance НЕ ТРЕБУЕТ "
        "contract_terms — если неустойки асимметричны, а сроков нет, верни риск "
        "с contract_terms: [].\n"
        "Выход:\n" + _EXAMPLE_RISK_WITH_TERMS
        + "\n### Пример 3: риска нет, но сроки в contract_terms есть\n"
        "Вход: в CONTRACT_TERMS есть delivery fixed_date; рисков нет.\n"
        "Выход:\n" + _EXAMPLE_NO_RISK_WITH_TERMS
        + "\n### Пример 4: один кандидат → несколько рисков\n"
        "Вход: кандидат про заявки подтверждает и срок поставки, и количество.\n"
        "Выход:\n" + _EXAMPLE_MULTI_RISK
        + "\n### Пример 5: MEDIUM + confidence LOW + НЕСКОЛЬКО fixed_date\n"
        "Вход: кандидат содержит ссылку на ГОСТ без номера; в CONTRACT_TERMS "
        "несколько дат поставки (партии).\n"
        "ВАЖНО: severity=MEDIUM — риск ЕСТЬ, но размыт (ГОСТ без номера). "
        "confidence=LOW — цитата косвенная (нет явного нарушения, только "
        "неполнота). confidence=LOW → PENDING_CONFIRMATION (юрист проверит). "
        "Два fixed_date — это ДВЕ ПАРТИИ, каждая со своим сроком; НЕ объединяй "
        "их в один объект, верни два.\n"
        "Выход:\n" + _EXAMPLE_MEDIUM_LOW_FIXED
    )


def _term_to_text(t) -> str:
    kind = t.kind.value

    if t.fixed_date:
        return f"kind={kind}, date={t.fixed_date}"
    if t.period_start and t.period_end:
        return f"kind={kind}, period={t.period_start}…{t.period_end}"

    sub = f", sub_kind={t.sub_kind.value}" if t.sub_kind else ""
    unit = t.unit.value if t.unit else "?"
    return f"kind={kind}{sub}, event={t.event or '?'}, offset={t.offset}, unit={unit}"


def _build_summary(result: PreprocessingResult, terms_by_kind: dict[str, list]) -> str:
    lines = ["\n=====\nСВОДКА (карта документа)\n"]

    checked = list(result.risk_types_checked)
    with_candidates = [rt for rt in checked if result.fragments_for(rt)]
    without_candidates = [rt for rt in checked if not result.fragments_for(rt)]

    lines.append(f"• Секции с кандидатами ({len(with_candidates)}): "
                 f"{', '.join(with_candidates) or '—'}\n")
    lines.append(f"• Секции БЕЗ кандидатов ({len(without_candidates)}): "
                 f"{', '.join(without_candidates) or '—'}\n")

    has_table_like = False
    for rt in checked:
        for frag in result.fragments_for(rt):
            if any(sign in frag.text for sign in _TABLE_SIGNS):
                has_table_like = True
                break
        if has_table_like:
            break
    lines.append(
        f"• Товарная таблица в кандидатах (эвристика): "
        f"{'ДА' if has_table_like else 'нет'}. "
        f"Парсер проверит точнее и снимет ложные риски.\n"
    )

    delivery_cnt = len(terms_by_kind.get("delivery", []))
    acceptance_cnt = len(terms_by_kind.get("acceptance", []))
    renewal_cnt = len(terms_by_kind.get("renewal", []))

    lines.append(
        f"• Сроки в CONTRACT_TERMS: "
        f"delivery={delivery_cnt}, acceptance={acceptance_cnt}, renewal={renewal_cnt} "
        f"(см. секцию CONTRACT_TERMS ниже)\n"
    )

    lines.append("=====\n")
    return "".join(lines)


def build_user_prompt(result: PreprocessingResult, full_text: str = "") -> str:
    terms_by_kind: dict[str, list] = {}
    if full_text:
        all_terms = extract_all_terms(full_text)
        for t in all_terms:
            if t.kind in (TermKind.CONTRACT_DATE, TermKind.END_DATE):
                continue
            terms_by_kind.setdefault(t.kind.value, []).append(t)

    summary = _build_summary(result, terms_by_kind)

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
                f"TEXT:\n{frag.text}",
                f"--- END CANDIDATE [{i}] ---\n",
            ]
            sections.append("\n".join(lines))

    terms_section: list[str] = []
    if full_text:
        terms_section.append(
            "\n\n"
            "=====\n"
            "CONTRACT_TERMS — сроки, извлечённые по ВСЕМУ договору\n"
            "Эти сроки — для МОНИТОРИНГА. Подтверди/исправь/добавь/удали их "
            "в `contract_terms` ответе на основе предъявленных кандидатов так как "
            "целого договора я тебе не передаю, пользуйся вырезанными фрагментами кандидатов.\n"
            "=====\n"
        )

        for kind in [TermKind.DELIVERY, TermKind.ACCEPTANCE, TermKind.RENEWAL]:
            terms = terms_by_kind.get(kind.value, [])
            if not terms:
                continue
            terms_section.append(f"\n[{kind.value}] — {len(terms)} шт.:\n")
            for i, t in enumerate(terms):
                raw_preview = t.raw_text[:150].replace("\n", " ")
                terms_section.append(f"  {i}. {raw_preview!r}\n")
                terms_section.append(f"     → {_term_to_text(t)}\n")

        if not terms_by_kind:
            terms_section.append("\n(сроки не найдены в тексте)\n")

        terms_section.append(
            "\nПодтверди/исправь эти сроки в `contract_terms` ответа.\n"
        )

    header = (
        f"Проанализируй кандидатов. Всего рисков: {len(result.risk_types_checked)}, "
        f"с кандидатами: {total_risks_with_candidates}, "
        f"кандидатов: {total_candidates}.\n"
        f"Правила — в system prompt. СВОДКА (ниже) — карта документа."
    )

    return (
        header
        + "\n"
        + summary
        + "\n"
        + "\n".join(sections)
        + "\n".join(terms_section)
    )