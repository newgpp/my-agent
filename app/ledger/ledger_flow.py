from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.llm.deepseek_client import get_client
from app.mcp.runner import MCPRunner
from app.ledger.asr_extract import (
    build_combined_texts_from_asr,
    build_payloads_from_asr,
)
from app.prompts.loader import load_prompt
from app.ledger.ocr_extract import (
    build_combined_texts_from_ocr,
    build_payloads_from_ocr,
    _normalize_records,
    extract_json,
    truncate_text,
)

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data_uploads"
RECEIPT_DIR = UPLOAD_DIR / "receipts"
VOICE_DIR = UPLOAD_DIR / "voice"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
AUDIO_EXTENSIONS = {".wav", ".m4a"}

LLM_SYSTEM_PROMPT = load_prompt("ledger_extract")

PENDING_LLM_INPUTS: Dict[str, Dict[str, Any]] = {}


class ProcessResponse(BaseModel):
    inserted: int
    results: List[Dict[str, Any]]
    missing_entries: List[Dict[str, Any]]
    combined_texts: List[str]


class LedgerFlowType(str, Enum):
    ASR_LEDGER = "ASR_LEDGER"
    OCR_LEDGER = "OCR_LEDGER"
    TEXT_LEDGER = "TEXT_LEDGER"


