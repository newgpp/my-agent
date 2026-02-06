from __future__ import annotations

from pathlib import Path

_PROMPT_MAP = {
    "chat_planner": "prompts/chat_planner.md",
    "route_external_knowledge": "prompts/route_external_knowledge.md",
    "route_file_list": "prompts/route_file_list.md",
    "text_to_sql": "prompts/text_to_sql.md",
    "route_sql_generate": "prompts/route_sql_generate.md",
    "route_ledger": "prompts/route_ledger.md",
    "ledger_extract": "prompts/ledger_extract.md",
}


def load_prompt(name: str) -> str:
    """Load a prompt template by name."""
    if name not in _PROMPT_MAP:
        raise KeyError(f"Unknown prompt name: {name}")
    base_dir = Path(__file__).resolve().parents[2]
    path = base_dir / _PROMPT_MAP[name]
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")
