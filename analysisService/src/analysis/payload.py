from src.contracts.contract import Contract
from src.parsing.result_model import ParsedDocument

def build_analyzed_event(contract: Contract, version: int) -> dict:
    return {
        "contract_id": contract.contract_id,
        "version": version,
        "contract_date": contract.contract_date,
        "end_date": contract.end_date,
        "attachments_ok": contract.attachments_ok,
        "missing_attachments": contract.missing_attachments,
        "risks": [
            {
                "risk_id": f"risk-{i+1}",
                "risk_type": r.risk_type,
                "severity": r.severity,
                "confidence": r.confidence,
                "status": r.status,
                "description": r.description,
                "recommendation": r.recommendation,
                "fragments": [
                    {
                        "global_start": f.global_start,
                        "global_end": f.global_end,
                        "text": f.text,
                    }
                    for f in r.fragments
                ],
            }
            for i, r in enumerate(contract.risks)
        ],
        "terms": [t.to_export_dict() for t in contract.terms],
    }

def build_export_event(contract: Contract, doc: ParsedDocument, version: int) -> dict:
    risks_payload = []

    for i, risk in enumerate(contract.risks):
        segments = []
        for frag in risk.fragments:
            overlapping = [
                b for b in doc.blocks
                if b.global_start < frag.global_end and b.global_end > frag.global_start
            ]
            for block in overlapping:
                seg_start = max(frag.global_start, block.global_start)
                seg_end = min(frag.global_end, block.global_end)
                if seg_start >= seg_end:
                    continue

                source = doc.sources.get(block.source_id)
                if source is None:
                    continue

                local_start = block.local_start + (seg_start - block.global_start)
                local_end = block.local_start + (seg_end - block.global_start)

                seg = {
                    "source_id": block.source_id,
                    "format": source.format.value,
                    "local_start": local_start,
                    "local_end": local_end,
                    "global_start": seg_start,
                    "global_end": seg_end,
                    "paragraph": None,
                    "table": None,
                    "row": None,
                    "page": None,
                    "pdf_char_offset_start": None,
                    "pdf_char_offset_end": None,
                }

                if source.format.value == "DOCX":
                    seg["paragraph"] = block.paragraph
                    seg["table"] = block.table
                    seg["row"] = block.row
                else:
                    seg["page"] = block.page
                    if block.pdf_char_offset_start is not None:
                        seg["pdf_char_offset_start"] = (
                            block.pdf_char_offset_start + (seg_start - block.global_start)
                        )
                        seg["pdf_char_offset_end"] = (
                            block.pdf_char_offset_start + (seg_end - block.global_start)
                        )

                segments.append(seg)

        risks_payload.append({
            "risk_id": f"risk-{i+1}",
            "risk_type": risk.risk_type,
            "severity": risk.severity,
            "export_segments": segments,
        })

    return {
        "contract_id": contract.contract_id,
        "version": version,
        "sources": [
            {"source_id": sid, "file_path": src.source.path, "format": src.format.value}
            for sid, src in doc.sources.items()
        ],
        "risks": risks_payload,
    }