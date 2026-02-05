from __future__ import annotations

import json
from typing import Any, Dict

from app.llm.deepseek_client import DeepSeekClient
from app.prompts.loader import load_prompt


LLM_SYSTEM_PROMPT = load_prompt("ledger_extract")


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


async def llm_extract_fields(text: str) -> Dict[str, str]:
    try:
        client = DeepSeekClient()
    except Exception:
        return {}
    messages = [
        {"role": "system", "content": LLM_SYSTEM_PROMPT},
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


async def llm_extract_many(texts: list[str]) -> list[Dict[str, str]]:
    if not texts:
        return []
    try:
        client = DeepSeekClient()
    except Exception:
        return []
    user_parts = []
    for idx, text in enumerate(texts, start=1):
        user_parts.append(f"RECORD {idx}:\n{truncate_text(text)}")
    messages = [
        {"role": "system", "content": LLM_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]
    try:
        response = await client.chat(messages, temperature=0.1, max_tokens=800)
    except Exception:
        return []
    choices = response.get("choices") or []
    if not choices:
        return []
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    payload = extract_json(content)
    records = _normalize_records(payload)
    return records
