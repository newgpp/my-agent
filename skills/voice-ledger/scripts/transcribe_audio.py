#!/usr/bin/env python3
"""
Transcribe audio via Groq Whisper and output structured JSON.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import os

from groq import Groq

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


def run(audio_path: Path, model: str, device: str) -> Dict[str, Any]:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY")
    client = Groq(api_key=api_key)
    groq_model = _resolve_groq_model(model)
    with audio_path.open("rb") as file:
        transcription = client.audio.transcriptions.create(
            file=(audio_path.name, file.read()),
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
        "audio_path": str(audio_path),
        "language": "zh",
        "raw_text": raw_text,
        "segments": segment_list,
        "extracted": extracted,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, help="Absolute path to WAV audio")
    parser.add_argument("--model", default="small", help="faster-whisper model size")
    parser.add_argument("--device", default="cpu", help="cpu or cuda")
    parser.add_argument("--output", default="-", help="Output JSON file or '-' for stdout")
    args = parser.parse_args()

    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        print(f"[ERROR] Audio not found: {audio_path}", file=sys.stderr)
        return 1

    payload = run(audio_path, args.model, args.device)
    output_text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output == "-":
        print(output_text)
        return 0

    output_path = Path(args.output).expanduser().resolve()
    output_path.write_text(output_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
