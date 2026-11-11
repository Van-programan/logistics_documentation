from pathlib import Path

from src.contracts.source import SourceDocument
from src.parsing.enums import AttachmentType
from src.parsing.orchestrator import MultiFileParser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def debug_parse_multi(sources: list[SourceDocument]) -> None:
    print("=" * 70)
    print("ШАГ 1. ПАРСИНГ")
    print("=" * 70)
    for s in sources:
        print(f"  - [{s.attachment_type.value}] {s.file_name} → {s.path}")

    parser = MultiFileParser()
    doc = parser.parse(sources)

    print(f"\nСклеенный текст: {len(doc.full_text)} символов")
    print(f"Источников: {len(doc.sources)}")
    print(f"Блоков: {len(doc.blocks)}")

    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ШАГ 2. ПРЕДОБРАБОТКА")
    print("=" * 70)

    from src.preprocessing.extractor import preprocess
    result = preprocess(doc)

    print(f"Типов рисков: {len(result.risk_types_checked)}")
    print(f"Кандидатов: {len(result.fragments)}")

    print("\nРазбивка по рискам:")
    for rt in result.risk_types_checked:
        frags = result.fragments_for(rt)
        marker = ""
        if not frags and rt in result.risk_types_without_any_triggers:
            marker = " [absence]"
        print(f"  {rt:30s} {len(frags):2d} фрагмент(ов){marker}")

    # Показать первые 200 символов каждого кандидата — для проверки
    print("\nПревью кандидатов:")
    for rt in result.risk_types_checked:
        for i, frag in enumerate(result.fragments_for(rt)):
            preview = frag.text[:120].replace("\n", " ")
            print(f"  [{rt}][{i}] global=[{frag.global_start}:{frag.global_end}] "
                  f"neg={frag.has_negative_context} — {preview!r}")

    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ШАГ 3. СБОРКА ПРОМПТА")
    print("=" * 70)

    from src.llm.prompts import build_system_prompt, build_user_prompt
    system = build_system_prompt()
    user = build_user_prompt(result)

    print(f"System: {len(system)} символов")
    print(f"User:   {len(user)} символов")
    print(f"Всего:  {len(system) + len(user)} символов "
          f"(~{(len(system) + len(user)) // 3} токенов)")

    # СОХРАНИТЬ промпты в файлы — чтобы точно видеть, что уходит
    debug_dir = PROJECT_ROOT / "debug"
    debug_dir.mkdir(exist_ok=True)
    (debug_dir / "system_prompt.txt").write_text(system, encoding="utf-8")
    (debug_dir / "user_prompt.txt").write_text(user, encoding="utf-8")

    print(f"\nПромпты сохранены в:")
    print(f"  {debug_dir / 'system_prompt.txt'}")
    print(f"  {debug_dir / 'user_prompt.txt'}")

    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ШАГ 4. ПРОВЕРКА: ВСЕ ЛИ КАНДИДАТЫ ПОПАЛИ В USER-ПРОМПТ")
    print("=" * 70)

    total_in_prompt = 0
    for rt in result.risk_types_checked:
        frags = result.fragments_for(rt)
        count_in_prompt = user.count(f"RISK_TYPE: {rt}")
        count_candidates_in_prompt = user.count("CANDIDATE [")

        print(f"  {rt:30s} "
              f"фрагментов={len(frags):2d}, "
              f"в промпте риск={count_in_prompt}, "
              f"всего CANDIDATE в промпте={count_candidates_in_prompt}")
        total_in_prompt += len(frags)

    print(f"\nВсего фрагментов: {total_in_prompt}")
    print(f"CANDIDATE [ в user-промпте: {user.count('CANDIDATE [')}")

    if total_in_prompt != user.count("CANDIDATE ["):
        print(f"⚠️ РАСХОЖДЕНИЕ: фрагментов={total_in_prompt}, "
              f"в промпте={user.count('CANDIDATE [')}")
    else:
        print("✓ Все фрагменты попали в user-промпт")

    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ШАГ 5. ВЫЗОВ GIGACHAT")
    print("=" * 70)

    from src.llm.client import call_gigachat

    try:
        raw = call_gigachat(system, user)
    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
        return

    print(f"\n✅ Ответ получен ({len(raw)} символов)")
    (debug_dir / "llm_raw_response.txt").write_text(raw, encoding="utf-8")
    print(f"Сохранён в: {debug_dir / 'llm_raw_response.txt'}")

    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ШАГ 6. РАЗБОР ОТВЕТА")
    print("=" * 70)

    print("\nСырой ответ:")
    print("-" * 70)
    print(raw)
    print("-" * 70)

    import json
    import re

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        print("(markdown-обёртка удалена)")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON невалиден: {e}")
        print(f"Позиция ошибки: {e.pos}, строка {e.lineno}, колонка {e.colno}")
        print(f"Контекст: {cleaned[max(0, e.pos-50):e.pos+50]!r}")
        return

    print(f"\n✅ JSON валиден")
    print(f"   Ключи: {list(data.keys())}")

    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ШАГ 7. АНАЛИЗ ОТВЕТА")
    print("=" * 70)

    risks = data.get("risks", [])
    terms = data.get("contract_delivery_terms", [])

    print(f"\nРисков: {len(risks)}")
    for r in risks:
        print(f"\n  [{r.get('risk_type')}] severity={r.get('severity')} "
              f"confidence={r.get('confidence')}")
        print(f"    description: {r.get('description', '')[:100]}")
        print(f"    fragments: {len(r.get('fragments', []))}")
        for f in r.get("fragments", []):
            print(f"      candidate_index={f.get('candidate_index')} "
                  f"quote={f.get('quote', '')[:60]!r}")

    print(f"\nСроков договора: {len(terms)}")
    for t in terms:
        print(f"  {t}")

    # ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("ШАГ 8. СВЕРКА: ЧТО LLM ПРОПУСТИЛА")
    print("=" * 70)

    found_risk_types = {r.get("risk_type") for r in risks}
    all_with_candidates = {
        rt for rt in result.risk_types_checked
        if result.fragments_for(rt)
    }

    print(f"\nРиски с кандидатами: {len(all_with_candidates)}")
    print(f"LLM вернула рисков: {len(found_risk_types)}")

    missed = all_with_candidates - found_risk_types
    if missed:
        print(f"\n⚠️ LLM пропустила (были кандидаты, но риска нет):")
        for rt in missed:
            frags = result.fragments_for(rt)
            print(f"  {rt} ({len(frags)} фрагмент(ов))")

    absence_types = set(result.risk_types_without_any_triggers)
    if absence_types:
        print(f"\nAbsence-риски (нет кандидатов): {absence_types}")


if __name__ == "__main__":
    sources = [
        SourceDocument(
            source_id="main",
            file_name="contract.docx",
            attachment_type=AttachmentType.MAIN,
            path=str(DATA_DIR / "contract2.pdf"),
        ),
        SourceDocument(
            source_id="main",
            file_name="contract.docx",
            attachment_type=AttachmentType.SPECIFICATION,
            path=str(DATA_DIR / "spec.docx"),
        ),
    ]
    debug_parse_multi(sources)