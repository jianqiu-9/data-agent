# Data Agent 数据平台智能助手 PRD v2.0

## 1. 产品概述

### 1.1 产品定位

Data Agent 是面向数据研发、数据分析、业务分析及数据平台使用用户的智能助手。

目标不是让“不会 SQL 的人直接问数据”，而是：

> **让一个已经具备 SQL 和基本数据分析能力的用户，不需要深入理解数据平台内部的表体系、角色体系、权限申请流程、SQL 性能优化规则以及各类平台操作细节，就能够高效完成数据使用任务。**

Data Agent 通过自然语言 + SQL + 数据平台元数据，将原本分散在：

* 数据目录
* 表/字段元数据
* 权限中心
* 角色系统
* 工单系统
* SQL 审计
* SQL 优化能力
* 数据查询引擎

中的能力统一起来。

用户可以直接问：

> “dwd_order 这张表到底是干什么的？”

> “这个字段和 order_amount 有什么区别？”

> “我为什么查不了这张表？”

> “我应该申请什么权限？”

> “这个 SQL 为什么这么慢？”

> “帮我优化一下。”

> “这个 role 到底有什么权限？”

Agent 负责理解问题、调用正确的平台能力，并给出可执行结果。

---

# 2. 背景与问题

## 2.1 当前数据平台用户的主要痛点

当前数据平台用户通常已经具备 SQL 能力，但实际使用过程中仍存在较高的“平台认知成本”。

### 问题一：知道业务，不一定知道表

用户知道：

> “我要查订单。”

但可能不知道：

* 应该使用 `dwd_order`
* 还是 `dws_order`
* 还是某个业务宽表
* 表属于哪个数据域
* 当前表的业务定义
* 表的数据更新时间
* 表数据覆盖范围
* 字段之间的区别

因此常见问题不是“不会写 SQL”，而是：

> **不知道应该用哪个数据资产。**

---

### 问题二：知道表，也不一定知道表的含义

例如用户看到：

```text
dwd_order
order_id
pay_amount
gmv
settle_amount
```

可能知道这些是数据字段，但无法快速确认：

* `gmv` 的实际业务口径
* `pay_amount` 是否包含退款
* `settle_amount` 的计算规则
* 哪个字段是推荐用于某个场景的字段

因此需要：

> **表/字段语义解释能力。**

---

### 问题三：有 SQL 能力，但权限流程复杂

用户发现：

> SQL 写好了，但是执行不了。

接下来需要自己判断：

```text
是不是没权限？
↓
缺什么权限？
↓
应该申请什么资源？
↓
应该申请 select 还是 export？
↓
应该申请哪个环境？
↓
应该找谁审批？
↓
申请多久？
↓
以前是不是申请过？
```

权限体系本身成为数据使用门槛。

---

### 问题四：知道 SQL 能写，不代表知道为什么慢

用户可能只知道：

> “这条 SQL 很慢。”

但要进一步定位，通常需要自己分析：

* EXPLAIN
* 索引
* Join 顺序
* 数据量
* 分区条件
* 全表扫描
* SQL 改写
* 统计信息
* 数据倾斜

因此需要：

> **SQL 性能诊断和优化能力。**

---

### 问题五：数据平台能力分散

一个用户完成一次数据使用任务，往往需要跨多个系统：

```text
数据目录
   ↓
表结构
   ↓
权限中心
   ↓
工单
   ↓
SQL 编辑器
   ↓
SQL 审计
   ↓
查询引擎
```

用户需要自己理解这些系统之间的关系。

Data Agent 的核心价值就是：

> **屏蔽平台复杂性，而不是屏蔽 SQL 能力。**

---

# 3. 产品目标

## 3.1 核心目标

### 目标一：降低“理解数据”的门槛

用户只知道业务概念，也能够快速找到：

* 相关表
* 字段
* 指标
* 数据域
* 数据资产

并理解其业务含义。

---

### 目标二：降低“使用权限体系”的门槛

