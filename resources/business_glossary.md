# 业务口径说明

- GMV：默认只统计 `orders.order_status = 'paid'` 的订单金额。
- 金额换算：所有 *_cents 字段为“分”，输出金额需除以 100 得到“元”。
- 活跃用户：`users.status = 'active'`。
- 订阅状态：`subscriptions.status = 'active'` 为有效订阅。
- 时间字段：
  - 订单时间：`orders.ordered_at`
  - 用户注册：`users.created_at`
  - 订阅开始：`subscriptions.started_at`
- 组织归属：`users.org_id = orgs.org_id`
