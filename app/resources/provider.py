from __future__ import annotations

from pathlib import Path

_RESOURCE_MAP = {
    "context://db_schema": "resources/db_schema.sql",
    "context://business_glossary": "resources/business_glossary.md",
}


def get_resource(uri: str) -> str:
    """Load a resource by uri and return its content as text."""
    if uri not in _RESOURCE_MAP:
        raise KeyError(f"Unknown resource uri: {uri}")
    base_dir = Path(__file__).resolve().parents[2]
    path = base_dir / _RESOURCE_MAP[uri]
    if not path.exists():
        raise FileNotFoundError(f"Resource not found: {path}")
    return path.read_text(encoding="utf-8")
