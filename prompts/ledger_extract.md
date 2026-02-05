Extract receipt fields from the user's text. Return ONLY JSON with keys:
date, merchant, amount, currency, category, payment_method.

Rules:
- date must be YYYY-MM-DD. If unknown, return empty string.
- amount must be a plain number string (no currency symbols). If unknown, empty string.
- currency should be ISO code when possible (e.g., CNY, USD). If unknown, empty string.
- category must be one of: 餐饮, 购物, 日用, 交通, 蔬菜, 水果, 零食, 通讯, 娱乐, 服饰, 美容, 住房, 社交, 旅行.
  If unsure, return empty string.
- payment_method must be one of: 支付宝, 微信, 云闪付. If unsure, return empty string.

Hints:
- Mentions of 微信, 零钱, 财付通, 扫二维码付款, 小程序 usually imply payment_method=微信.
- Mentions of 支付宝, 花呗, 余额宝 usually imply payment_method=支付宝.
- Mentions of 云闪付 usually imply payment_method=云闪付.
- Merchant keywords for category (examples): 水果 -> 水果, 蔬菜 -> 蔬菜, 超市/便利店 -> 日用, 餐厅/饭店 -> 餐饮,
  交通/地铁/公交 -> 交通, 电影/游戏 -> 娱乐, 通讯/话费 -> 通讯, 服装/鞋 -> 服饰, 美容/美发 -> 美容,
  酒店/房租 -> 住房, 旅游/机票 -> 旅行, 礼物/聚会 -> 社交.
