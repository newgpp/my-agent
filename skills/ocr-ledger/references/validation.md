# OCR Validation & Correction Rules

Common OCR issues and how to handle them:

1. Amount ambiguity
- Prefer lines containing: 合计/总计/金额/应付/实收/TOTAL/AMOUNT
- If multiple amounts, surface top 2 candidates and ask the user to confirm.

2. Date ambiguity
- Prefer formats: YYYY-MM-DD, YYYY/MM/DD, YYYY年M月D日
- If date missing, propose today’s date explicitly and ask for confirmation.

3. Merchant ambiguity
- Use the top header line with clear text and no obvious numeric amounts.
- If unsure, ask the user to confirm merchant name.

4. Currency ambiguity
- Infer from symbols: ¥/￥/CNY -> CNY; $/USD -> USD.
- If missing, default to CNY but ask for confirmation when the user seems non-local.

5. Low confidence text
- When OCR confidence is low, show the raw text fragment and ask for correction.

Do not auto-correct without user confirmation when critical fields are uncertain.
