-- 数据库连接信息 数据库已经启动 root@123456mysql://127.0.0.1:3306/product
-- 组织表：用户归属组织
CREATE TABLE orgs (
  org_id      BIGINT      NOT NULL COMMENT '组织ID；用于与 users.org_id 关联（users.org_id = orgs.org_id）',
  org_name    VARCHAR(100) NOT NULL COMMENT '组织名称（如 Acme）',
  city        VARCHAR(50)  NOT NULL COMMENT '组织所在城市（如 San Francisco）',
  created_at  DATETIME     NOT NULL COMMENT '创建时间',
  PRIMARY KEY (org_id)
) COMMENT='组织维度表；与 users 表通过 org_id 关联';

-- 用户表：订单、订阅均从用户出发
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

-- 品类表：商品所属品类
CREATE TABLE categories (
  category_id    BIGINT      NOT NULL COMMENT '品类ID；JOIN：products.category_id = categories.category_id',
  category_name  VARCHAR(60) NOT NULL COMMENT '品类名称（Compute/Storage/AI Tools）',
  PRIMARY KEY (category_id)
) COMMENT='商品品类维度表';

-- 商品表：订单明细关联商品
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

-- 订单表：用户下单事实表
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

-- 订单明细表：一单多行
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

-- 订阅表：用户订阅计划
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

-- 样例数据
INSERT INTO orgs(org_id, org_name, city, created_at) VALUES
(1,'Acme','San Francisco','2025-01-01 09:00:00'),
(2,'BetaWorks','Los Angeles','2025-02-01 09:00:00'),
(3,'GammaLab','Seattle','2025-03-01 09:00:00');

INSERT INTO users(user_id, org_id, email, full_name, status, created_at) VALUES
(101,1,'alice@acme.com','Alice Zhang','active','2025-06-01 10:00:00'),
(102,1,'bob@acme.com','Bob Li','active','2025-06-10 10:00:00'),
(103,1,'cathy@acme.com','Cathy Wu','disabled','2025-07-01 10:00:00'),
(201,2,'david@beta.com','David Chen','active','2025-06-15 10:00:00'),
(202,2,'eva@beta.com','Eva Wang','active','2025-08-01 10:00:00'),
(301,3,'frank@gamma.com','Frank Sun','active','2025-09-01 10:00:00');

INSERT INTO categories(category_id, category_name) VALUES
(10,'Compute'),
(20,'Storage'),
(30,'AI Tools');

INSERT INTO products(product_id, category_id, sku, product_name, price_cents, is_active) VALUES
(1001,10,'GPU-A100','NVIDIA A100 Hourly Pack',5000,1),
(1002,10,'CPU-XL','CPU XL Monthly',2000,1),
(2001,20,'S3-100','Object Storage 100GB',800,1),
(3001,30,'SQL-COPILOT','SQL Copilot Pro',1500,1),
(3002,30,'OCR-PLUS','OCR Plus',1200,1);

INSERT INTO orders(order_id, user_id, order_status, order_total_cents, ordered_at) VALUES
(9001,101,'paid',6500,'2026-01-05 11:00:00'),
(9002,101,'refunded',1500,'2026-01-12 11:00:00'),
(9003,102,'paid',2000,'2026-01-20 15:30:00'),
(9004,201,'paid',5800,'2026-01-22 09:10:00'),
(9005,202,'cancelled',800,'2026-01-25 12:00:00'),
(9006,301,'paid',1200,'2026-01-28 18:20:00');

INSERT INTO order_items(order_item_id, order_id, product_id, quantity, item_total_cents) VALUES
(1,9001,1001,1,5000),
(2,9001,3001,1,1500),
(3,9002,3001,1,1500),
(4,9003,1002,1,2000),
(5,9004,1001,1,5000),
(6,9004,2001,1,800),
(7,9005,2001,1,800),
(8,9006,3002,1,1200);

INSERT INTO subscriptions(subscription_id, user_id, plan_name, status, started_at, ended_at) VALUES
(7001,101,'pro','active','2025-12-15 00:00:00',NULL),
(7002,102,'free','active','2025-12-01 00:00:00',NULL),
(7003,201,'pro','active','2026-01-01 00:00:00',NULL),
(7004,202,'free','cancelled','2025-11-01 00:00:00','2026-01-10 00:00:00');