用户不需要理解完整的：

> User → Role → Permission → Policy → Resource

只需要表达：

> “我需要查这张表。”

Agent 自动判断：

* 当前是否有权限
* 缺什么权限
* 当前角色
* 推荐申请权限
* 申请期限
* 审批路径
* 是否已有历史权限

---

### 目标三：降低 SQL 排查和优化成本

用户可以直接：

> “为什么这个 SQL 跑这么慢？”

Agent 自动分析：

* EXPLAIN
* 索引
* Join
* Filter
* 分区
* 数据规模
* SQL 结构

并给出：

* 问题定位
* 优化建议
* 重写 SQL
* 风险说明

---

### 目标四：减少平台操作跳转

尽可能让用户在 Agent 内完成：

```text
找表
↓
理解表
↓
查权限
↓
申请权限
↓
SQL 优化
↓
查询
↓
查看结果
```

而不是频繁跳转多个平台。

---

## 3.2 非目标

Data Agent 第一阶段不试图替代：

* 数据开发人员
* DBA
* 数据 Owner
* 权限审批人
* SQL 编辑器
* 数据治理平台

Agent 是：

> **平台能力的智能编排层。**

而不是新的底层数据平台。

---

# 4. 用户角色

| 用户角色        | 核心诉求                   |
| ----------- | ---------------------- |
| 数据分析用户      | 找表、理解字段、查权限、优化 SQL     |
| 数据研发用户      | 找表、定位元数据、权限处理、SQL 性能优化 |
| 业务数据用户      | 理解数据资产、快速使用已有数据        |
| 数据 Owner    | 解释数据、维护数据语义            |
| 审批用户        | 理解申请人角色、历史权限、风险并辅助审批   |
| DBA / 平台管理员 | SQL 性能治理、权限治理、审计、规则配置  |

---

# 5. 核心产品原则

## 5.1 用户只需要关注“任务”

例如用户说：

> “我想查 9 月华东订单。”

Agent 自动处理：

```text
业务概念
↓
数据资产
↓
权限
↓
SQL
↓
执行环境
```

用户不需要主动学习平台内部结构。

---

## 5.2 LLM 不直接决定关键事实

以下信息必须来自真实系统：

### 权限

权限中心。

### 角色

角色元数据。

### 数据资产

数据目录 / 元数据中心。

### 表结构

Metadata Catalog。

### SQL 执行计划

真实 Query Engine / EXPLAIN。

### 数据结果

真实查询引擎。

LLM 负责：

> 理解、解释、编排、生成建议。

而不是：

> 自己创造事实。

---

## 5.3 Agent 优先解释，平台负责执行

核心原则：

```text
LLM
负责：
理解 + 规划 + 解释

Tool
负责：
查询 + 检查 + 执行

Data Platform
负责：
事实 + 权限 + 数据
```

---

# 6. 核心功能

# 6.1 数据资产发现 Data Discovery

这是 v2.0 相比原 PRD 最重要的新增能力。

## 6.1.1 自然语言找表

用户：

> “我要查销售订单。”

Agent：

```text
找到 4 个相关数据资产：

① dwd_order
用途：订单明细
粒度：订单
更新时间：每天 08:00
推荐度：★★★★★

② dws_sales_order
用途：销售汇总
粒度：用户/天
推荐度：★★★★

③ ads_sales_report
用途：销售报表
粒度：业务日报
推荐度：★★★
```

Agent 给出推荐和原因。

---

## 6.1.2 表解释

用户：

> “dwd_order 是干嘛的？”

返回：

```text
表：dw.dwd_order

业务含义：
销售订单明细表。

数据粒度：
一条订单一条记录。

主要用途：
订单分析、销售分析、订单状态分析。

数据范围：
2025-01-01 至今。

更新频率：
每日更新。

主要字段：
order_id：订单ID
user_id：用户ID
pay_amount：支付金额
order_status：订单状态

注意：
GMV 不建议直接使用 pay_amount，
需要根据业务口径确认。
```

