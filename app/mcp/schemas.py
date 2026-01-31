from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, ConfigDict


class MCPTool(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    description: Optional[str] = None
    input_schema: Dict[str, Any] = Field(default_factory=dict, alias="inputSchema")


class OpenAIFunction(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class OpenAITool(BaseModel):
    type: str = "function"
    function: OpenAIFunction
    x_mcp_server: Optional[str] = Field(default=None, alias="x-mcp-server")


class ToolResultContent(BaseModel):
    model_config = ConfigDict(extra="allow")

    content: Any
    is_error: Optional[bool] = None
