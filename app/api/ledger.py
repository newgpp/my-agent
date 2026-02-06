from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.mcp.runner import MCPRunner
from app.services.ledger import ProcessResponse, process_ledger_request

router = APIRouter()


def get_runner() -> MCPRunner:
    from app.main import mcp_runner
    return mcp_runner


@router.post("/v1/ledger/process", response_model=ProcessResponse)
async def ledger_process(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    runner: MCPRunner = Depends(get_runner),
) -> ProcessResponse:
    return await process_ledger_request(file=file, text=text, runner=runner)