---

## 6.1.3 字段解释

用户：

> “pay_amount 和 settle_amount 有什么区别？”

Agent 从：

* 字段 metadata
* 字段描述
* 数据血缘
* 指标定义
* 数据字典

中获取信息并解释。

---

## 6.1.4 相似表推荐

用户：

> “有没有比 dwd_order 更适合做销售日报的表？”

Agent 自动推荐：

```text
推荐：
dws_sales_daily

原因：
- 已聚合到日维度
- 已计算销售指标
- 查询性能更好
- 当前用户有权限
```

---

# 6.2 数据语义理解 Data Semantic

建立统一的数据语义层：

```text
Business Concept
       ↓
Metric
       ↓
Dimension
       ↓
Data Asset
       ↓
Table
       ↓
Column
```

例如：

```text
GMV

定义：
支付成功订单商品金额

数据来源：
dws_order_summary

时间口径：
pay_time

过滤条件：
order_status = PAID

负责人：
销售数据 Owner
```

Agent 在解释结果或生成 SQL 时必须优先使用 Metric Definition，而不能自行猜测。

---

# 6.3 权限查询 Permission

保留原 PRD 的核心能力。

用户可以直接问：

> “我有 dwd_order 的权限吗？”

Agent 调用：

```text
permission/check
```

返回：

```text
有权限。

资源：
dw.dwd_order

动作：
select

环境：
prod

有效期：
2026-12-31 23:59:59

来源：
销售域数据分析师

权限范围：
销售域只读
```

---

# 6.4 权限原因解释

增加：

> **“为什么我没有权限？”**

例如：

```text
你当前没有 dw.dwd_order 的生产环境 SELECT 权限。

当前角色：
销售域数据分析师

当前角色权限范围：
销售域汇总数据只读

该表：
属于销售订单明细数据

因此当前 Role 不包含该资源。
```

相比只返回：

> “没有权限”

更有价值。

---

# 6.5 权限申请 Agent

用户：

> “我需要查 dwd_order，做 618 销售分析。”

Agent 自动识别：

```text
资源：dw.dwd_order
动作：select
环境：prod
用途：618 销售分析
```

并查询：

```text
当前权限
历史申请
角色边界
推荐期限
审批人
```

然后生成：

```text
权限申请预览

资源：
dw.dwd_order

权限：
SELECT

环境：
PROD

建议期限：
30 天

申请理由：
用于 618 销售复盘

预计审批人：
销售数据 Owner
```

用户确认后才创建工单。

---

# 6.6 智能权限申请期限

不再简单采用：

> 缺失期限 → 默认 30 天。

Agent 根据任务类型给出推荐。

例如：

### 一次性分析

> 建议 1 天。

### 周期性分析

> 建议 30 天。

### 长期项目

> 建议 90 天。

同时必须允许用户修改。

---

# 6.7 权限申请自动衔接任务

这是 Agent 很重要的体验能力。

用户：

> “帮我查 dwd_order 的 9 月订单。”

Agent：

```text
发现：
当前没有查询权限。

是否申请：
dwd_order / SELECT / PROD / 7天
```

用户：

> “申请。”

Agent：

```text
创建工单 T20260910001。

审批完成后，我会继续执行原查询任务。
```

这里 Agent 保存：

```text
Task State
```

例如：

```json
{
  "task": "查询9月订单",
  "resource": "dwd_order",
  "action": "select",
  "env": "prod",
  "pending_action": "query"
}
```

权限通过后继续：

```text
Permission Granted
↓
Query Generate
↓
Query Execute
↓
Return Result
```

---

# 6.8 SQL 助手

用户可以直接贴 SQL：

```sql
SELECT ...
FROM dwd_order
JOIN dim_user ...
```

Agent 自动完成：

```text
SQL Parse
↓
Metadata
↓
EXPLAIN
↓
Rule Engine
↓
LLM Analysis
```

---

## 6.8.1 SQL 问题诊断

输出：

