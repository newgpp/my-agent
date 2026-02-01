from __future__ import annotations

from pathlib import Path


_PROMPT_MAP = {
    "text_to_sql": "prompts/text_to_sql.md",
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
