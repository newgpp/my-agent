from __future__ import annotations

import json
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional

from app.llm.deepseek_client import DeepSeekClient
from app.mcp.runner import MCPRunner
from loguru import logger

TIME_RE = re.compile(r"(上午|下午)?\d{1,2}:\d{2}")
AMOUNT_RE = re.compile(r"[¥￥]\s*\d+(?:\.\d{1,2})?")
DATE_RE = re.compile(r"\d{4}[年/-]\d{1,2}[月/-]\d{1,2}")
PAYMENT_HINT_RE = re.compile(r"(微信|支付宝|云闪付)")
LIST_TIME_RE = re.compile(r"\d{1,2}月\d{1,2}日\d{1,2}:\d{2}")
LIST_AMOUNT_RE = re.compile(r"-?\d+(?:\.\d{1,2})?")
REL_TIME_RE = re.compile(r"(今天|昨天)\d{1,2}:\d{2}|\d{2}-\d{2}\s?\d{1,2}:\d{2}")
DOT_DATE_RE = re.compile(r"\d{2}\.\d{2}(?:周[一二三四五六日天]|昨天|今天)?")

NOISE_LINES = {"我的账单", "支付服务", "摇优惠", "日报设置"}
HEADER_KEYWORDS = {
    "交易记录",
    "筛选",
    "云闪付APP",
    "全部",
    "网购",
    "线下消费",
    "转账",
    "信用卡还款",
    "支出",
    "收入",
    "收支分析",
    "设置支出预算",
}
STATUS_KEYWORDS = {"自动扣款成功", "交通出行"}


def truncate_text(text: str, limit: int = 800) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit]