async def llm_extract_many(texts: list[str]) -> list[Dict[str, str]]:
    if not texts:
        return []
    try:
        client = get_client()
    except Exception:
        return []
    user_parts: List[str] = []
    append_part = user_parts.append
    for idx, text in enumerate(texts, start=1):
        append_part(f"RECORD {idx}:\n{truncate_text(text)}")
    messages = [
        {"role": "system", "content": LLM_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    try:
        response = await client.chat(messages, temperature=0.1, max_tokens=800)
    except Exception:
        return []
    choices = response.get("choices") or []
    if not choices:
        return []
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    payload = extract_json(content)
    return _normalize_records(payload)


def _ensure_within_allowed(path: Path) -> None:
    settings = get_settings()
    roots = [Path(root).resolve() for root in settings.fs_roots()]
    if not roots:
        raise HTTPException(status_code=500, detail="FS_ALLOWED_DIR_1/2 not configured")
    resolved = path.resolve()
    for root in roots:
        if resolved.is_relative_to(root):
            return
    raise HTTPException(
        status_code=400,
        detail="Upload path is outside allowed directories. Update FS_ALLOWED_DIR_1/2.",
    )


def _make_filename(original: str) -> str:
    suffix = Path(original).suffix.lower()
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex}{suffix}"


def _write_upload_content(filename: str, content: bytes, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _make_filename(filename or "upload.bin")
    target_path = target_dir / safe_name
    _ensure_within_allowed(target_path)
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")
    target_path.write_bytes(content)
    return target_path


def _merge_pending_input(pending_id: str, clarify_text: str) -> List[str]:
    cached_entry = PENDING_LLM_INPUTS.get(pending_id)
    if not cached_entry:
        raise HTTPException(status_code=404, detail="pending_id not found or expired.")
    combined_texts = cached_entry.get("combined_texts", [])
    missing_indices = cached_entry.get("missing_indices", [])
    if not isinstance(combined_texts, list) or not isinstance(missing_indices, list):
        raise HTTPException(status_code=500, detail="pending cache is invalid.")
    if clarify_text:
        for idx in missing_indices:
            if idx < len(combined_texts):
                existing = combined_texts[idx]
                if existing:
                    combined_texts[idx] = f"{existing}\n{clarify_text}"
                else:
                    combined_texts[idx] = clarify_text
        cached_entry["combined_texts"] = combined_texts
        PENDING_LLM_INPUTS[pending_id] = cached_entry
    return combined_texts


def _cache_pending_input(
    pending_id: str,
    combined_texts: List[str],
    missing_indices: List[int],
) -> None:
    PENDING_LLM_INPUTS[pending_id] = {
        "combined_texts": combined_texts,
        "missing_indices": missing_indices,
    }


async def _prepare_upload_path(
    file: Optional[UploadFile],
    flow_type: LedgerFlowType,
) -> str:
    if flow_type is LedgerFlowType.OCR_LEDGER:
        filename = file.filename or "" if file else ""
        content = await file.read() if file else b""
        path = _write_upload_content(filename, content, RECEIPT_DIR)
        return str(path)
    if flow_type is LedgerFlowType.ASR_LEDGER:
        filename = file.filename or "" if file else ""
        content = await file.read() if file else b""
        path = _write_upload_content(filename, content, VOICE_DIR)
        return str(path)
    if flow_type is LedgerFlowType.TEXT_LEDGER:
        return ""
    raise HTTPException(status_code=400, detail="Invalid ledger flow type.")


async def process_ledger(
    file: Optional[UploadFile],
    text: Optional[str],
    runner: MCPRunner,
    flow_type: LedgerFlowType,
    pending_id: Optional[str] = None,
) -> ProcessResponse:
    if pending_id:
        clarify_text = (text or "").strip()
        combined_texts = _merge_pending_input(pending_id, clarify_text)
        upload_path = ""
        text = None
    else:
        upload_path = ""
        combined_texts: List[str] = []
        upload_path = await _prepare_upload_path(file, flow_type)
        if flow_type is LedgerFlowType.TEXT_LEDGER:
            combined_texts = [text] if text else []

    try:
        if not combined_texts:
            if flow_type is LedgerFlowType.ASR_LEDGER:
                combined_texts = await build_combined_texts_from_asr(
                    runner, upload_path, text
                )
            elif flow_type is LedgerFlowType.OCR_LEDGER:
                combined_texts = await build_combined_texts_from_ocr(
                    runner, upload_path, text
                )
            elif flow_type is LedgerFlowType.TEXT_LEDGER:
                combined_texts = [text] if text else []
            else:
                raise HTTPException(status_code=400, detail="Invalid ledger flow type.")
        llm_records = await llm_extract_many(combined_texts)
        if flow_type is LedgerFlowType.ASR_LEDGER:
            payloads, combined_texts = build_payloads_from_asr(
                llm_records,
                combined_texts,
                text,
                source_image="",
                source_audio=upload_path,
            )
        else:
            payloads, combined_texts = build_payloads_from_ocr(
                llm_records,
                combined_texts,
                text,
                source_image=(
                    upload_path if flow_type is LedgerFlowType.OCR_LEDGER else ""
                ),
                source_audio="",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    inserted = 0
    missing_entries: List[Dict[str, Any]] = []
    valid_payloads: List[Dict[str, Any]] = []
    valid_indices: List[int] = []
    results: List[Dict[str, Any]] = [{} for _ in payloads]

    pending_key: Optional[str] = None
    missing_indices: List[int] = []
    for idx, payload in enumerate(payloads):
        missing = [
            field for field in ("date", "merchant", "amount") if not payload.get(field)
        ]
        if missing:
            if pending_key is None:
                pending_key = uuid.uuid4().hex
            missing_indices.append(idx)
            missing_entries.append(
                {"pending_id": pending_key, "missing": missing, "row": payload}
            )
            results[idx] = {
                "status": "skipped",
                "reason": "missing_required_fields",
                "missing": missing,
                "row": payload,
                "pending_id": pending_key,
            }
            continue
        valid_payloads.append(payload)
        valid_indices.append(idx)

    if pending_key:
        _cache_pending_input(pending_key, combined_texts, missing_indices)

    if valid_payloads:
        result = await runner.call_tool(
            "ledger",
            "ledger_upsert_many",
            {"payloads": valid_payloads, "dedupe": True, "csv_path": None},
        )
        if hasattr(result, "model_dump"):
            batch_data = result.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
        else:
            batch_data = result
        tool_results = (
            batch_data.get("results") if isinstance(batch_data, dict) else None
        )
        if isinstance(tool_results, list):
            for idx, item in enumerate(tool_results):
                target_index = valid_indices[idx] if idx < len(valid_indices) else None
                if target_index is not None:
                    results[target_index] = item
                    if isinstance(item, dict) and item.get("status") == "inserted":
                        inserted += 1
        else:
            for target_index in valid_indices:
                results[target_index] = {"status": "inserted"}
                inserted += 1

    if inserted == 0 and missing_entries:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Missing required fields after LLM extraction.",
                "missing_entries": missing_entries,
            },
        )

    return ProcessResponse(
        inserted=inserted,
        results=results,
        missing_entries=missing_entries,
        combined_texts=combined_texts,
    )
