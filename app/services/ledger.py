from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.mcp.runner import MCPRunner
from app.services.asr_ledger import build_payloads_from_asr, parse_audio
from app.services.ocr_ledger import build_payloads_from_ocr, parse_image

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data_uploads"
RECEIPT_DIR = UPLOAD_DIR / "receipts"
VOICE_DIR = UPLOAD_DIR / "voice"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
AUDIO_EXTENSIONS = {".wav", ".m4a"}


class ProcessResponse(BaseModel):
    inserted: int
    results: List[Dict[str, Any]]
    missing_entries: List[Dict[str, Any]]


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


def _validate_extension(filename: str, allowed: set[str]) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")


def _write_upload_content(filename: str, content: bytes, target_dir: Path, allowed_exts: set[str]) -> Path:
    _validate_extension(filename, allowed_exts)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _make_filename(filename or "upload.bin")
    target_path = target_dir / safe_name
    _ensure_within_allowed(target_path)
    if not content:
        raise HTTPException(status_code=400, detail="Empty upload")
    target_path.write_bytes(content)
    return target_path


async def process_ledger_request(
    file: Optional[UploadFile],
    text: Optional[str],
    runner: MCPRunner,
) -> ProcessResponse:
    if not file and not text:
        raise HTTPException(status_code=400, detail="Provide file or text.")

    upload_path = ""
    media_type = "text"
    parse_result: Dict[str, Any]

    if file:
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()
        content = await file.read()
        if ext in IMAGE_EXTENSIONS:
            path = _write_upload_content(filename, content, RECEIPT_DIR, IMAGE_EXTENSIONS)
            media_type = "image"
        elif ext in AUDIO_EXTENSIONS:
            path = _write_upload_content(filename, content, VOICE_DIR, AUDIO_EXTENSIONS)
            media_type = "audio"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        upload_path = str(path)

        if media_type == "image":
            parse_result = await parse_image(runner, upload_path, "ch")
        else:
            parse_result = await parse_audio(runner, upload_path)
    else:
        cleaned_text = (text or "").strip()
        parse_result = {"raw_text": cleaned_text}

    if isinstance(parse_result, dict) and parse_result.get("isError"):
        content = parse_result.get("content")
        detail = content[0].get("text") if isinstance(content, list) and content else "Tool execution failed."
        raise HTTPException(status_code=500, detail=detail)

    try:
        if media_type == "audio":
            payloads = await build_payloads_from_asr(
                parse_result,
                text,
                source_image="",
                source_audio=upload_path if media_type == "audio" else "",
            )
        else:
            payloads = await build_payloads_from_ocr(
                parse_result,
                text,
                source_image=upload_path if media_type == "image" else "",
                source_audio=upload_path if media_type == "audio" else "",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    inserted = 0
    missing_entries: List[Dict[str, Any]] = []
    valid_payloads: List[Dict[str, Any]] = []
    valid_indices: List[int] = []
    results: List[Dict[str, Any]] = [{} for _ in payloads]

    for idx, payload in enumerate(payloads):
        missing = [field for field in ("date", "merchant", "amount") if not payload.get(field)]
        if missing:
            missing_entries.append({"missing": missing, "row": payload})
            results[idx] = {
                "status": "skipped",
                "reason": "missing_required_fields",
                "missing": missing,
                "row": payload,
            }
            continue
        valid_payloads.append(payload)
        valid_indices.append(idx)

    if valid_payloads:
        result = await runner.call_tool(
            "ledger",
            "ledger_upsert_many",
            {"payloads": valid_payloads, "dedupe": True, "csv_path": None},
        )
        if hasattr(result, "model_dump"):
            batch_data = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        else:
            batch_data = result
        tool_results = batch_data.get("results") if isinstance(batch_data, dict) else None
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

    return ProcessResponse(inserted=inserted, results=results, missing_entries=missing_entries)
