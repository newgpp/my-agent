#!/usr/bin/env python3
"""
Transcribe WAV audio via faster-whisper and output structured JSON.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _load_whisper(model: str, device: str):
    # Ensure HF cache directory is writable in the workspace.
    base_dir = Path(__file__).resolve().parents[3]
    cache_dir = base_dir / "data_uploads" / "hf_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    import os

    os.environ.setdefault("HF_HOME", str(cache_dir))
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError(
            "faster-whisper is not available. Install faster-whisper in the runtime environment."
        ) from exc
    return WhisperModel(model, device=device)


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
    whisper = _load_whisper(model, device)
    segments, info = whisper.transcribe(str(audio_path), language="zh")

    segment_list: List[Dict[str, Any]] = []
    raw_parts: List[str] = []
    for segment in segments:
        segment_list.append(
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "avg_logprob": getattr(segment, "avg_logprob", None),
            }
        )
        raw_parts.append(segment.text)

    raw_text = " ".join(raw_parts).strip()

    extracted = {
        "date": _extract_date(raw_text),
        "amount": _extract_amount(raw_text),
        "currency": _extract_currency(raw_text),
        "merchant": None,
    }

    return {
        "audio_path": str(audio_path),
        "language": getattr(info, "language", None),
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
