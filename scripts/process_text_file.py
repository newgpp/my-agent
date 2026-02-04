#!/usr/bin/env python3
"""Batch process ledger text lines from a file by calling /v1/ledger/process."""

import argparse
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data/text/1.text", help="Path to text file with one entry per line")
    parser.add_argument("--url", default="http://127.0.0.1:8000/v1/ledger/process", help="Ledger process URL")
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    path = Path(args.file).expanduser().resolve()
    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        return 1

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        print("[ERROR] No valid lines found")
        return 1

    with httpx.Client(timeout=args.timeout) as client:
        for idx, line in enumerate(lines, start=1):
            data = {"text": line}
            try:
                resp = client.post(args.url, data=data)
                if resp.status_code >= 400:
                    print(f"[{idx}] FAIL {resp.status_code}: {resp.text}")
                else:
                    print(f"[{idx}] OK: {resp.json()}")
            except Exception as exc:
                print(f"[{idx}] ERROR: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
