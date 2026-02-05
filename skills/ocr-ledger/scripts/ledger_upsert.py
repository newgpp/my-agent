#!/usr/bin/env python3
"""
Append a receipt record to a fixed CSV ledger.
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List

CSV_PATH = Path("/Users/mini/Documents/py_projects/my-agent/data/ledger.csv")
FIELDS: List[str] = [
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


def _read_json_payload(args: argparse.Namespace) -> Dict[str, str]:
    if args.data_file:
        data_path = Path(args.data_file).expanduser().resolve()
        if not data_path.exists():
            raise FileNotFoundError(f"Data file not found: {data_path}")
        return json.loads(data_path.read_text(encoding="utf-8"))
    if args.data:
        return json.loads(args.data)
    raise ValueError("Missing --data or --data-file")


def _validate_payload(payload: Dict[str, str]) -> Dict[str, str]:
    normalized = {key: ("" if payload.get(key) is None else str(payload.get(key))) for key in FIELDS}
    missing = [field for field in REQUIRED_FIELDS if not normalized.get(field)]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")
    return normalized


def _ensure_csv(csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if csv_path.exists():
        return
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()


def _row_exists(csv_path: Path, row: Dict[str, str]) -> bool:
    if not csv_path.exists():
        return False
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
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


def _ensure_trailing_newline(csv_path: Path) -> None:
    if not csv_path.exists():
        return
    if csv_path.stat().st_size == 0:
        return
    with csv_path.open("rb") as handle:
        handle.seek(-1, 2)
        last_byte = handle.read(1)
    if last_byte != b"\n":
        with csv_path.open("ab") as handle:
            handle.write(b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="JSON string with ledger fields")
    parser.add_argument("--data-file", help="Path to JSON file with ledger fields")
    parser.add_argument("--csv", help="Override CSV path")
    parser.add_argument("--dedupe", action="store_true", help="Skip if row already exists")
    args = parser.parse_args()

    try:
        payload = _read_json_payload(args)
        row = _validate_payload(payload)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    csv_path = Path(args.csv).expanduser().resolve() if args.csv else CSV_PATH
    _ensure_csv(csv_path)

    if args.dedupe and _row_exists(csv_path, row):
        print(
            json.dumps(
                {
                    "status": "skipped",
                    "reason": "duplicate",
                    "csv_path": str(csv_path),
                    "row": row,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    _ensure_trailing_newline(csv_path)
    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writerow(row)

    print(
        json.dumps(
            {
                "status": "inserted",
                "csv_path": str(csv_path),
                "row": row,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
