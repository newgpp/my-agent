from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from app.services.ledger_extract import llm_extract_many
from app.services.ocr_ledger import (
    PAYMENT_HINT_RE,
    extract_date_context,
    extract_payment_context,
    split_receipt_entries,
)


def _lines_from_text(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


async def build_payloads_from_asr(
    parse_result: Dict[str, Any],
    text: Optional[str],
    source_image: str,
    source_audio: str,
) -> List[Dict[str, Any]]:
    raw_text = parse_result.get("raw_text") if isinstance(parse_result, dict) else ""
    text_for_llm = raw_text.strip() if isinstance(raw_text, str) else ""
    if text:
        text_for_llm = f"{text_for_llm}\n{text}".strip() if text_for_llm else text.strip()

    if not text_for_llm:
        raise ValueError("No ASR/text available for extraction.")

    lines_for_llm = _lines_from_text(text_for_llm)
    segments = split_receipt_entries(lines_for_llm)
    if len(segments) <= 1:
        segments = [lines_for_llm]

    date_context = extract_date_context(lines_for_llm)
    payment_context = extract_payment_context(lines_for_llm)
    combined_texts: List[str] = []
    for segment in segments:
        segment_text = "\n".join(segment).strip()
        if not segment_text:
            continue
        combined_text = segment_text
        if date_context:
            combined_text = "\n".join(date_context) + "\n" + combined_text
        if payment_context and not PAYMENT_HINT_RE.search(combined_text):
            combined_text = "\n".join(payment_context) + "\n" + combined_text
        if text:
            combined_text = f"{combined_text}\n{text}".strip()
        combined_texts.append(combined_text)

    llm_records = await llm_extract_many(combined_texts)
    payloads: List[Dict[str, Any]] = []
    for idx, _ in enumerate(combined_texts):
        llm_fields = llm_records[idx] if idx < len(llm_records) else {}
        payload: Dict[str, Any] = {
            "date": llm_fields.get("date") or "",
            "merchant": llm_fields.get("merchant") or "",
            "amount": llm_fields.get("amount") or "",
            "currency": llm_fields.get("currency") or "",
            "category": llm_fields.get("category") or "",
            "payment_method": llm_fields.get("payment_method") or "",
            "note": text.strip() if text else "",
            "source_image": source_image,
            "source_audio": source_audio,
        }
        if not payload.get("date"):
            payload["date"] = date.today().isoformat()
        payloads.append(payload)
    return payloads