```text
SQL 性能问题：

① dwd_order 存在大范围扫描
② user_id 连接字段缺少有效索引
③ dt 条件选择性较低
④ JOIN 前过滤不充分

预计主要瓶颈：
dwd_order 扫描
```

---

## 6.8.2 SQL 优化

给出：

```text
原 SQL
优化 SQL
优化原因
```

例如：

```text
优化方向：

1. 提前过滤 dwd_order
2. 将条件下推到子查询
3. 使用 dt + user_id 联合索引
4. 减少无用字段
```

---

## 6.8.3 SQL 优化依据

不能只说：

> “建议加索引。”

必须说明：

```text
依据：
EXPLAIN 显示：
type = ALL

预计扫描：
约 1 亿行

现有索引：
idx_dt

建议：
(dt, user_id)

原因：
同时满足时间过滤和 JOIN。
```

---

# 6.9 SQL 自动获取上下文

原 PRD 要求用户提供：

* DDL
* 索引
* EXPLAIN
* 数据量。

这对于用户仍然存在门槛。

改成：

> 用户只提供 SQL。

Agent 尝试自动获取：

```text
SQL
↓
Parse
↓
Identify tables
↓
Metadata Tool
↓
获取 DDL
↓
获取 Index
↓
获取 Row Count
↓
EXPLAIN
```

如果平台权限允许，则自动补全。

只有无法获取时才要求用户补充。

---

# 6.10 Query Assistant

增加真正的数据查询能力。

用户：

> “执行一下这个 SQL。”

Agent：

```text
SQL 检查
↓
权限检查
↓
风险检查
↓
执行
↓
结果
```

结果包括：

```text
执行耗时
扫描数据量
返回行数
执行状态
```

---

# 6.11 查询结果解释

用户拿到结果后可以继续问：

> “这个结果说明什么？”

Agent 基于真实查询结果解释：

```text
订单量：
+12.4%

主要原因：
华东地区 +8.2%
新用户 +4.7%

下降项：
华南 -2.1%
```

---

# 6.12 多轮数据分析

Data Agent 不应该每次都重新理解上下文。

例如：

用户：

> 查 9 月订单量。

Agent：

> 结果……

用户：

> 只看华东。

Agent：

> 结果……

用户：

> 再按照城市拆一下。

Agent：

> 上海、杭州、南京……

用户：

> 上海为什么下降？

Agent 自动理解：

```text
Metric：
订单量

Time：
2026-09

Region：
上海

Analysis Goal：
下降原因
```

形成连续的数据分析任务。

---

# 7. 审批 Agent

保留原 PRD 的审批能力。

审批人进入工单后，Agent 自动生成：

```text
申请人：
张三

角色：
销售域数据分析师

Role 含义：
销售域数据分析

当前申请：
dwd_order / SELECT / PROD / 30天

历史权限：
曾申请过 dwd_order SELECT
已于 2026-01-31 过期

重复检查：
当前无有效权限

风险：
Medium

建议：
通过，30天，仅 SELECT
```

---

# 8. 审批风险分析

规则引擎负责：

```text
重复申请
敏感字段
生产环境
export 权限
长期权限
超出 Role 边界
异常期限
```

Agent 负责解释。

例如：

> **建议谨慎审批。**

原因：

1. 申请资源包含敏感用户字段。
2. 当前 Role 不包含该类数据。
3. 申请期限为 180 天，高于该资源通常申请期限。

---

# 9. 系统总体架构

```text
                         Data Agent
                             │
                  ┌──────────┼──────────┐
                  ↓          ↓          ↓
              Intent      Planning     Memory
                  │          │          │
                  └──────────┼──────────┘
                             ↓
                    Agent Orchestrator
                             │
       ┌────────────┬────────┼───────────┬────────────┐
       ↓            ↓        ↓           ↓            ↓
 Data Discovery  Semantic  Permission  SQL Agent  Query Agent
       │            │        Agent        │            │
       │            │                     │            │
       ↓            ↓                     ↓            ↓
 Metadata        Metric               SQL Parser   Query Engine
 Catalog          Center              EXPLAIN      Execute
       │
       ↓
 Data Catalog
```

