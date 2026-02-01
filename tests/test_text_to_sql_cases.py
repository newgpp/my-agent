import re

from app.sql.validator import validate_sql


CASES = [
    (
        "列出 org_name=Acme 下 active 用户邮箱、注册时间，倒序前10",
        """
        SELECT u.email, u.created_at
        FROM users u
        JOIN orgs o ON u.org_id = o.org_id
        WHERE o.org_name = 'Acme' AND u.status = 'active'
        ORDER BY u.created_at DESC
        LIMIT 10
        """,
        ["users", "orgs"],
    ),
    (
        "统计 2026-01-01 到 2026-01-31 Acme GMV（元）",
        """
        SELECT o.org_name, SUM(ord.order_total_cents) / 100.0 AS gmv_yuan
        FROM orders ord
        JOIN users u ON ord.user_id = u.user_id
        JOIN orgs o ON u.org_id = o.org_id
        WHERE o.org_name = 'Acme'
          AND ord.order_status = 'paid'
          AND ord.ordered_at >= '2026-01-01'
          AND ord.ordered_at < '2026-02-01'
        LIMIT 1
        """,
        ["orders", "users", "orgs"],
    ),
    (
        "Alice Zhang 在 2026-01 消费金额（元），不含退款取消",
        """
        SELECT u.full_name, SUM(ord.order_total_cents) / 100.0 AS gmv_yuan
        FROM orders ord
        JOIN users u ON ord.user_id = u.user_id
        WHERE u.full_name = 'Alice Zhang'
          AND ord.order_status = 'paid'
          AND ord.ordered_at >= '2026-01-01'
          AND ord.ordered_at < '2026-02-01'
        LIMIT 1
        """,
        ["orders", "users"],
    ),
    (
        "2026-01 销售额最高商品 Top3：商品名/品类/GMV(元)",
        """
        SELECT p.product_name, c.category_name, SUM(oi.item_total_cents) / 100.0 AS gmv_yuan
        FROM order_items oi
        JOIN orders ord ON oi.order_id = ord.order_id
        JOIN products p ON oi.product_id = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        WHERE ord.order_status = 'paid'
          AND ord.ordered_at >= '2026-01-01'
          AND ord.ordered_at < '2026-02-01'
        GROUP BY p.product_name, c.category_name
        ORDER BY gmv_yuan DESC
        LIMIT 3
        """,
        ["order_items", "orders", "products", "categories"],
    ),
    (
        "2026-01 各组织活跃用户数（paid），前10",
        """
        SELECT o.org_name, COUNT(DISTINCT u.user_id) AS active_users
        FROM orders ord
        JOIN users u ON ord.user_id = u.user_id
        JOIN orgs o ON u.org_id = o.org_id
        WHERE ord.order_status = 'paid'
          AND ord.ordered_at >= '2026-01-01'
          AND ord.ordered_at < '2026-02-01'
        GROUP BY o.org_name
        ORDER BY active_users DESC
        LIMIT 10
        """,
        ["orders", "users", "orgs"],
    ),
    (
        "2026-01 各城市 GMV（元）与活跃用户数，按 GMV 降序",
        """
        SELECT o.city,
               SUM(ord.order_total_cents) / 100.0 AS gmv_yuan,
               COUNT(DISTINCT u.user_id) AS active_users
        FROM orders ord
        JOIN users u ON ord.user_id = u.user_id
        JOIN orgs o ON u.org_id = o.org_id
        WHERE ord.order_status = 'paid'
          AND ord.ordered_at >= '2026-01-01'
          AND ord.ordered_at < '2026-02-01'
        GROUP BY o.city
        ORDER BY gmv_yuan DESC
        LIMIT 10
        """,
        ["orders", "users", "orgs"],
    ),
    (
        "2026-01 pro 订阅用户 GMV（元）",
        """
        SELECT SUM(ord.order_total_cents) / 100.0 AS gmv_yuan
        FROM subscriptions s
        JOIN users u ON s.user_id = u.user_id
        JOIN orders ord ON ord.user_id = u.user_id
        WHERE s.plan_name = 'pro'
          AND s.status = 'active'
          AND ord.order_status = 'paid'
          AND ord.ordered_at >= '2026-01-01'
          AND ord.ordered_at < '2026-02-01'
        LIMIT 1
        """,
        ["subscriptions", "users", "orders"],
    ),
    (
        "2026-01 有 active 订阅但无 paid 订单用户：邮箱/plan/started_at 前50",
        """
        SELECT u.email, s.plan_name, s.started_at
        FROM subscriptions s
        JOIN users u ON s.user_id = u.user_id
        LEFT JOIN orders ord
          ON ord.user_id = u.user_id
         AND ord.order_status = 'paid'
         AND ord.ordered_at >= '2026-01-01'
         AND ord.ordered_at < '2026-02-01'
        WHERE s.status = 'active'
          AND ord.order_id IS NULL
        ORDER BY s.started_at DESC
        LIMIT 50
        """,
        ["subscriptions", "users", "orders"],
    ),
    (
        "2026-01 各品类 GMV（元）前10",
        """
        SELECT c.category_name, SUM(oi.item_total_cents) / 100.0 AS gmv_yuan
        FROM order_items oi
        JOIN orders ord ON oi.order_id = ord.order_id
        JOIN products p ON oi.product_id = p.product_id
        JOIN categories c ON p.category_id = c.category_id
        WHERE ord.order_status = 'paid'
          AND ord.ordered_at >= '2026-01-01'
          AND ord.ordered_at < '2026-02-01'
        GROUP BY c.category_name
        ORDER BY gmv_yuan DESC
        LIMIT 10
        """,
        ["order_items", "orders", "products", "categories"],
    ),
    (
        "最近活跃用户趋势怎么样？",
        """
        -- NEED_CLARIFY: 缺少时间范围和指标口径
        SELECT 1 WHERE 1=0 LIMIT 0
        """,
        [],
    ),
]


def _assert_sql_rules(sql: str) -> None:
    ok, reason = validate_sql(sql)
    assert ok, reason
    upper = sql.upper()
    assert "SELECT *" not in upper
    assert re.search(r"\bLIMIT\b", upper)
    for keyword in ["INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "TRUNCATE", "CREATE"]:
        assert not re.search(rf"\b{keyword}\b", upper)


def _assert_paid(sql: str) -> None:
    assert "order_status = 'paid'" in sql or "order_status='paid'" in sql


def test_text_to_sql_cases() -> None:
    for question, sql, tables in CASES:
        _assert_sql_rules(sql)
        if "NEED_CLARIFY" not in sql and ("GMV" in question or "活跃用户" in question or "消费金额" in question):
            _assert_paid(sql)
        for table in tables:
            assert table in sql
