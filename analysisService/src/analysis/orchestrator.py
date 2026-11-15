from __future__ import annotations

from src.analysis.parser import parse_llm_response
from src.contracts.contract import Contract
from src.contracts.source import SourceDocument
from src.analysis.llm.client import call_gigachat
from src.analysis.llm.prompts import build_system_prompt, build_user_prompt
from src.parsing.result_model import ParsedDocument
from src.preprocessing.terms.attachments import detect_missing_attachments
from src.preprocessing.extractor import preprocess


def analyze(doc: ParsedDocument, sources: list[SourceDocument], contract_id: str, call_llm: bool = True) -> Contract | None:

    result = preprocess(doc)

    missing = detect_missing_attachments(doc, sources)
    attachments_ok = len(missing) == 0
    missing_names = [m.referenced_name for m in missing]

    if not call_llm:
        return None

    system = build_system_prompt()
    user = build_user_prompt(result, doc.full_text)

    try:
        raw = call_gigachat(system, user)
    except Exception as e:
        raise RuntimeError(f"GigaChat error: {e}") from e

    candidates_by_risk = {
        rt: result.fragments_for(rt)
        for rt in result.risk_types_checked
    }

    contract = parse_llm_response(
        raw=raw,
        full_text=doc.full_text,
        contract_id=contract_id,
        candidates_by_risk=candidates_by_risk,
        attachments_ok=attachments_ok,
        missing_attachments=missing_names,
    )

    return contract