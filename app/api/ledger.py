from __future__ import annotations

import json
import importlib.util
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.mcp.runner import MCPRunner
from app.llm.deepseek_client import DeepSeekClient

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
    upsert: ToolResponse


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


LLM_SYSTEM_PROMPT = (
    "Extract receipt fields from the user's text. "
    "Return ONLY JSON with keys: date, merchant, amount, currency. "
    "Use YYYY-MM-DD for date. If unknown, return empty string."
)

def _truncate_text(text: str, limit: int = 800) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit]


def _extract_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return {}


def _normalize_tool_output(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    if "extracted" in result:
        return result
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0] if isinstance(content[0], dict) else {}
        text = first.get("text") if isinstance(first, dict) else None
        if isinstance(text, str):
            payload = _extract_json(text)
            if isinstance(payload, dict) and payload:
                return payload
    return result


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


async def _llm_extract_fields(text: str) -> Dict[str, str]:
    try:
        client = DeepSeekClient()
    except Exception:
        return {}
    messages = [
        {"role": "system", "content": LLM_SYSTEM_PROMPT},
        {"role": "user", "content": _truncate_text(text)},
    ]
    try:
        response = await client.chat(messages, temperature=0.1, max_tokens=120)
    except Exception:
        return {}
    choices = response.get("choices") or []
    if not choices:
        return {}
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    payload = _extract_json(content)
    result = {}
    for key in ("date", "merchant", "amount", "currency"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if value is None:
            result[key] = ""
        else:
            result[key] = str(value)
    return result


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
        parse_result = _normalize_tool_output(raw_result)
    if not file:
        cleaned_text = (text or "").strip()
        parse_result = {"raw_text": cleaned_text}

    parse = ToolResponse(result=parse_result, media_type=media_type)
    if isinstance(raw_result, dict) and raw_result.get("isError"):
        content = parse.result.get("content")
        detail = content[0].get("text") if isinstance(content, list) and content else "Tool execution failed."
        if media_type == "image" and _should_fallback_ocr(detail):
            direct_payload = _ocr_receipt_direct(upload.path)
            parse_result = _normalize_tool_output(direct_payload)
            parse = ToolResponse(result=parse_result, media_type=media_type)
            raw_result = direct_payload
        else:
            raise HTTPException(status_code=500, detail=detail)

    text_for_llm = ""
    if isinstance(parse.result, dict):
        raw_text = parse.result.get("raw_text")
        if isinstance(raw_text, str):
            text_for_llm = raw_text
    if text:
        text_for_llm = f"{text_for_llm}\n{text}".strip() if text_for_llm else text.strip()

    if not text_for_llm:
        raise HTTPException(status_code=400, detail="No OCR/transcript/text available for extraction.")

    llm_fields = await _llm_extract_fields(text_for_llm)
    payload: Dict[str, Any] = {
        "date": llm_fields.get("date") or "",
        "merchant": llm_fields.get("merchant") or "",
        "amount": llm_fields.get("amount") or "",
        "currency": llm_fields.get("currency") or "",
        "category": "",
        "payment_method": "",
        "note": text.strip() if text else "",
        "source_image": upload.path if upload and upload.media_type == "image" else "",
        "source_audio": upload.path if upload and upload.media_type == "audio" else "",
    }
    missing = [field for field in ("date", "merchant", "amount") if not payload.get(field)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail={"message": "Missing required fields after LLM extraction.", "missing": missing},
        )

    result = await runner.call_tool(
        "ledger",
        "ledger_upsert",
        {"payload": payload, "dedupe": True, "csv_path": None},
    )
    if hasattr(result, "model_dump"):
        upsert_data = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    else:
        upsert_data = result
    upsert = ToolResponse(result=upsert_data)

    return ProcessResponse(upload=upload, parse=parse, upsert=upsert)
