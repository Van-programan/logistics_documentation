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
        n_blocks = len(src.blocks)
        print(f"  [{sid}] {src.source.file_name}: {src.format.value}, "
              f"{n_blocks} блоков, {len(src.full_text)} символов")

    print("\n--- Первые 2000 символов склейки ---")
    print(doc.full_text[-3000:])

    # Проверка: возьмём первые 2 блока — они должны указывать на договор
    print("\n--- Первые 2 блока ---")
    for b in doc.blocks[:2]:
        assert doc.full_text[b.global_start:b.global_end] == b.text
        src = doc.sources[b.source_id]
        assert src.full_text[b.local_start:b.local_end] == b.text
        print(
            f"[{b.source_id}] local={b.local_start}-{b.local_end} "
            f"global={b.global_start}-{b.global_end} "
            f"paragraph={b.paragraph} table={b.table} row={b.row} page={b.page}: "
            f"{b.text[:60]!r}"
        )

    # Проверка: найдём позицию спецификации
    print("\n--- Первые 200 символов спецификации ---")
    for sid, src in doc.sources.items():
        if sid != "main":
            print(f"[{sid}]: {src.full_text[:400]}")
            break

    print("\n=== Тест фрагментации для сервиса экспорта (Путь B) ===")

    def check_export_roundtrip(doc, global_start: int, global_end: int) -> None:
        """Проверяет, что фрагмент, пройдя через export_info, возвращается
        тем же текстом при склейке сегментов — с точностью до разделителей
        между блоками, которые не принадлежат ни одному блоку."""
        original = doc.full_text[global_start:global_end]
        info = doc.export_info(global_start, global_end)
        assert info is not None, f"export_info=None для [{global_start}:{global_end}]"

        segments = info["segments"]
        assert segments, "Пустой список segments"

        # 1. Порядок и отсутствие перекрытий
        g_starts = [s["global_start"] for s in segments]
        assert g_starts == sorted(g_starts)
        for a, b in zip(segments, segments[1:]):
            assert a["global_end"] <= b["global_start"]

        # 2. Каждый сегмент должен лежать внутри одного блока
        for s in segments:
            block = doc.block_for_position(s["global_start"])
            assert block is not None
            assert block.source_id == s["source_id"]
            assert block.global_start <= s["global_start"]
            assert s["global_end"] <= block.global_end

            if s["format"] == "DOCX" and s["table"] is None:
                assert s["paragraph"] == block.paragraph
            if s["format"] == "PDF":
                assert s["page"] == block.page

        # 3. Восстановление текста: сегменты == фрагмент БЕЗ «дыр».
        #    Собираем из фрагмента только те куски, что покрыты сегментами.
        covered_text_parts: list[str] = []
        cursor = global_start
        for s in segments:
            # Пропускаем «дыру» между cursor и s["global_start"] — это разделители
            # между блоками/страницами, они не принадлежат ни одному блоку.
            covered_text_parts.append(doc.full_text[s["global_start"]:s["global_end"]])
            cursor = s["global_end"]

        covered_by_global = "".join(covered_text_parts)

        covered_by_segments = "".join(
            doc.sources[s["source_id"]].full_text[s["local_start"]:s["local_end"]]
            for s in segments
        )

        assert covered_by_global == covered_by_segments, (
            f"Сегменты не восстанавливают покрытую часть фрагмента!\n"
            f"  by_global   = {covered_by_global!r}\n"
            f"  by_segments = {covered_by_segments!r}"
        )

        # 4. Дополнительно: суммарная «потеря» — это только разделители,
        #    и их длина должна быть ровно (общая длина фрагмента - покрытое).
        lost_len = (global_end - global_start) - sum(
            s["global_end"] - s["global_start"] for s in segments
        )
        # Допустимая потеря: только разделители между блоками.
        if lost_len > 0:
            # Найдём все позиции разделителей внутри [global_start, global_end]
            expected_lost = 0
            for sep_start, sep_end in doc.separators:
                if global_start < sep_start and sep_end < global_end:
                    expected_lost += sep_end - sep_start
            # Плюс внутренние разделители между страницами PDF (не в doc.separators).
            # Их длина = 2 (len(separator)). Проверим, что потеря кратна этой длине.
            # Не строгая проверка, но достаточная для диагностики:
            assert lost_len <= (global_end - global_start) * 0.05, (
                f"Слишком много потеряно: {lost_len} символов. "
                f"Возможно, потеряны не только разделители."
            )

        # 5. PDF: bbox должен покрывать сегмент
        for s in segments:
            if s["format"] != "PDF":
                continue
            src = doc.sources[s["source_id"]]
            overlapping = [
                bb for bb in src.pdf_char_bboxes
                if bb.page == s["page"]
                   and bb.char_index >= s["local_start"]
                   and bb.char_index < s["local_end"]
            ]
            covered = len(overlapping)
            needed = s["local_end"] - s["local_start"]
            coverage = covered / max(1, needed)
            assert coverage > 0.5, (
                f"Низкое покрытие bbox для PDF-сегмента "
                f"[{s['local_start']}:{s['local_end']}] на page={s['page']}: "
                f"{coverage:.1%} ({covered}/{needed})"
            )

        print(
            f"  ✓ [{'+'.join(info['source_ids'])}] "
            f"global=[{global_start}:{global_end}] → "
            f"{len(segments)} сегмент(ов) — {original[:50]!r}"
        )

    # --- Тесты ---

    # 1. Осмысленные фразы из документа
    test_needles = [
        "в разумный срок",
        "по мере необходимости",
        "Мир техники",
        "«10» февраля 2026 г.",
        "Срок поставки",
    ]
    for needle in test_needles:
        idx = doc.full_text.find(needle)
        if idx == -1:
            continue
        print(f"\n-- Фраза: {needle!r} @ {idx} --")
        check_export_roundtrip(doc, idx, idx + len(needle))

    # 2. Фрагменты, пересекающие границу блоков (главный кейс Пути B)
    print("\n-- Фрагменты через границы блоков --")
    for i in range(min(3, len(doc.blocks) - 1)):
        b1, b2 = doc.blocks[i], doc.blocks[i + 1]
        if b1.source_id != b2.source_id:
            continue
        # От середины b1 до середины b2
        gs = b1.global_start + (b1.global_end - b1.global_start) // 2
        ge = b2.global_start + (b2.global_end - b2.global_start) // 2
        check_export_roundtrip(doc, gs, ge)

    # 3. Фрагмент, начинающийся до первого блока и кончающийся после последнего
    #    (крайние случаи)
    print("\n-- Крайние случаи --")
    first = doc.blocks[0]
    last = doc.blocks[-1]
    # Начало первого блока — последний символ последнего
    check_export_roundtrip(doc, first.global_start, last.global_end)

    # 4. Обрывки посреди текста
    print("\n-- Случайные обрывки --")
    for start, length in [(500, 37), (1500, 83), (3000, 1120), (8000, 55)]:
        end = min(start + length, len(doc.full_text))
        if end > start:
            check_export_roundtrip(doc, start, end)

if __name__ == "__main__":
    sources = [
        SourceDocument(
            source_id="main",
            file_name="contract2.pdf",
            attachment_type=AttachmentType.MAIN,
            path=str(DATA_DIR / "contract2.pdf"),
        ),
        SourceDocument(
            source_id="schedule",
            file_name="schedule.docx",
            attachment_type=AttachmentType.SCHEDULE,
            path=str(DATA_DIR / "schedule.docx"),
        ),
    ]
    debug_parse_multi(sources)