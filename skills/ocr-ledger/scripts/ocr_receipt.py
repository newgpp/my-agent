#!/usr/bin/env python3
"""
Call remote OCR API on a receipt image and output structured JSON.
"""

import argparse
import json
import base64
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")


def _get_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _read_file_base64(path: Path) -> str:
    data = path.read_bytes()
    if not data:
        raise RuntimeError("Image is empty.")
    return base64.b64encode(data).decode("ascii")


def _file_type(path: Path) -> int:
    if path.suffix.lower() == ".pdf":
        return 0
    return 1


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
    api_ip = (os.getenv("OCR_API_IP") or "").strip()
    if api_ip:
        parsed = urlparse(api_url)
        host = (os.getenv("OCR_API_HOST") or parsed.netloc).strip()
        if not host:
            raise RuntimeError("OCR_API_HOST is required when OCR_API_IP is set.")
        api_url = f"{parsed.scheme}://{api_ip}{parsed.path}"
        headers["Host"] = host
    timeout = 60
    resp = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        raise RuntimeError(f"OCR API error {resp.status_code}: {resp.text}")
    data = resp.json()
    result = data.get("result") if isinstance(data, dict) else None
    if not isinstance(result, dict):
        raise RuntimeError("OCR API response missing result payload.")
    return result


def _extract_lines_from_api(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    ocr_results = result.get("ocrResults") or []
    if isinstance(ocr_results, list):
        for item in ocr_results:
            if not isinstance(item, dict):
                continue
            pruned = item.get("prunedResult")
            if not isinstance(pruned, dict):
                continue
            rec_texts = pruned.get("rec_texts")
            if not isinstance(rec_texts, list):
                continue
            for raw in rec_texts:
                if not isinstance(raw, str):
                    continue
                text = raw.strip()
                if text:
                    lines.append({"text": text, "score": None})
    return lines


def run(image_path: Path, lang: str) -> Dict[str, Any]:
    result = _call_ocr_api(image_path, lang)
    lines = _extract_lines_from_api(result)
    raw_text = "\n".join(line["text"] for line in lines)

    return {
        "image_path": str(image_path),
        "raw_text": raw_text,
        "lines": lines,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, help="Absolute path to receipt image")
    parser.add_argument("--lang", default="ch", help="PaddleOCR language (default: ch)")
    parser.add_argument("--output", default="-", help="Output JSON file or '-' for stdout")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        print(f"[ERROR] Image not found: {image_path}", file=sys.stderr)
        return 1

    payload = run(image_path, args.lang)
    output_text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output == "-":
        print(output_text)
        return 0

    output_path = Path(args.output).expanduser().resolve()
    output_path.write_text(output_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
