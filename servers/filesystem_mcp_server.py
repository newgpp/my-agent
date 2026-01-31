import os
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

mcp = FastMCP("filesystem")
load_dotenv()


def _allowed_roots() -> List[Path]:
    roots: List[Path] = []
    for key in ("FS_ALLOWED_DIR_1", "FS_ALLOWED_DIR_2"):
        value = os.getenv(key)
        if not value:
            continue
        try:
            roots.append(Path(value).expanduser().resolve())
        except Exception:
            continue
    return roots


def _is_allowed(path: Path, roots: List[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _resolve_path(path: str, roots: List[Path]) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    for root in roots:
        resolved = (root / candidate).resolve()
        if resolved.exists():
            return resolved
    return candidate.resolve()


@mcp.tool()
def list_directory(path: str, limit: int = 100) -> Dict[str, Any]:
    """List files in a directory within allowed roots."""
    roots = _allowed_roots()
    if not roots:
        raise RuntimeError("FS_ALLOWED_DIR_1/FS_ALLOWED_DIR_2 not set")
    target = _resolve_path(path, roots)
    if not _is_allowed(target, roots):
        raise RuntimeError(f"Path not allowed: {target}")
    if not target.exists() or not target.is_dir():
        raise RuntimeError(f"Not a directory: {target}")
    entries = []
    for idx, entry in enumerate(sorted(target.iterdir())):
        if idx >= limit:
            break
        entries.append(
            {
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else None,
            }
        )
    return {"path": str(target), "entries": entries}


@mcp.tool()
def read_file(path: str, max_bytes: int = 200_000) -> Dict[str, Any]:
    """Read file content within allowed roots."""
    roots = _allowed_roots()
    if not roots:
        raise RuntimeError("FS_ALLOWED_DIR_1/FS_ALLOWED_DIR_2 not set")
    target = _resolve_path(path, roots)
    if not _is_allowed(target, roots):
        raise RuntimeError(f"Path not allowed: {target}")
    if not target.exists() or not target.is_file():
        raise RuntimeError(f"Not a file: {target}")
    data = target.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    return {"path": str(target), "content": data.decode("utf-8", errors="replace")}


if __name__ == "__main__":
    logger.info("Starting Filesystem MCP server")
    mcp.run()
