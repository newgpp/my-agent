-- 数据库表结构（无外键；JOIN 关系以中文注释为准）

CREATE TABLE orgs (
  org_id      BIGINT      NOT NULL COMMENT '组织ID；用于与 users.org_id 关联（users.org_id = orgs.org_id）',
  org_name    VARCHAR(100) NOT NULL COMMENT '组织名称（如 Acme）',
  city        VARCHAR(50)  NOT NULL COMMENT '组织所在城市（如 San Francisco）',
  created_at  DATETIME     NOT NULL COMMENT '创建时间',
  PRIMARY KEY (org_id)
) COMMENT='组织维度表；与 users 表通过 org_id 关联';

CREATE TABLE users (
  user_id     BIGINT       NOT NULL COMMENT '用户ID；用于与 orders.user_id、subscriptions.user_id 关联',
  org_id      BIGINT       NOT NULL COMMENT '所属组织ID；JOIN：users.org_id = orgs.org_id',
  email       VARCHAR(120) NOT NULL COMMENT '邮箱；唯一',
  full_name   VARCHAR(80)  NOT NULL COMMENT '姓名',
  status      VARCHAR(20)  NOT NULL COMMENT '状态：active/disabled',
  created_at  DATETIME     NOT NULL COMMENT '注册时间',
  PRIMARY KEY (user_id),
  UNIQUE KEY uk_users_email (email),
  KEY idx_users_org_created (org_id, created_at)
) COMMENT='用户表；JOIN：orgs(org_id)；orders(user_id)；subscriptions(user_id)';

CREATE TABLE categories (
  category_id    BIGINT      NOT NULL COMMENT '品类ID；JOIN：products.category_id = categories.category_id',
  category_name  VARCHAR(60) NOT NULL COMMENT '品类名称（Compute/Storage/AI Tools）',
  PRIMARY KEY (category_id)
) COMMENT='商品品类维度表';

CREATE TABLE products (
  product_id    BIGINT       NOT NULL COMMENT '商品ID；JOIN：order_items.product_id = products.product_id',
  category_id   BIGINT       NOT NULL COMMENT '品类ID；JOIN：products.category_id = categories.category_id',
  sku           VARCHAR(40)  NOT NULL COMMENT 'SKU；唯一',
  product_name  VARCHAR(120) NOT NULL COMMENT '商品名称',
  price_cents   BIGINT       NOT NULL COMMENT '标价（分）',
  is_active     TINYINT      NOT NULL COMMENT '是否上架：1是/0否',
  PRIMARY KEY (product_id),
  UNIQUE KEY uk_products_sku (sku),
  KEY idx_products_category (category_id)
) COMMENT='商品表；JOIN：categories(category_id)，order_items(product_id)';

CREATE TABLE orders (
  order_id           BIGINT      NOT NULL COMMENT '订单ID；JOIN：order_items.order_id = orders.order_id',
  user_id            BIGINT      NOT NULL COMMENT '下单用户ID；JOIN：orders.user_id = users.user_id',
  order_status       VARCHAR(20) NOT NULL COMMENT '订单状态：paid/refunded/cancelled；口径：GMV默认只算 paid',
  order_total_cents  BIGINT      NOT NULL COMMENT '订单总金额（分）；注意：是否使用明细汇总以业务口径为准（默认用此字段）',
  ordered_at         DATETIME    NOT NULL COMMENT '下单时间（用于时间范围过滤）',
  PRIMARY KEY (order_id),
  KEY idx_orders_user_time (user_id, ordered_at),
  KEY idx_orders_time (ordered_at)
) COMMENT='订单事实表；JOIN：users(user_id)，order_items(order_id)；GMV口径默认 paid';

CREATE TABLE order_items (
  order_item_id     BIGINT   NOT NULL COMMENT '明细行ID',
  order_id          BIGINT   NOT NULL COMMENT '订单ID；JOIN：order_items.order_id = orders.order_id',
  product_id        BIGINT   NOT NULL COMMENT '商品ID；JOIN：order_items.product_id = products.product_id',
  quantity          INT      NOT NULL COMMENT '购买数量',
  item_total_cents  BIGINT   NOT NULL COMMENT '明细行金额（分）',
  PRIMARY KEY (order_item_id),
  KEY idx_items_order (order_id),
  KEY idx_items_product (product_id)
) COMMENT='订单明细表；JOIN：orders(order_id)，products(product_id)';

CREATE TABLE subscriptions (
  subscription_id BIGINT      NOT NULL COMMENT '订阅ID',
  user_id         BIGINT      NOT NULL COMMENT '用户ID；JOIN：subscriptions.user_id = users.user_id',
  plan_name       VARCHAR(50) NOT NULL COMMENT '订阅计划：free/pro/enterprise',
  status          VARCHAR(20) NOT NULL COMMENT '订阅状态：active/cancelled',
  started_at      DATETIME    NOT NULL COMMENT '订阅开始时间',
  ended_at        DATETIME    NULL COMMENT '订阅结束时间（取消时写入）',
  PRIMARY KEY (subscription_id),
  KEY idx_sub_user_status (user_id, status)
) COMMENT='订阅事实表；JOIN：users(user_id)';
