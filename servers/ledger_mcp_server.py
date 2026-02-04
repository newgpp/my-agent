import json
import sys
import subprocess
import importlib.util
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from loguru import logger
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ledger")
load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
OCR_SCRIPT = BASE_DIR / "skills" / "ocr-ledger" / "scripts" / "ocr_receipt.py"
VOICE_SCRIPT = BASE_DIR / "skills" / "voice-ledger" / "scripts" / "transcribe_audio.py"
LEDGER_CSV = BASE_DIR / "data" / "ledger.csv"

LEDGER_FIELDS = [
    "date",
    "merchant",
    "amount",
    "currency",
    "category",
    "payment_method",
    "note",
    "source_image",
    "source_audio",
]

REQUIRED_FIELDS = {"date", "merchant", "amount"}
_OCR_MODULE = None


def _load_ocr_module():
    global _OCR_MODULE
    if _OCR_MODULE is not None:
        return _OCR_MODULE
    spec = importlib.util.spec_from_file_location("ocr_receipt", OCR_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load OCR module from {OCR_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _OCR_MODULE = module
    return module


def _run_script_json(script_path: Path, args: list[str]) -> Dict[str, Any]:
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")
    cmd = [sys.executable, str(script_path), *args]
    logger.info("Running script: {}", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Script failed")
    output = result.stdout.strip()
    if not output:
        raise RuntimeError("Script returned empty output")
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from script: {exc}") from exc


def _ensure_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    import csv

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        writer.writeheader()


def _validate_payload(payload: Dict[str, Any]) -> Dict[str, str]:
    normalized = {key: "" if payload.get(key) is None else str(payload.get(key)) for key in LEDGER_FIELDS}
    missing = [field for field in REQUIRED_FIELDS if not normalized.get(field)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    return normalized


def _row_exists(path: Path, row: Dict[str, str]) -> bool:
    if not path.exists():
        return False
    import csv

    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for existing in reader:
            if (
                existing.get("date") == row.get("date")
                and existing.get("merchant") == row.get("merchant")
                and existing.get("amount") == row.get("amount")
                and existing.get("source_image") == row.get("source_image")
                and existing.get("source_audio") == row.get("source_audio")
            ):
                return True
    return False


@mcp.tool()
def ocr_receipt(image_path: str, lang: str = "ch") -> Dict[str, Any]:
    """Run PaddleOCR on a receipt image and return structured JSON."""
    module = _load_ocr_module()
    payload = module.run(Path(image_path), lang)
    if not isinstance(payload, dict):
        raise RuntimeError("OCR module returned unexpected payload.")
    return payload


@mcp.tool()
def transcribe_audio(audio_path: str, model: str = "small", device: str = "cpu") -> Dict[str, Any]:
    """Transcribe WAV audio via faster-whisper and return structured JSON."""
    payload = _run_script_json(
        VOICE_SCRIPT,
        [
            "--audio",
            audio_path,
            "--model",
            model,
            "--device",
            device,
            "--output",
            "-",
        ],
    )
    return payload


@mcp.tool()
def ledger_upsert(payload: Dict[str, Any], dedupe: bool = True, csv_path: Optional[str] = None) -> Dict[str, Any]:
    """Append a ledger record to CSV with optional deduplication."""
    csv_path = Path(csv_path).expanduser().resolve() if csv_path else LEDGER_CSV
    row = _validate_payload(payload)
    _ensure_csv(csv_path)

    if dedupe and _row_exists(csv_path, row):
        return {"status": "skipped", "reason": "duplicate", "csv_path": str(csv_path), "row": row}

    import csv

    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LEDGER_FIELDS)
        writer.writerow(row)

    return {"status": "inserted", "csv_path": str(csv_path), "row": row}


if __name__ == "__main__":
    logger.info("Starting Ledger MCP server")
    mcp.run()
