from __future__ import annotations

import json
import re
import importlib.util
import os
import shutil
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import get_settings
from app.prompts.loader import load_prompt
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


LLM_SYSTEM_PROMPT = load_prompt("ledger_extract")

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


_TIME_RE = re.compile(r"(上午|下午)?\d{1,2}:\d{2}")
_AMOUNT_RE = re.compile(r"[¥￥]\s*\d+(?:\.\d{1,2})?")
_DATE_RE = re.compile(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}")
_PAYMENT_HINT_RE = re.compile(r"(微信|支付宝|云闪付)")


def _extract_lines(parse_result: Dict[str, Any]) -> List[str]:
    lines = parse_result.get("lines")
    if isinstance(lines, list) and lines:
        extracted: List[str] = []
        for item in lines:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    extracted.append(text.strip())
            elif isinstance(item, str) and item.strip():
                extracted.append(item.strip())
        if extracted:
            return extracted
    raw_text = parse_result.get("raw_text")
    if isinstance(raw_text, str) and raw_text.strip():
        return [line.strip() for line in raw_text.splitlines() if line.strip()]
    return []


def _extract_date_context(lines: List[str]) -> List[str]:
    context: List[str] = []
    for line in lines:
        if _DATE_RE.search(line):
            context.append(line)
    return context


def _extract_payment_context(lines: List[str]) -> List[str]:
    context: List[str] = []
    for line in lines:
        if _PAYMENT_HINT_RE.search(line):
            context.append(line)
    return context


def _split_receipt_entries(lines: List[str]) -> List[List[str]]:
    if not lines:
        return []
    noise_lines = {"我的账单", "支付服务", "摇优惠", "日报设置"}
    filtered = [line for line in lines if line.strip() and line.strip() not in noise_lines]
    if not filtered:
        return []

    time_indices = [i for i, line in enumerate(filtered) if _TIME_RE.search(line)]
    amount_indices = [i for i, line in enumerate(filtered) if _AMOUNT_RE.search(line)]
    detail_indices = {i for i, line in enumerate(filtered) if "账单详情" in line}

    # If no time/amount signals, fall back to a single segment.
    if not time_indices or not amount_indices:
        return [filtered]

    max_gap = 7  # amount should appear within a small window after the time line
    lead_window = 4  # include small lead-in context before time (e.g., 微信支付)
    segments: List[List[str]] = []
    last_end = 0
    for idx, time_idx in enumerate(time_indices):
        next_time = time_indices[idx + 1] if idx + 1 < len(time_indices) else len(filtered)
        # Find the first amount after this time within window.
        amount_idx = None
        for ai in amount_indices:
            if ai < time_idx:
                continue
            if ai - time_idx <= max_gap:
                amount_idx = ai
                break
            if ai > next_time:
                break
        if amount_idx is None:
            # No nearby amount; skip this time marker to avoid false segments.
            continue

        # Segment end: prefer the first "账单详情" after amount, otherwise next time.
        end_idx = next_time
        for di in range(amount_idx, next_time):
            if di in detail_indices:
                end_idx = di + 1
                break
        # Include a small lead-in context before time but don't cross previous segment.
        lead_start = max(last_end, time_idx - lead_window)
        lead_segment = filtered[lead_start:time_idx]
        segment = [line for line in lead_segment + filtered[time_idx:end_idx] if "账单详情" not in line]
        if segment:
            segments.append(segment)
            last_end = end_idx

    if segments:
        return segments
    return [filtered]


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
    for key in ("date", "merchant", "amount", "currency", "category", "payment_method"):
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
    lines_for_llm: List[str] = []
    if isinstance(parse.result, dict):
        raw_text = parse.result.get("raw_text")
        if isinstance(raw_text, str):
            text_for_llm = raw_text
        lines_for_llm = _extract_lines(parse.result)
    if text:
        text_for_llm = f"{text_for_llm}\n{text}".strip() if text_for_llm else text.strip()

    if not text_for_llm and not lines_for_llm:
        raise HTTPException(status_code=400, detail="No OCR/transcript/text available for extraction.")

    segments = _split_receipt_entries(lines_for_llm)
    if len(segments) <= 1:
        segments = [lines_for_llm] if lines_for_llm else [text_for_llm.splitlines()]

    date_context = _extract_date_context(lines_for_llm)
    payment_context = _extract_payment_context(lines_for_llm)
    upserts: List[ToolResponse] = []
    inserted = 0
    missing_entries: List[Dict[str, Any]] = []
    for segment in segments:
        segment_text = "\n".join(segment).strip()
        if not segment_text:
            continue
        combined_text = segment_text
        if date_context:
            combined_text = "\n".join(date_context) + "\n" + combined_text
        if payment_context and not _PAYMENT_HINT_RE.search(combined_text):
            combined_text = "\n".join(payment_context) + "\n" + combined_text
        if text:
            combined_text = f"{combined_text}\n{text}".strip()
        llm_fields = await _llm_extract_fields(combined_text)
        payload: Dict[str, Any] = {
            "date": llm_fields.get("date") or "",
            "merchant": llm_fields.get("merchant") or "",
            "amount": llm_fields.get("amount") or "",
            "currency": llm_fields.get("currency") or "",
            "category": llm_fields.get("category") or "",
            "payment_method": llm_fields.get("payment_method") or "",
            "note": text.strip() if text else "",
            "source_image": upload.path if upload and upload.media_type == "image" else "",
            "source_audio": upload.path if upload and upload.media_type == "audio" else "",
        }
        if not payload.get("date"):
            payload["date"] = date.today().isoformat()
        missing = [field for field in ("date", "merchant", "amount") if not payload.get(field)]
        if missing:
            missing_entries.append({"missing": missing, "row": payload})
            upserts.append(
                ToolResponse(
                    result={
                        "status": "skipped",
                        "reason": "missing_required_fields",
                        "missing": missing,
                        "row": payload,
                    }
                )
            )
            continue
        result = await runner.call_tool(
            "ledger",
            "ledger_upsert",
            {"payload": payload, "dedupe": True, "csv_path": None},
        )
        if hasattr(result, "model_dump"):
            upsert_data = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        else:
            upsert_data = result
        upserts.append(ToolResponse(result=upsert_data))
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
