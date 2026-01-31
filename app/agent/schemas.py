from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, ConfigDict


class FunctionCall(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    arguments: Union[str, Dict[str, Any], None] = None


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    type: Optional[str] = None
    function: Optional[FunctionCall] = None


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None


class ChatCompletionChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: ChatMessage


class ChatCompletionResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    choices: List[ChatCompletionChoice] = Field(default_factory=list)


class ChatDelta(BaseModel):
    model_config = ConfigDict(extra="allow")

    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    model_config = ConfigDict(extra="allow")

    delta: ChatDelta = Field(default_factory=ChatDelta)


class ChatCompletionChunk(BaseModel):
    model_config = ConfigDict(extra="allow")

    choices: List[ChatCompletionChunkChoice] = Field(default_factory=list)
