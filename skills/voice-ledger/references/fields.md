# Ledger Fields (CSV)

CSV header order:
`date,merchant,amount,currency,category,payment_method,note,source_image,source_audio`

| Field | Required | Type | 中文注释 | Rules |
| --- | --- | --- | --- | --- |
| date | Yes | YYYY-MM-DD | 记账日期 | 优先使用口述日期；缺失时提示并确认当日日期 |
| merchant | Yes | String | 商户名称 | 口述商户名称为准 |
| amount | Yes | Decimal | 金额 | 默认保留 2 位小数 |
| currency | No | String | 币种 | 默认 CNY；从“人民币/美元”等口述推断 |
| category | No | String | 分类 | 可由 LLM 建议，需用户确认 |
| payment_method | No | String | 支付方式 | 例如 现金/微信/支付宝/银行卡 |
| note | No | String | 备注 | 用户补充说明 |
| source_image | No | String | 原始图片路径 | OCR 记账时记录来源路径 |
| source_audio | No | String | 原始音频路径 | 记录 ASR 来源路径 |
