#!/usr/bin/env python3
"""
Run PaddleOCR on a receipt image and output structured JSON.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

KEYWORDS_AMOUNT = (
    "合计",
    "总计",
    "金额",
    "应付",
    "应收",
    "实收",
    "付款",
    "小计",
    "TOTAL",
    "AMOUNT",
    "PAY",
)

CURRENCY_MAP = {
    "¥": "CNY",
    "￥": "CNY",
    "CNY": "CNY",
    "RMB": "CNY",
    "$": "USD",
    "USD": "USD",
    "US$": "USD",
}

AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,?\d{3})*(?:\.\d{1,2})?)(?!\d)")
DATE_RE = re.compile(r"(20\d{2}[/-]\d{1,2}[/-]\d{1,2})")
DATE_CN_RE = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")


def _load_paddleocr(lang: str):
    # Ensure PaddleX cache directory is writable in the workspace.
    base_dir = Path(__file__).resolve().parents[3]
    cache_dir = base_dir / "data_uploads" / "paddlex_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddleocr import PaddleOCR
    except Exception as exc:
        raise RuntimeError(
            "PaddleOCR is not available. Install paddleocr in the runtime environment."
        ) from exc
    ocr_version = os.getenv("PADDLE_OCR_VERSION", "PP-OCRv5")
    return PaddleOCR(
        lang=lang,
        ocr_version=ocr_version,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _flatten_result(result: Any) -> List[Any]:
    if not result:
        return []
    if isinstance(result, list):
        if result and isinstance(result[0], list) and len(result[0]) == 2:
            return result
        flattened: List[Any] = []
        for page in result:
            if isinstance(page, list):
                flattened.extend(page)
        return flattened
    return []


def _extract_lines(result: Any) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    for item in _flatten_result(result):
        if not isinstance(item, list) or len(item) < 2:
            continue
        text = None
        score = None
        meta = item[1]
        if isinstance(meta, (list, tuple)) and meta:
            text = meta[0]
            if len(meta) > 1:
                score = meta[1]
        if not text:
            continue
        lines.append({"text": str(text), "score": score})
    return lines


def _find_currency(lines: List[Dict[str, Any]]) -> Optional[str]:
    for line in lines:
        text = line["text"]
        for symbol, currency in CURRENCY_MAP.items():
            if symbol in text:
                return currency
    return None


def _extract_date(lines: List[Dict[str, Any]]) -> Optional[str]:
    for line in lines:
        text = line["text"]
        match = DATE_RE.search(text)
        if match:
            return match.group(1).replace("/", "-")
        match_cn = DATE_CN_RE.search(text)
        if match_cn:
            year, month, day = match_cn.groups()
            return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return None


def _extract_amount(lines: List[Dict[str, Any]]) -> Optional[str]:
    candidates: List[Tuple[float, str]] = []
    for line in lines:
        text = line["text"]
        matches = AMOUNT_RE.findall(text)
        if not matches:
            continue
        is_keyword_line = any(keyword in text for keyword in KEYWORDS_AMOUNT)
        has_currency = any(symbol in text for symbol in CURRENCY_MAP)
        if not (is_keyword_line or has_currency):
            continue
        for match in matches:
            value = float(match.replace(",", ""))
            candidates.append((value, match))

    if not candidates:
        return None
    best = max(candidates, key=lambda item: item[0])
    return best[1]


def _extract_merchant(lines: List[Dict[str, Any]]) -> Optional[str]:
    for line in lines:
        text = line["text"].strip()
        if not text:
            continue
        if any(keyword in text for keyword in KEYWORDS_AMOUNT):
            continue
        if AMOUNT_RE.search(text):
            continue
        if len(text) > 30:
            continue
        return text
    return None


def run(image_path: Path, lang: str) -> Dict[str, Any]:
    ocr = _load_paddleocr(lang)
    # Downscale large images to speed up OCR.
    image_input: Any = str(image_path)
    use_path = os.getenv("PADDLE_OCR_USE_PATH", "0").lower() in ("1", "true", "yes")
    if not use_path:
        try:
            from PIL import Image, ImageEnhance, ImageOps, ImageStat
            import numpy as np

            with Image.open(image_path) as img:
                img = img.convert("RGB")
                if os.getenv("PADDLE_OCR_PREPROCESS", "1").lower() in ("1", "true", "yes"):
                    gray = ImageOps.grayscale(img)
                    if ImageStat.Stat(gray).mean[0] < 80:
                        gray = ImageOps.invert(gray)
                    img = gray.convert("RGB")
                    img = ImageOps.autocontrast(img)
                    img = ImageEnhance.Contrast(img).enhance(1.6)
                    img = ImageEnhance.Sharpness(img).enhance(1.3)
                max_width = int(os.getenv("PADDLE_OCR_MAX_WIDTH", "1024"))
                if img.width > max_width:
                    scale = max_width / img.width
                    new_size = (max_width, int(img.height * scale))
                    img = img.resize(new_size)
                image_input = np.array(img)[:, :, ::-1]
        except Exception:
            image_input = str(image_path)

    # PaddleOCR API changed: newer versions expect predict() without cls.
    try:
        result = ocr.predict(image_input)
    except Exception:
        result = ocr.ocr(image_input, cls=True)
    lines = _extract_lines(result)
    raw_text = "\n".join(line["text"] for line in lines)

    extracted = {
        "date": _extract_date(lines),
        "amount": _extract_amount(lines),
        "currency": _find_currency(lines),
        "merchant": _extract_merchant(lines),
    }

    return {
        "image_path": str(image_path),
        "raw_text": raw_text,
        "lines": lines,
        "extracted": extracted,
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
