import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from groq import Groq
import httpx
from loguru import logger
from mcp.server.fastmcp import FastMCP

import base64
import requests

mcp = FastMCP("ledger")
load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
LEDGER_CSV = BASE_DIR / "data" / "ledger.csv"

LEDGER_FIELDS = [
    "date",
    "merchant",
    "amount",
    "currency",
    "category",
    "payment_method",
    "note",
    "source_image",
    "source_audio",
    "insert_time",
]

REQUIRED_FIELDS = {"date", "merchant", "amount"}
AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,?\d{3})*(?:\.\d{1,2})?)(?!\d)")
DATE_RE = re.compile(r"(20\d{2}[/-]\d{1,2}[/-]\d{1,2})")
DATE_CN_RE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")

CURRENCY_HINTS = {
    "美元": "USD",
    "美金": "USD",
    "人民币": "CNY",
    "块": "CNY",
    "元": "CNY",
}

_GROQ_HTTP_CLIENT: Optional[httpx.Client] = None


def _get_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


@lru_cache(maxsize=1)
def _get_groq_client() -> Groq:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY")
    proxy_url = (os.getenv("GROQ_PROXY_URL") or "").strip()
    if proxy_url:
        global _GROQ_HTTP_CLIENT
        if _GROQ_HTTP_CLIENT is None:
            _GROQ_HTTP_CLIENT = httpx.Client(
                proxies={
                    "http://": proxy_url,
                    "https://": proxy_url,
                }
            )
        return Groq(api_key=api_key, http_client=_GROQ_HTTP_CLIENT)
    return Groq(api_key=api_key)


def _read_file_base64(path: Path) -> str:
    data = path.read_bytes()
    if not data:
        raise RuntimeError("Image is empty.")
    return base64.b64encode(data).decode("ascii")


def _file_type(path: Path) -> int:
    return 0 if path.suffix.lower() == ".pdf" else 1

def _call_ocr_api(image_path: Path, lang: str) -> Dict[str, Any]:
    api_url = _get_env("OCR_API_URL")
    token = _get_env("OCR_API_TOKEN")
    payload: Dict[str, Any] = {
        "file": _read_file_base64(image_path),
        "fileType": _file_type(image_path),
        "useDocOrientationClassify": False,
        "useDocUnwarping": False,
        "useTextlineOrientation": False,
    }
    headers = {"Authorization": f"token {token}", "Content-Type": "application/json"}
    resp = requests.post(api_url, json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"OCR API error {resp.status_code}: {resp.text}")
    data = resp.json()
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError("OCR API response missing result payload.")
    return result


def _extract_lines_from_api(result: Dict[str, Any]) -> list[Dict[str, Any]]:
    lines: list[Dict[str, Any]] = []
    ocr_results = result.get("ocrResults") or []
    if isinstance(ocr_results, list):
        for item in ocr_results:
            if not isinstance(item, dict):
                continue
            pruned = item.get("prunedResult")
            if not isinstance(pruned, dict):
                continue
            rec_texts = pruned.get("rec_texts")
            rec_boxes = pruned.get("rec_boxes")
            if not isinstance(rec_boxes, list):
                rec_boxes = None
            if not isinstance(rec_texts, list):
                continue
            for idx, raw in enumerate(rec_texts):
                if not isinstance(raw, str):
                    continue
                text = raw.strip()
                if text:
                    entry = {"text": text, "score": None}
                    if rec_boxes and idx < len(rec_boxes) and isinstance(rec_boxes[idx], list):
                        entry["bbox"] = rec_boxes[idx]
                    lines.append(entry)
    return lines


def _resolve_groq_model(model: str) -> str:
    if model in ("whisper-large-v3", "whisper-large-v3-turbo"):
        return model
    if model in ("small", "base", "medium", "large"):
        return "whisper-large-v3-turbo"
    return os.getenv("GROQ_ASR_MODEL", "whisper-large-v3-turbo")


def _extract_date(text: str) -> Optional[str]:
    match = DATE_RE.search(text)
    if match:
        return match.group(1).replace("/", "-")
    match_cn = DATE_CN_RE.search(text)
    if match_cn:
        year, month, day = match_cn.groups()
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return None


