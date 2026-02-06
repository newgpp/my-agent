from __future__ import annotations

import re
from typing import Tuple

_FORBIDDEN_KEYWORDS = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "ALTER",
    "DROP",
    "TRUNCATE",
    "CREATE",
]


def _strip_leading_comments(sql: str) -> str:
    lines = sql.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx].lstrip()
        if line.startswith("--") or line == "":
            idx += 1
            continue
        break
    return "\n".join(lines[idx:]).lstrip()


def validate_sql(sql: str) -> Tuple[bool, str]:
    """Validate SQL safety constraints for text-to-sql output."""
    if not sql or not sql.strip():
        return False, "empty sql"

    upper_sql = sql.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            return False, f"forbidden keyword: {keyword}"

    cleaned = _strip_leading_comments(sql)
    if not cleaned.upper().startswith("SELECT"):
        return False, "sql must start with SELECT"

    if re.search(r"\bSELECT\s+\*", upper_sql):
        return False, "SELECT * is not allowed"

    # Allow trailing semicolon, but no extra statements.
    parts = [part.strip() for part in sql.split(";") if part.strip()]
    if len(parts) > 1:
        return False, "multiple statements are not allowed"

    if not re.search(r"\bLIMIT\b", upper_sql):
        return False, "LIMIT is required"

    return True, "ok"


def contains_forbidden_keyword(text: str) -> bool:
    upper_text = text.upper()
    return any(
        re.search(rf"\b{keyword}\b", upper_text) for keyword in _FORBIDDEN_KEYWORDS
    )