底层平台：

```text
Permission Center
Ticket System
Role Metadata
Data Catalog
Metadata Service
SQL Audit
Query Engine
Rule Engine
Workflow System
```

---

# 10. Agent Tool 设计

## 10.1 Data Discovery

```text
/search_data_assets
/get_table_metadata
/get_column_metadata
/get_data_lineage
/search_metrics
/get_metric_definition
/recommend_data_asset
```

---

## 10.2 Permission

```text
/check_permission
/batch_check_permission
/get_user_roles
/get_role_detail
/get_permission_history
/recommend_permission
/create_permission_ticket
/get_ticket_status
```

---

## 10.3 SQL

```text
/parse_sql
/get_table_ddl
/get_indexes
/get_statistics
/explain_sql
/validate_sql
/optimize_sql
/rewrite_sql
```

---

## 10.4 Query

```text
/execute_query
/get_query_status
/get_query_result
/cancel_query
```

---

## 10.5 Approval

```text
/get_ticket_context
/check_duplicate_permission
/analyze_risk
/get_approval_history
```

---

# 11. Agent 路由设计

核心 Intent：

```text
data_discovery
table_explain
column_explain
metric_explain

permission_check
permission_apply
permission_history
role_explain

sql_analyze
sql_optimize
sql_rewrite

query_execute
query_explain

approval_context
approval_risk
```

---

# 12. Agent 核心流程

## 12.1 找表

```text
用户问题
↓
识别业务实体
↓
搜索 Data Catalog
↓
候选数据资产排序
↓
获取 metadata
↓
返回推荐
```

---

## 12.2 权限

```text
用户需求
↓
识别 resource
↓
Permission Check
↓
有权限 → 继续任务
↓
无权限
↓
判断申请需求
↓
生成申请方案
↓
用户确认
↓
提交工单
```

---

## 12.3 SQL 优化

```text
SQL
↓
Parser
↓
识别表
↓
获取 metadata
↓
EXPLAIN
↓
规则检查
↓
LLM 综合分析
↓
优化 SQL
↓
返回优化结果
```

---

## 12.4 数据查询

```text
用户 SQL
↓
SQL Validate
↓
Permission Check
↓
Risk Check
↓
Execute
↓
Result
↓
Explain
```

---

# 13. 数据模型

## 13.1 Data Asset

```text
data_asset
```

核心字段：

```text
asset_id
asset_name
asset_type
business_domain
description
grain
owner
update_frequency
data_range
source_table
quality_level
sensitivity_level
```

---

## 13.2 Metric

```text
metric_definition
```

字段：

```text
metric_id
metric_name
definition
formula
time_dimension
filter_condition
source_asset
owner
version
```

---

## 13.3 Role Metadata

沿用原 PRD：

```text
role_id
role_name
meaning
description
business_domain
responsibilities
permission_boundary
risk_level
owner
docs
```

---

## 13.4 Permission

```text
user_id
role_id
resource_type
resource_id
action
env
effect
valid_from
valid_to
source
```

---

## 13.5 Task State

新增：

```text
task_id
session_id
intent
business_goal
identified_resources
required_permission
generated_sql
query_status
result_reference
pending_action
created_at
updated_at
```

用于实现：

> 权限申请完成后继续执行原任务。

---

# 14. Prompt 设计

## 14.1 System Prompt

核心规则：

```text
你是企业数据平台 Data Agent。

用户通常具备 SQL 和数据分析能力，
你的职责不是替用户完成数据分析本身，
而是降低数据平台的使用复杂度。

你可以帮助用户：

1. 理解表和字段。
2. 搜索数据资产。
3. 理解指标口径。
4. 查询数据权限。
5. 申请数据权限。
6. 解释角色和权限边界。
7. 分析 SQL 性能。
8. 优化 SQL。
9. 执行只读查询。
10. 解释查询结果。

所有平台事实必须通过工具获取。

不得：
- 编造表信息
- 编造字段信息
- 编造权限
- 编造角色含义
- 编造查询结果
- 在没有依据时给出确定性结论。
```