def extract_json(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        stripped = stripped.replace("json", "", 1).strip()
    try:
        return json.loads(stripped)
    except Exception:
        pass
    array_start = stripped.find("[")
    array_end = stripped.rfind("]")
    if array_start != -1 and array_end != -1 and array_end > array_start:
        try:
            return json.loads(stripped[array_start : array_end + 1])
        except Exception:
            pass
    obj_start = stripped.find("{")
    obj_end = stripped.rfind("}")
    if obj_start == -1 or obj_end == -1 or obj_end <= obj_start:
        return {}
    try:
        return json.loads(stripped[obj_start : obj_end + 1])
    except Exception:
        return {}


def _normalize_record(payload: Any) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for key in ("date", "merchant", "amount", "currency", "category", "payment_method"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if value is None:
            result[key] = ""
        else:
            result[key] = str(value)
    return result


def _normalize_records(payload: Any) -> list[Dict[str, str]]:
    if isinstance(payload, list):
        return [_normalize_record(item) for item in payload]
    if isinstance(payload, dict):
        return [_normalize_record(payload)]
    return []


async def llm_extract_fields(text: str, system_prompt: str) -> Dict[str, str]:
    if not system_prompt:
        return {}
    try:
        client = DeepSeekClient()
    except Exception:
        return {}
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": truncate_text(text)},
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
    payload = extract_json(content)
    records = _normalize_records(payload)
    if not records:
        return {}
    return records[0]


def normalize_tool_output(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    if "extracted" in result:
        return result
    content = result.get("content")
    if isinstance(content, list) and content:
        first = content[0] if isinstance(content[0], dict) else {}
        text = first.get("text") if isinstance(first, dict) else None
        if isinstance(text, str):
            payload = extract_json(text)
            if isinstance(payload, dict) and payload:
                return payload
    return result


async def parse_image(
    runner: MCPRunner,
    image_path: str,
    lang: str = "ch",
) -> Dict[str, Any]:
    result = await runner.call_tool(
        "ledger",
        "ocr_receipt",
        {"image_path": image_path, "lang": lang},
    )
    if hasattr(result, "model_dump"):
        raw_result = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    else:
        raw_result = result
    return normalize_tool_output(raw_result)


def extract_lines(parse_result: Dict[str, Any]) -> List[str]:
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


def extract_line_items(parse_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = parse_result.get("lines")
    if isinstance(lines, list) and lines:
        extracted: List[Dict[str, Any]] = []
        for item in lines:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    entry = {"text": text.strip()}
                    bbox = item.get("bbox")
                    if isinstance(bbox, list) and len(bbox) == 4:
                        entry["bbox"] = bbox
                        entry["cy"] = (bbox[1] + bbox[3]) / 2
                        entry["cx"] = (bbox[0] + bbox[2]) / 2
                    extracted.append(entry)
            elif isinstance(item, str) and item.strip():
                extracted.append({"text": item.strip()})
        if extracted:
            return extracted
    return []


def _compute_y_threshold(items: List[Dict[str, Any]]) -> float:
    ys = []
    for item in items:
        bbox = item.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 4:
            ys.append(bbox[1])
            ys.append(bbox[3])
    if not ys:
        return 18.0
    height = max(ys) - min(ys)
    if height <= 0:
        return 18.0
    return max(10.0, height * 0.012)


def _group_lines_by_y(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    with_bbox = [item for item in items if "cy" in item]
    if not with_bbox:
        return [{"text": item["text"], "cy": idx} for idx, item in enumerate(items)]
    with_bbox.sort(key=lambda x: (x["cy"], x.get("cx", 0)))
    rows: List[List[Dict[str, Any]]] = []
    row: List[Dict[str, Any]] = []
    current_y = None
    y_threshold = _compute_y_threshold(with_bbox)
    for item in with_bbox:
        if current_y is None or abs(item["cy"] - current_y) <= y_threshold:
            row.append(item)
            current_y = (
                item["cy"] if current_y is None else (current_y + item["cy"]) / 2
            )
        else:
            rows.append(row)
            row = [item]
            current_y = item["cy"]
    if row:
        rows.append(row)
    merged: List[Dict[str, Any]] = []
    for row_items in rows:
        row_items.sort(key=lambda x: x.get("cx", 0))
        text = "".join(part["text"] for part in row_items)
        avg_y = sum(part["cy"] for part in row_items) / len(row_items)
        merged.append({"text": text, "cy": avg_y})
    return merged


def extract_date_context(lines: List[str]) -> List[str]:
    context: List[str] = []
    for line in lines:
        if DATE_RE.search(line):
            context.append(line)
    return context


def extract_payment_context(lines: List[str]) -> List[str]:
    context: List[str] = []
    for line in lines:
        if PAYMENT_HINT_RE.search(line):
            context.append(line)
    return context


def split_receipt_entries(lines: List[str]) -> List[List[str]]:
    if not lines:
        return []
    filtered = [
        line for line in lines if line.strip() and line.strip() not in NOISE_LINES
    ]
    if not filtered:
        return []

    list_time_indices = [
        i for i, line in enumerate(filtered) if LIST_TIME_RE.search(line)
    ]
    if len(list_time_indices) >= 2:
        segments: List[List[str]] = []
        for idx, start in enumerate(list_time_indices):
            end = (
                list_time_indices[idx + 1]
                if idx + 1 < len(list_time_indices)
                else len(filtered)
            )
            segment = filtered[start:end]
            segments.append(segment)
        return segments

    time_indices = [i for i, line in enumerate(filtered) if TIME_RE.search(line)]
    amount_indices = [i for i, line in enumerate(filtered) if AMOUNT_RE.search(line)]
    detail_indices = {i for i, line in enumerate(filtered) if "账单详情" in line}

    if not time_indices or not amount_indices:
        # Fallback for list-style ledger: split by a date-time line if present.
        if list_time_indices:
            segments: List[List[str]] = []
            start = list_time_indices[0]
            for idx in range(1, len(filtered)):
                if idx in list_time_indices:
                    segments.append(filtered[start:idx])
                    start = idx
            segments.append(filtered[start:])
            return segments
        return [filtered]

    max_gap = 7  # amount should appear within a small window after the time line
    lead_window = 4  # include small lead-in context before time (e.g., 微信支付)
    segments: List[List[str]] = []
    last_end = 0
    for idx, time_idx in enumerate(time_indices):
        next_time = (
            time_indices[idx + 1] if idx + 1 < len(time_indices) else len(filtered)
        )
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
            continue

        end_idx = next_time
        for di in range(amount_idx, next_time):
            if di in detail_indices:
                end_idx = di + 1
                break
        lead_start = max(last_end, time_idx - lead_window)
        lead_segment = filtered[lead_start:time_idx]
        segment = [
            line
            for line in lead_segment + filtered[time_idx:end_idx]
            if "账单详情" not in line
        ]
        if segment:
            segments.append(segment)
            last_end = end_idx

    if segments:
        return segments
    return [filtered]


def split_receipt_entries_with_bbox(items: List[Dict[str, Any]]) -> List[List[str]]:
    rows = _group_lines_by_y(items)
    if not rows:
        return []
    detail_indices = [i for i, row in enumerate(rows) if "账单详情" in row["text"]]
    if len(detail_indices) >= 1:
        segments: List[List[str]] = []
        start = 0
        for di in detail_indices:
            segment = [
                row["text"] for row in rows[start:di] if row["text"] not in NOISE_LINES
            ]
            if segment:
                segments.append(segment)
            start = di + 1
        tail = [row["text"] for row in rows[start:] if row["text"] not in NOISE_LINES]
        if tail:
            segments.append(tail)
        return _merge_time_only_segments(segments)
    segments: List[List[str]] = []
    current: List[str] = []
    current_date_line: str | None = None
    has_amount = False

    def is_amount_line(text: str) -> bool:
        return bool(LIST_AMOUNT_RE.search(text))

    def is_date_anchor(text: str) -> bool:
        return bool(LIST_TIME_RE.search(text) or DOT_DATE_RE.search(text))

    def is_time_line(text: str) -> bool:
        return bool(REL_TIME_RE.search(text))

    def is_bank_line(text: str) -> bool:
        return "·" in text or "银行" in text

    def is_merchant_line(text: str) -> bool:
        if is_amount_line(text) or is_date_anchor(text) or is_time_line(text):
            return False
        if is_bank_line(text):
            return False
        return len(text) >= 3

    for row in rows:
        text = row["text"]
        if text in NOISE_LINES:
            continue
        is_anchor = bool(is_date_anchor(text) or ("－" in text) or ("—" in text))
        if is_anchor:
            if current:
                segments.append(current)
            current = [text]
            current_date_line = text if is_date_anchor(text) else current_date_line
            has_amount = False
            continue
        if not current:
            current = [text]
            if is_date_anchor(text):
                current_date_line = text
            has_amount = is_amount_line(text)
            continue
        # If we already captured an amount and see another merchant line,
        # start a new segment but keep the current date line for context.
        if has_amount and is_merchant_line(text):
            segments.append(current)
            current = [current_date_line] if current_date_line else []
            current.append(text)
            has_amount = False
            continue
        current.append(text)
        if is_amount_line(text):
            has_amount = True
    if current:
        segments.append(current)
    return _merge_time_only_segments(segments)


def _is_time_only_segment(segment: List[str]) -> bool:
    if not segment:
        return False
    text = "".join(segment)
    if LIST_TIME_RE.search(text) or REL_TIME_RE.search(text):
        has_amount = bool(LIST_AMOUNT_RE.search(text))
        has_merchant = "－" in text or "—" in text
        return not has_amount and not has_merchant
    return False


def _merge_time_only_segments(segments: List[List[str]]) -> List[List[str]]:
    if not segments:
        return segments
    merged: List[List[str]] = []
    for segment in segments:
        if _is_time_only_segment(segment):
            if merged:
                merged[-1].extend(segment)
            else:
                merged.append(segment)
            continue
        merged.append(segment)
    return merged


def _segment_has_amount(segment: List[str]) -> bool:
    return any(LIST_AMOUNT_RE.search(line) for line in segment)


def _segment_has_header_noise(segment: List[str]) -> bool:
    return any(any(keyword in line for keyword in HEADER_KEYWORDS) for line in segment)


def _segment_has_status(segment: List[str]) -> bool:
    return any(any(keyword in line for keyword in STATUS_KEYWORDS) for line in segment)


def _segment_is_candidate(segment: List[str]) -> bool:
    if not segment:
        return False
    if _segment_has_header_noise(segment):
        return False
    if not _segment_has_amount(segment):
        return False
    # Require some status/category signal to avoid stray noise fragments.
    if not _segment_has_status(segment):
        return False
    return True


async def build_combined_texts_from_ocr(
    runner: MCPRunner,
    image_path: str,
    text: Optional[str],
) -> List[str]:
    parse_result = await parse_image(runner, image_path, "ch")
    text_for_llm = ""
    line_items = extract_line_items(parse_result)
    lines_for_llm = extract_lines(parse_result)
    raw_text = parse_result.get("raw_text")
    if isinstance(raw_text, str):
        text_for_llm = raw_text.strip()
    if text:
        text_for_llm = (
            f"{text_for_llm}\n{text}".strip() if text_for_llm else text.strip()
        )

    if not text_for_llm and not lines_for_llm:
        raise ValueError("No OCR/transcript/text available for extraction.")

    segments = (
        split_receipt_entries_with_bbox(line_items)
        if line_items
        else split_receipt_entries(lines_for_llm)
    )
    segments = [segment for segment in segments if _segment_is_candidate(segment)]
    if len(segments) <= 1:
        segments = [lines_for_llm] if lines_for_llm else [text_for_llm.splitlines()]

    date_context = extract_date_context(lines_for_llm)
    payment_context = extract_payment_context(lines_for_llm)
    combined_texts: List[str] = []
    for segment in segments:
        segment_text = "\n".join(segment).strip()
        if not segment_text:
            continue
        combined_text = segment_text
        if date_context:
            combined_text = "\n".join(date_context) + "\n" + combined_text
        if payment_context and not PAYMENT_HINT_RE.search(combined_text):
            combined_text = "\n".join(payment_context) + "\n" + combined_text
        if text:
            combined_text = f"{combined_text}\n{text}".strip()
        combined_texts.append(combined_text)

    if os.getenv("OCR_SEGMENT_DEBUG", "").lower() in ("1", "true", "yes"):
        for idx, segment in enumerate(segments, start=1):
            logger.info("OCR segments {}: {}", idx, " | ".join(segment))

    return combined_texts


def build_payloads_from_ocr(
    llm_records: List[Dict[str, Any]],
    combined_texts: List[str],
    text: Optional[str],
    source_image: str,
    source_audio: str,
) -> tuple[List[Dict[str, Any]], List[str]]:
    if len(combined_texts) == 1 and len(llm_records) > 1:
        payloads: List[Dict[str, Any]] = []
        for llm_fields in llm_records:
            payload: Dict[str, Any] = {
                "date": llm_fields.get("date") or "",
                "merchant": llm_fields.get("merchant") or "",
                "amount": llm_fields.get("amount") or "",
                "currency": llm_fields.get("currency") or "",
                "category": llm_fields.get("category") or "",
                "payment_method": llm_fields.get("payment_method") or "",
                "note": text.strip() if text else "",
                "source_image": source_image,
                "source_audio": source_audio,
            }
            if not payload.get("date"):
                payload["date"] = date.today().isoformat()
            payloads.append(payload)
        expanded_inputs = [combined_texts[0]] * len(payloads)
        return payloads, expanded_inputs
    payloads: List[Dict[str, Any]] = []
    for idx, combined_text in enumerate(combined_texts):
        llm_fields = llm_records[idx] if idx < len(llm_records) else {}
        payload: Dict[str, Any] = {
            "date": llm_fields.get("date") or "",
            "merchant": llm_fields.get("merchant") or "",
            "amount": llm_fields.get("amount") or "",
            "currency": llm_fields.get("currency") or "",
            "category": llm_fields.get("category") or "",
            "payment_method": llm_fields.get("payment_method") or "",
            "note": text.strip() if text else "",
            "source_image": source_image,
            "source_audio": source_audio,
        }
        if not payload.get("date"):
            payload["date"] = date.today().isoformat()
        payloads.append(payload)
    return payloads, combined_texts
