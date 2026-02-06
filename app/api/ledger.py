from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.mcp.runner import MCPRunner
from app.ledger.ledger_flow import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    LedgerFlowType,
    ProcessResponse,
    process_ledger,
)

router = APIRouter()


def get_runner() -> MCPRunner:
    from app.main import mcp_runner

    return mcp_runner


@router.post("/v1/ledger/process", response_model=ProcessResponse)
async def ledger_process(
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    pending_id: Optional[str] = Form(None),
    runner: MCPRunner = Depends(get_runner),
) -> ProcessResponse:
    if pending_id:
        if file:
            raise HTTPException(
                status_code=400, detail="pending_id cannot be used with file uploads."
            )
        if not (text or "").strip():
            raise HTTPException(
                status_code=400, detail="Clarification text is required."
            )
        flow_type = LedgerFlowType.TEXT_LEDGER
    else:
        if not file and not text:
            raise HTTPException(status_code=400, detail="Provide file or text.")
        if file:
            filename = file.filename or ""
            ext = Path(filename).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                flow_type = LedgerFlowType.OCR_LEDGER
            elif ext in AUDIO_EXTENSIONS:
                flow_type = LedgerFlowType.ASR_LEDGER
            else:
                raise HTTPException(
                    status_code=400, detail=f"Unsupported file type: {ext}"
                )
        else:
            flow_type = LedgerFlowType.TEXT_LEDGER
            if not (text or "").strip():
                raise HTTPException(
                    status_code=400, detail="Text is required for TEXT_LEDGER."
                )

    return await process_ledger(
        file=file,
        text=text,
        pending_id=pending_id,
        runner=runner,
        flow_type=flow_type,
    )