---

# 15. 安全设计

## 15.1 权限

Agent 本身不拥有直接授权能力。

```text
Agent
↓
Permission Center
```

所有授权由平台完成。

---

## 15.2 SQL

默认只允许：

```text
SELECT
```

对于：

```text
INSERT
UPDATE
DELETE
DDL
```

需要更高等级权限和人工确认。

---

## 15.3 导出

Export 属于高风险操作：

```text
查询数据
≠
导出数据
```

导出必须单独进行权限检查。

---

# 16. 可观测性与审计

所有 Agent 行为需要记录：

```text
user_id
session_id
task_id
intent
tool
tool_request
tool_response
sql
permission_check
ticket_id
query_id
result
latency
error
```

重点记录：

> Agent 为什么得出了这个结论？

做到：

```text
用户问题
↓
Agent 决策
↓
调用工具
↓
工具结果
↓
最终答案
```

全链路可追溯。

---

# 17. 性能指标

| 场景     |          目标 |
| ------ | ----------: |
| 表/字段解释 |    P99 < 2s |
| 数据资产搜索 |    P99 < 2s |
| 权限检查   | P99 < 500ms |
| 权限上下文  |    P99 < 2s |
| SQL 分析 |    P99 < 5s |
| SQL 优化 |    P99 < 5s |
| 简单查询   |    P99 < 3s |
| 复杂查询   |          异步 |

---

# 18. 核心产品指标

原 PRD 的指标可以进一步调整。

## 18.1 降低平台使用成本

### 数据资产搜索成功率

用户输入业务需求后，Agent 找到正确数据资产的比例。

### 首次找到正确表的比例

衡量 Data Discovery 是否有效。

### 表语义问题解决率

用户询问：

> “这张表什么意思？”

是否可以直接得到有效答案。

---

## 18.2 权限效率

### 权限自助解决率

用户无需人工咨询即可完成权限处理的比例。

### 权限申请耗时

从：

> “发现没权限”

到：

> “完成申请”

的平均耗时。

### 重复权限申请下降率

---

## 18.3 SQL 效率

### SQL 优化采纳率

### SQL 平均执行耗时下降比例

### SQL 性能问题定位准确率

---

## 18.4 用户体验

最终建议重点关注一个指标：

> ### Data Platform Task Completion Rate

即：

> 用户提出一个数据平台任务后，Agent 最终帮助用户完成任务的比例。

例如：

```text
用户：
我要查 9 月销售订单。

↓
找到正确数据
↓
权限检查
↓
权限申请
↓
SQL
↓
执行
↓
结果
```

整个流程完成，才算：

> **Task Completed**

而不是：

> “Agent 回复了一条消息。”

---

# 19. MVP 版本规划

## MVP 0.1：降低数据理解门槛

优先做：

```text
① 数据资产搜索
② 表解释
③ 字段解释
④ 数据血缘
⑤ 权限查询
⑥ Role 解释
```

目标：

> 用户不知道表的时候，可以快速找到并理解正确的数据。

---

# MVP 0.2：降低权限使用门槛

增加：

```text
① 权限申请
② 历史权限
③ 权限申请推荐
④ 审批人推荐
⑤ 申请状态查询
⑥ 权限申请完成后继续任务
```

---

# MVP 0.3：降低 SQL 使用门槛

增加：

```text
① SQL 自动解析
② 自动获取 DDL
③ 自动获取索引
④ EXPLAIN
⑤ SQL 问题诊断
⑥ SQL 优化
⑦ SQL Rewrite
```

---

# MVP 0.4：完整数据任务闭环

形成：