def _extract_amount(text: str) -> Optional[str]:
    matches = AMOUNT_RE.findall(text)
    if not matches:
        return None
    return matches[-1]


def _extract_currency(text: str) -> Optional[str]:
    for hint, currency in CURRENCY_HINTS.items():
        if hint in text:
            return currency
    return None


def _ensure_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import csv

    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
            writer.writeheader()
        return

    # If file exists but header is missing new columns, rewrite with updated header.
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        existing_fields = reader.fieldnames or []
        rows = list(reader)
    if "insert_time" in existing_fields:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        writer.writeheader()
        for row in rows:
            row.setdefault("insert_time", "")
            writer.writerow(row)


def _validate_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    normalized = {key: "" if payload.get(key) is None else str(payload.get(key)) for key in LEDGER_FIELDS}
    missing = [field for field in REQUIRED_FIELDS if not normalized.get(field)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    return normalized


def _basename(value: str) -> str:
    return Path(value).name if value else ""


@mcp.tool()
def ocr_receipt(image_path: str, lang: str = "ch") -> Dict[str, Any]:
    """Run PaddleOCR on a receipt image and return structured JSON."""
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    result = _call_ocr_api(path, lang)
    lines = _extract_lines_from_api(result)
    raw_text = "\n".join(line["text"] for line in lines)
    return {
        "image_path": str(path),
        "raw_text": raw_text,
        "lines": lines,
    }


@mcp.tool()
def transcribe_audio(audio_path: str, model: str = "small", device: str = "cpu") -> Dict[str, Any]:
    """Transcribe audio via Groq Whisper and return structured JSON."""
    client = _get_groq_client()
    groq_model = _resolve_groq_model(model)
    path = Path(audio_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Audio not found: {path}")
    with path.open("rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(path.name, file.read()),
            model=groq_model,
            language="zh",
            response_format="verbose_json",
        )

    if isinstance(transcription, dict):
        raw_text = (transcription.get("text") or "").strip()
        segment_list = transcription.get("segments") or []
    else:
        raw_text = (getattr(transcription, "text", "") or "").strip()
        segment_list = getattr(transcription, "segments", []) or []

    extracted = {
        "date": _extract_date(raw_text),
        "amount": _extract_amount(raw_text),
        "currency": _extract_currency(raw_text),
        "merchant": None,
    }

    return {
        "audio_path": str(path),
        "language": "zh",
        "raw_text": raw_text,
        "segments": segment_list,
        "extracted": extracted,
    }


@mcp.tool()
def ledger_upsert(payload: Dict[str, Any], dedupe: bool = True, csv_path: Optional[str] = None) -> Dict[str, Any]:
    """Append a ledger record to CSV."""
    csv_path = Path(csv_path).expanduser().resolve() if csv_path else LEDGER_CSV
    row = _validate_payload(payload)
    row["source_image"] = _basename(row.get("source_image", ""))
    row["source_audio"] = _basename(row.get("source_audio", ""))
    if not row.get("insert_time"):
        from datetime import datetime

        row["insert_time"] = datetime.now().isoformat()
    _ensure_csv(csv_path)

    import csv

    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        writer.writerow(row)

    return {"status": "inserted", "csv_path": str(csv_path), "row": row}


@mcp.tool()
def ledger_upsert_many(
    payloads: list[Dict[str, Any]],
    dedupe: bool = True,
    csv_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Append multiple ledger records to CSV."""
    csv_path = Path(csv_path).expanduser().resolve() if csv_path else LEDGER_CSV
    _ensure_csv(csv_path)

    import csv

    results: list[Dict[str, Any]] = []
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        for payload in payloads:
            row = _validate_payload(payload)
            row["source_image"] = _basename(row.get("source_image", ""))
            row["source_audio"] = _basename(row.get("source_audio", ""))
            if not row.get("insert_time"):
                from datetime import datetime

                row["insert_time"] = datetime.now().isoformat()
            writer.writerow(row)
            results.append({"status": "inserted", "csv_path": str(csv_path), "row": row})

    return {"results": results}


if __name__ == "__main__":
    logger.info("Starting Ledger MCP server")
    mcp.run()
