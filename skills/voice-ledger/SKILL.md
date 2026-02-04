---
name: voice-ledger
description: Voice-based bookkeeping with local faster-whisper ASR and CSV ledger output. Use when users upload/drag WAV audio to record expenses by speech, then extract fields, confirm values, and append rows to a fixed CSV ledger. Also use for correcting ASR extraction results and enforcing ledger field rules.
---

# Voice Ledger

## Overview

Transcribe WAV audio via local faster-whisper, confirm structured fields with the user, and append a record to a fixed CSV ledger.

## Workflow (Two-Step, Single Tool Call Per Turn)

1. Run ASR on the uploaded/dragged WAV and propose structured fields.
2. Ask for confirmation or missing values, then append to CSV.

## Step 1: Transcribe Audio

Use `scripts/transcribe_audio.py` to transcribe and extract candidate fields.

Inputs
- Audio path MUST be an absolute path under the allowed filesystem roots.
- Default audio directory: `/Users/mini/Documents/py_projects/my-agent/data/voice/`

Output expectations
- JSON with `raw_text`, `segments`, and `extracted` fields.
- `extracted` SHOULD include `date`, `amount`, `currency`, `merchant` when possible.
- Always surface low-confidence or missing fields for user confirmation.

## Step 2: Confirm and Write CSV

Use `scripts/ledger_upsert.py` to append a record to the fixed ledger:
`/Users/mini/Documents/py_projects/my-agent/data/ledger.csv`

Rules
- Ask only for missing or ambiguous fields.
- Do not overwrite ASR output silently.
- If `date` is missing, propose today’s date with an explicit YYYY-MM-DD and ask for confirmation.

## Field Rules

Read `references/fields.md` for field definitions and Chinese comments.
Read `references/validation.md` for ASR validation and correction rules.

## Notes on LLM Usage

LLM is optional but recommended for robust extraction and correction. Without LLM, rely on ASR text + regex and ask the user to confirm any uncertain fields.

## Resources

### scripts/
- `transcribe_audio.py`: Run faster-whisper locally and emit structured JSON.
- `ledger_upsert.py`: Append a ledger record to CSV with basic validation.

### references/
- `fields.md`: Ledger fields with Chinese comments and required rules.
- `validation.md`: ASR error patterns and correction guidance.