```text
找表
 ↓
理解表
 ↓
查权限
 ↓
申请权限
 ↓
生成/优化 SQL
 ↓
执行 SQL
 ↓
查询结果
 ↓
继续分析
```

---

# 20. 核心用户体验示例

## 场景一：不知道表是什么意思

用户：

> `dwd_order 是干嘛的？`

Agent：

> `dwd_order` 是销售订单明细数据，粒度为订单。
> 主要用于订单分析和销售分析。
> 当前数据覆盖 2025-01 至今，每日更新。
> 主要字段包括订单 ID、用户 ID、支付金额、订单状态。
> 如果你准备做销售日报，我更推荐 `dws_sales_daily`，因为它已经完成日粒度聚合。

---

## 场景二：不知道应该用哪张表

用户：

> 我要查每天销售额，应该用哪张表？

Agent：

> 推荐 `dws_sales_daily`。
> 原因是它已经聚合到天粒度，并包含标准销售指标。
> `dwd_order` 也可以实现，但需要扫描订单明细，查询成本更高。

---

## 场景三：不知道为什么没有权限

用户：

> 为什么我查不了 dwd_order？

Agent：

> 你当前没有 `dw.dwd_order` 的生产环境 SELECT 权限。
> 你的当前角色是“销售域数据分析师”，该角色目前只覆盖销售域汇总数据。
> 如果你要做订单明细分析，可以申请该表的临时 SELECT 权限。
> 建议期限：7 天。

---

## 场景四：不会走权限流程

用户：

> 那帮我申请。

Agent：

> 已生成申请：

```text
资源：dw.dwd_order
权限：SELECT
环境：PROD
期限：7 天
用途：订单明细分析
```

> 确认提交后，我会创建权限工单。

---

## 场景五：SQL 很慢

用户：

> 这个 SQL 很慢，帮我看看。

Agent 自动获取：

```text
DDL
Index
EXPLAIN
Statistics
```

返回：

```text
主要问题：

1. dwd_order 发生全表扫描
2. WHERE 中虽然有 dt，但现有索引利用率较低
3. JOIN user_id 缺少有效索引
4. 查询返回字段过多

推荐优化：

① 增加联合索引
② 提前过滤订单数据
③ 减少 SELECT 字段
④ 优化 JOIN 顺序
```

然后给出优化 SQL。

---

# 21. 产品最终形态

Data Agent 最终不是：

> 一个“权限机器人”。

也不是：

> 一个“SQL Copilot”。

而应该是：

> ### 数据平台的智能使用层

底层仍然是：

```text
数据平台
├── Data Catalog
├── Metadata
├── Permission
├── Role
├── Workflow
├── Query Engine
├── SQL Audit
└── Data Governance
```

上层增加：

```text
                    Data Agent
                         │
       ┌─────────────────┼─────────────────┐
       ↓                 ↓                 ↓
    理解数据          使用数据平台        优化数据使用
       │                 │                 │
     找表              查权限             SQL诊断
     看字段            申请权限            SQL优化
     看指标            看角色              Query
     看血缘            查历史              分析
```

最终用户体验应该是：

> **“我会 SQL，但我不用记住数据平台里所有的表、字段、角色、权限规则和性能细节。”**

而不是：

> **“我连 SQL 都不会，全部让 Agent 替我做。”**

---

# 22. 核心价值总结

Data Agent 解决的不是“用户不会数据分析”的问题，而是：

### 1. 数据认知成本

> “这张表是什么？”

### 2. 数据发现成本

> “我要找的数据在哪？”

### 3. 权限认知成本

> “为什么没有权限？”

### 4. 权限流程成本

> “我要申请什么？找谁申请？”

### 5. SQL 性能成本

> “为什么 SQL 慢？怎么优化？”

### 6. 平台操作成本

> “这个事情应该去哪个系统做？”

因此产品最终应该实现：

> **用户负责提出数据任务和进行专业判断，Data Agent 负责处理数据平台复杂性。**

这才是这套 Data Agent 对“会 SQL 的专业用户”真正有价值的地方。
