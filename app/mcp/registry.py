import json
import os
import shutil
from typing import Dict, List, Optional

from loguru import logger
from dotenv import load_dotenv
from pydantic import BaseModel, Field

class MCPServerConfig(BaseModel):
    name: Optional[str] = None
    command: str
    args: List[str] = Field(default_factory=list)
    env: Optional[Dict[str, str]] = None


class MCPServersFile(BaseModel):
    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)


def _expand_env(value: str) -> str:
    """Expand environment variables in a string."""
    return os.path.expandvars(value)


def _resolve_command(command: str) -> str:
    """Resolve a command to an absolute path if possible."""
    resolved = shutil.which(command)
    if resolved:
        return resolved
    if os.name == "nt":
        for ext in (".cmd", ".exe", ".bat"):
            if command.lower().endswith(ext):
                continue
            resolved = shutil.which(command + ext)
            if resolved:
                return resolved
    return command


def _is_resolved(value: str) -> bool:
    return "${" not in value and value.strip() != ""


def load_mcp_servers(config_path: str) -> Dict[str, MCPServerConfig]:
    """Load MCP server configs from JSON file."""
    # Ensure .env is loaded so ${FS_ALLOWED_DIR_*} expands correctly.
    load_dotenv()
    disabled_raw = os.getenv("MCP_DISABLED_SERVERS", "")
    disabled = {name.strip() for name in disabled_raw.split(",") if name.strip()}
    logger.info("Loading MCP servers from {}", config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    parsed = MCPServersFile.model_validate(raw)
    servers = parsed.servers
    result: Dict[str, MCPServerConfig] = {}
    for name, cfg in servers.items():
        if name in disabled:
            logger.info("Skipping MCP server {} (disabled)", name)
            continue
        command = _resolve_command(_expand_env(cfg.command))
        expanded_args = [_expand_env(arg) for arg in cfg.args]
        args = [arg for arg in expanded_args if _is_resolved(arg)]
        env = cfg.env
        if env:
            env = {k: _expand_env(v) for k, v in env.items()}
        result[name] = MCPServerConfig(name=name, command=command, args=args, env=env)
        logger.info("Registered MCP server {}", name)
    return result
