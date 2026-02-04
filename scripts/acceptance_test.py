#!/usr/bin/env python3
"""Run acceptance tests against FastAPI app using local test data without binding a port."""

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("FS_ALLOWED_DIR_1", str(BASE_DIR))
os.environ.setdefault("MCP_DISABLED_SERVERS", "filesystem,tavily")

from app.main import app  # noqa: E402

PICTURE_DIR = BASE_DIR / "data" / "picture"
VOICE_DIR = BASE_DIR / "data" / "voice"
TEXT_FILE = BASE_DIR / "data" / "text" / "1.text"
TEXT_FILE_FALLBACK = BASE_DIR / "data" / "text" / "1.txt"


def _post_file(client: TestClient, path: Path):
    with path.open("rb") as handle:
        files = {"file": (path.name, handle)}
        return client.post("/v1/ledger/process", files=files)


def _post_text(client: TestClient, text: str):
    data = {"text": text}
    return client.post("/v1/ledger/process", data=data)


def main() -> int:
    with TestClient(app) as client:
        if os.getenv("OCR_DISABLED", "").lower() not in ("1", "true", "yes"):
            print("== Image Tests ==")
            for path in sorted(PICTURE_DIR.glob("*.png")):
                resp = _post_file(client, path)
                print(path.name, resp.status_code)
                print(resp.text)

        if os.getenv("ASR_DISABLED", "").lower() not in ("1", "true", "yes"):
            print("== Voice Tests ==")
            for path in sorted(VOICE_DIR.glob("*.m4a")):
                resp = _post_file(client, path)
                print(path.name, resp.status_code)
                print(resp.text)

        print("== Text Tests ==")
        text_path = TEXT_FILE if TEXT_FILE.exists() else TEXT_FILE_FALLBACK
        if text_path.exists():
            for line in text_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                resp = _post_text(client, line)
                print(line, resp.status_code)
                print(resp.text)
        else:
            print("Text file not found:", TEXT_FILE)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
