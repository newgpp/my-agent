---
name: ocr-ledger
description: OCR-based receipt bookkeeping with local PaddleOCR and CSV ledger output. Use when users want to upload/drag receipt images (小票/发票/收据), extract fields, confirm values, and append rows to a fixed CSV ledger. Also use for correcting OCR extraction results and enforcing ledger field rules.
---

# OCR Ledger

## Overview

Extract receipt text via local PaddleOCR, confirm structured fields with the user, and append a record to a fixed CSV ledger.

## Workflow (Two-Step, Single Tool Call Per Turn)

1. Run OCR on the uploaded/dragged image and propose structured fields.
2. Ask for confirmation or missing values, then append to CSV.

## Step 1: OCR Receipt

Use `scripts/ocr_receipt.py` to extract text and candidate fields.

Inputs
- Image path MUST be an absolute path under the allowed filesystem roots.
- Default receipt directory: `/Users/mini/Documents/py_projects/my-agent/data/receipts/`

Output expectations
- JSON with `raw_text`, `lines`, and `extracted` fields.
- `extracted` SHOULD include `date`, `amount`, `currency`, `merchant` when possible.
- Always surface low-confidence or missing fields for user confirmation.

## Step 2: Confirm and Write CSV

Use `scripts/ledger_upsert.py` to append a record to the fixed ledger:
`/Users/mini/Documents/py_projects/my-agent/data/ledger.csv`

Rules
- Ask only for missing or ambiguous fields.
- Do not overwrite OCR output silently.
- If `date` is missing, propose today’s date with an explicit YYYY-MM-DD and ask for confirmation.

## Field Rules

Read `references/fields.md` for field definitions and Chinese comments.
Read `references/validation.md` for OCR validation and correction rules.

## Notes on LLM Usage

LLM is optional but recommended for robust extraction and correction. Without LLM, rely on OCR text + regex and ask the user to confirm any uncertain fields.

## Resources

### scripts/
- `ocr_receipt.py`: Run PaddleOCR locally and emit structured JSON.
- `ledger_upsert.py`: Append a ledger record to CSV with basic validation.

### references/
- `fields.md`: Ledger fields with Chinese comments and required rules.
- `validation.md`: OCR error patterns and correction guidance.
