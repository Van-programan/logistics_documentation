from pathlib import Path

from src.contracts.source import SourceDocument
from src.parsing.enums import AttachmentType
from src.parsing.orchestrator import MultiFileParser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def debug_parse_multi(sources: list[SourceDocument]) -> None:
    print(f"=== Парсинг {len(sources)} файл(ов) ===")
    for s in sources:
        print(f"  - [{s.attachment_type.value}] {s.file_name} → {s.path}")

    parser = MultiFileParser()
    doc = parser.parse(sources)

    print(f"\nСклеенный текст: {len(doc.full_text)} символов")
    print(f"Источников: {len(doc.sources)}")
    print(f"Блоков: {len(doc.blocks)}")
    print(f"Разделителей между файлами: {len(doc.separators)}")

    print("\n--- Раскладка по источникам ---")
    for sid, src in doc.sources.items():
        print(f"  [{sid}] {src.source.file_name}: {src.format.value}, "
              f"{len(src.blocks)} блоков, {len(src.full_text)} символов")

    print("\n--- Первые 2000 символов склейки ---")
    print(doc.full_text[:2000])

    # Проверка экспорта
    print("\n=== Тест фрагментации (Путь B) ===")

    def check_export_roundtrip(doc, global_start, global_end):
        original = doc.full_text[global_start:global_end]
        info = doc.export_info(global_start, global_end)
        assert info is not None
        segments = info.segments
        assert segments

        g_starts = [s.global_start for s in segments]
        assert g_starts == sorted(g_starts)

        for s in segments:
            block = doc.block_for_position(s.global_start)
            assert block is not None
            if s.format.value == "DOCX" and s.table is None:
                assert s.paragraph == block.paragraph
            if s.format.value == "PDF":
                assert s.page == block.page

        covered_by_global = "".join(
            doc.full_text[s.global_start:s.global_end] for s in segments
        )
        covered_by_segments = "".join(
            doc.sources[s.source_id].full_text[s.local_start:s.local_end]
            for s in segments
        )
        assert covered_by_global == covered_by_segments

        # Потери — только разделители
        lost_positions = []
        cursor = global_start
        for s in segments:
            if cursor < s.global_start:
                lost_positions.append((cursor, s.global_start))
            cursor = s.global_end
        if cursor < global_end:
            lost_positions.append((cursor, global_end))
        for ls, le in lost_positions:
            lost = doc.full_text[ls:le]
            assert all(ch in "\n\r\t " for ch in lost), f"Потерян текст: {lost!r}"

        print(f"  ✓ [{'+'.join(info.source_ids)}] "
              f"global=[{global_start}:{global_end}] — {original[:50]!r}")

    for needle in ["в разумный срок", "Мир техники", "Срок поставки"]:
        idx = doc.full_text.find(needle)
        if idx == -1:
            continue
        check_export_roundtrip(doc, idx, idx + len(needle))

    # Предобработка + LLM payload
    debug_llm_payload(doc)


def debug_llm_payload(doc) -> None:
    """Показывает ровно то, что уйдёт в LLM."""
    from src.preprocessing.extractor import preprocess

    print("\n" + "=" * 70)
    print("=== LLM PAYLOAD (что уйдёт в языковую модель) ===")
    print("=" * 70)

    result = preprocess(doc)

    by_risk: dict[str, list] = {}
    for frag in result.fragments:
        by_risk.setdefault(frag.risk_type, []).append(frag)

    total_fragments = 0
    total_chars = 0

    for risk_type in result.risk_types_checked:
        frags = by_risk.get(risk_type, [])

        print(f"\n{'─' * 70}")
        print(f"RISK: {risk_type}")
        print(f"{'─' * 70}")

        if not frags:
            absence = risk_type in result.risk_types_without_any_triggers
            marker = " [absence: триггеров нет]" if absence else ""
            print(f"  Кандидатов: 0{marker}")
            continue

        print(f"  Кандидатов: {len(frags)}")

        for i, frag in enumerate(frags):
            total_fragments += 1
            total_chars += len(frag.text)

            print(f"\n  ┌─ Кандидат [{i}] ─────────────────────────────────────")
            print(f"  │ rank={frag.rank}  len={len(frag.text)}  "
                  f"neg={frag.has_negative_context}")
            print(f"  │ global=[{frag.global_start}:{frag.global_end}]")
            print(f"  │ triggers: {[t.phrase for t in frag.triggers]}")

            if frag.delivery_terms:
                print(f"  │ delivery_terms ({len(frag.delivery_terms)}):")
                for j, term in enumerate(frag.delivery_terms):
                    print(f"  │   [{j}] kind={term.kind.value} raw={term.raw_text!r}")
                    if term.kind.value == "relative":
                        print(f"  │       event={term.event.value if term.event else None}, "
                              f"offset={term.offset}, "
                              f"unit={term.unit.value if term.unit else None}")
                    if term.kind.value == "fixed_date":
                        print(f"  │       date={term.fixed_date}")
                    if term.kind.value == "fixed_period":
                        print(f"  │       period={term.period_start} … {term.period_end}")

            print(f"  │")
            print(f"  │ --- TEXT (пойдёт в LLM) ---")
            for line in frag.text.splitlines():
                print(f"  │ {line}")
            print(f"  │ --- END ---")
            print(f"  └─────────────────────────────────────────────────────")

    print(f"\n{'=' * 70}")
    print(f"ИТОГО:")
    print(f"  Типов рисков:     {len(result.risk_types_checked)}")
    print(f"  Всего кандидатов: {total_fragments}")
    print(f"  Объём:            {total_chars} символов (~{total_chars // 3} токенов)")
    if total_chars > 30000:
        print(f"  ⚠️  Много для одного вызова — уменьшить max_fragments")
    else:
        print(f"  ✓  Приемлемо для одного LLM-вызова")
    print(f"{'=' * 70}")

if __name__ == "__main__":
    sources = [
        SourceDocument(
            source_id="main",
            file_name="contract3.docx",
            attachment_type=AttachmentType.MAIN,
            path=str(DATA_DIR / "contract3.docx"),
        ),
        SourceDocument(
            source_id="schedule",
            file_name="schedule.docx",
            attachment_type=AttachmentType.SPECIFICATION,
            path=str(DATA_DIR / "schedule.docx"),
        ),
    ]
    debug_parse_multi(sources)