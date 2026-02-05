from __future__ import annotations

import importlib.util
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.mcp.runner import MCPRunner
from app.services.asr_ledger import build_payloads_from_asr
from app.services.ocr_ledger import build_payloads_from_ocr, normalize_tool_output

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data_uploads"
RECEIPT_DIR = UPLOAD_DIR / "receipts"
VOICE_DIR = UPLOAD_DIR / "voice"
OCR_SCRIPT = BASE_DIR / "skills" / "ocr-ledger" / "scripts" / "ocr_receipt.py"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
AUDIO_EXTENSIONS = {".wav", ".m4a"}


class UploadResponse(BaseModel):
    path: str
    filename: str
    media_type: str


class ToolResponse(BaseModel):
    result: Dict[str, Any]
    media_type: Optional[str] = None


class ProcessResponse(BaseModel):
    upload: Optional[UploadResponse]
    parse: ToolResponse
    upsert: List[ToolResponse]


def get_runner() -> MCPRunner:
    from app.main import mcp_runner

    return mcp_runner


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


def _ocr_receipt_direct(image_path: str) -> Dict[str, Any]:
    spec = importlib.util.spec_from_file_location("ocr_receipt_direct", OCR_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load OCR script: {OCR_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module.run(Path(image_path), "ch")
    if not isinstance(payload, dict):
        raise RuntimeError("OCR direct call returned unexpected payload.")
    return payload


def _should_fallback_ocr(detail: str) -> bool:
    detail = detail.lower()
    return any(
        token in detail
        for token in (
            "failed to resolve",
            "nameresolutionerror",
            "nodename nor servname",
            "connectionerror",
        )
    )


@router.post("/v1/ledger/process", response_model=ProcessResponse)
async def ledger_process(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    model: str = Form("small"),
    device: str = Form("cpu"),
    runner: MCPRunner = Depends(get_runner),
) -> ProcessResponse:
    if not file and not text:
        raise HTTPException(status_code=400, detail="Provide file or text.")

    upload: Optional[UploadResponse] = None
    media_type = "text"
    parse_result: Dict[str, Any]
    raw_result: Any = None

    if file:
        filename = file.filename or ""
        ext = Path(filename).suffix.lower()
        content = await file.read()
        if ext in IMAGE_EXTENSIONS:
            if os.getenv("OCR_DISABLED", "").lower() in ("1", "true", "yes"):
                raise HTTPException(status_code=400, detail="OCR is disabled.")
            path = _write_upload_content(filename, content, RECEIPT_DIR, IMAGE_EXTENSIONS)
            media_type = "image"
        elif ext in AUDIO_EXTENSIONS:
            if os.getenv("ASR_DISABLED", "").lower() in ("1", "true", "yes"):
                raise HTTPException(status_code=400, detail="ASR is disabled.")
            if not shutil.which("ffmpeg"):
                raise HTTPException(
                    status_code=500,
                    detail="ffmpeg is required to decode m4a. Please install ffmpeg on the server.",
                )
            path = _write_upload_content(filename, content, VOICE_DIR, AUDIO_EXTENSIONS)
            media_type = "audio"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")
        upload = UploadResponse(path=str(path), filename=path.name, media_type=media_type)

        if media_type == "image":
            result = await runner.call_tool(
                "ledger",
                "ocr_receipt",
                {"image_path": upload.path},
            )
        else:
            result = await runner.call_tool(
                "ledger",
                "transcribe_audio",
                {"audio_path": upload.path, "model": model, "device": device},
            )

        if hasattr(result, "model_dump"):
            raw_result = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        else:
            raw_result = result
        parse_result = normalize_tool_output(raw_result)
    if not file:
        cleaned_text = (text or "").strip()
        parse_result = {"raw_text": cleaned_text}

    parse = ToolResponse(result=parse_result, media_type=media_type)
    if isinstance(raw_result, dict) and raw_result.get("isError"):
        content = parse.result.get("content")
        detail = content[0].get("text") if isinstance(content, list) and content else "Tool execution failed."
        if media_type == "image" and _should_fallback_ocr(detail):
            direct_payload = _ocr_receipt_direct(upload.path)
            parse_result = normalize_tool_output(direct_payload)
            parse = ToolResponse(result=parse_result, media_type=media_type)
            raw_result = direct_payload
        else:
            raise HTTPException(status_code=500, detail=detail)

    upserts: List[ToolResponse] = []
    inserted = 0
    missing_entries: List[Dict[str, Any]] = []
    try:
        if media_type == "audio":
            payloads = await build_payloads_from_asr(
                parse.result,
                text,
                source_image="",
                source_audio=upload.path if upload and upload.media_type == "audio" else "",
            )
        else:
            payloads = await build_payloads_from_ocr(
                parse.result,
                text,
                source_image=upload.path if upload and upload.media_type == "image" else "",
                source_audio=upload.path if upload and upload.media_type == "audio" else "",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    indexed_valid_payloads: List[Dict[str, Any]] = []
    valid_indices: List[int] = []
    upserts = [ToolResponse(result={}) for _ in payloads]
    for idx, payload in enumerate(payloads):
        missing = [field for field in ("date", "merchant", "amount") if not payload.get(field)]
        if missing:
            missing_entries.append({"missing": missing, "row": payload})
            upserts[idx] = ToolResponse(
                result={
                    "status": "skipped",
                    "reason": "missing_required_fields",
                    "missing": missing,
                    "row": payload,
                }
            )
            continue
        indexed_valid_payloads.append(payload)
        valid_indices.append(idx)

    if indexed_valid_payloads:
        result = await runner.call_tool(
            "ledger",
            "ledger_upsert_many",
            {"payloads": indexed_valid_payloads, "dedupe": True, "csv_path": None},
        )
        if hasattr(result, "model_dump"):
            batch_data = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        else:
            batch_data = result
        results = batch_data.get("results") if isinstance(batch_data, dict) else None
        if isinstance(results, list):
            for idx, item in enumerate(results):
                target_index = valid_indices[idx] if idx < len(valid_indices) else None
                if target_index is not None:
                    upserts[target_index] = ToolResponse(result=item)
                    if isinstance(item, dict) and item.get("status") == "inserted":
                        inserted += 1
        else:
            # Fallback: if response format unexpected, mark all valid entries as inserted.
            for target_index in valid_indices:
                upserts[target_index] = ToolResponse(result={"status": "inserted"})
                inserted += 1

    if inserted == 0 and missing_entries:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Missing required fields after LLM extraction.",
                "missing_entries": missing_entries,
            },
        )

    return ProcessResponse(upload=upload, parse=parse, upsert=upserts)
