import json
import os
from typing import Dict, List, Optional

from loguru import logger
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


def _is_resolved(value: str) -> bool:
    return "${" not in value and value.strip() != ""


def load_mcp_servers(config_path: str) -> Dict[str, MCPServerConfig]:
    """Load MCP server configs from JSON file."""
    logger.info("Loading MCP servers from {}", config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    parsed = MCPServersFile.model_validate(raw)
    servers = parsed.servers
    result: Dict[str, MCPServerConfig] = {}
    for name, cfg in servers.items():
        command = _expand_env(cfg.command)
        expanded_args = [_expand_env(arg) for arg in cfg.args]
        args = [arg for arg in expanded_args if _is_resolved(arg)]
        env = cfg.env
        if env:
            env = {k: _expand_env(v) for k, v in env.items()}
        result[name] = MCPServerConfig(name=name, command=command, args=args, env=env)
        logger.info("Registered MCP server {}", name)
    return result
