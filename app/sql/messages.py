from __future__ import annotations

from typing import Dict, List


def build_text_to_sql_messages(
    question: str,
    db_schema: str,
    glossary: str,
    prompt: str,
) -> List[Dict[str, str]]:
    return [
        {"role": "system", "content": prompt},
        {"role": "system", "content": db_schema},
        {"role": "system", "content": glossary},
        {"role": "user", "content": question},
    ]
