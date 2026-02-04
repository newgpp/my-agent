# ASR Validation & Correction Rules

Common ASR issues and how to handle them:

1. Amount ambiguity
- 口述可能出现同音错误（如“二十”听成“十二”）
- 出现多个金额时，提示用户确认

2. Date ambiguity
- 口述日期可能缺少年份（如“2月3日”）
- 缺少年份时，默认当前年份并要求确认
- 完全缺失时，提议今天的日期并确认

3. Merchant ambiguity
- 口述商户名被拆分或识别错误时，提示用户确认

4. Currency ambiguity
- 听到“美元/美金”时设为 USD
- 听到“人民币/人民币元/块”时设为 CNY
- 听不清时默认 CNY 但提示确认

5. Low confidence text
- 当 ASR 置信度低或文本不完整时，展示原文并询问修正

Do not auto-correct without user confirmation when critical fields are uncertain.
