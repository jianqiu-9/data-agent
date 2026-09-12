# 数据权限 Agent PRD

## 1. 背景与目标

### 1.1 背景
数据使用用户经常需要确认：
我有没有某张表/某个字段/某个数据域的查询权限？
权限什么时候过期？
没权限时怎么快速申请？
我写的 SQL 能不能优化索引、连表顺序、避免全表扫描？

审批用户经常需要判断：
申请人属于哪个 role？
这个 role 代表什么业务含义和权限边界？
这个 role 之前申请过哪些权限？
之前权限的过期时间是多久？
这次申请是否重复、是否越权、是否建议通过？
因此需要一个“数据权限 Agent”，连接权限中心、工单系统、角色元数据、数据目录、SQL 审计与优化能力，用自然语言完成查询、申请、审批辅助和 SQL 优化建议。

### 1.2 目标
使用用户：自助查权限、查过期时间、一键提单、SQL 优化建议。
审批用户：查看申请人角色语义、历史权限、过期时间、风险建议。
系统：所有权限结论以权限中心为准，Agent 只做编排、解释、汇总，不编造。
安全：申请需用户确认，审批只给建议，不自动批准；全链路审计。

## 2. 用户角色与核心场景
角色	          核心诉求	                           典型问题
使用用户	    查权限、查过期、提单、SQL优化	“我有 dwd_order 的 select 权限吗？什么时候过期？”
审批用户	    看 role 含义、历史权限、风险	“申请人是什么 role？这个 role 之前申请过什么？过期时间多久？”
数据Owner	维护角色元数据、审批策略	    “这个 role 的权限边界是什么？”
管理员	    配置 Agent、工具、审计	        “所有查询和提单都要留痕。”

核心场景：
权限查询：用户问“我有没有销售订单表的查询权限？”
过期查询：返回“有权限，2026-12-31 23:59:59 过期，来源角色：销售域数据分析师。”
一键提单：无权限时，Agent 生成申请单，用户确认后提交。

SQL 优化：用户贴 SQL，Agent 返回索引建议、连表优化、重写 SQL、风险。

审批辅助：审批人打开工单，Agent 展示申请人 role、role 含义、该 role 历史权限及过期时间，并给建议。

## 3. 总体设计思路
### 3.1 架构
LLM Agent + Function Calling + RAG + 规则引擎 + 权限中心 + 工单系统 + SQL优化引擎
LLM：意图识别、自然语言解释、汇总、生成申请理由、生成 SQL 优化说明。
Function Calling：调用权限检查、工单、角色解释、历史权限、SQL优化等接口。
RAG：角色元数据、制度文档、数据目录、权限申请规范。
规则引擎：权限判定、风险规则、重复申请检测、敏感字段识别。
权限中心：唯一权限判定来源。
工单系统：一键提单、审批流。
SQL优化引擎：SQL Parser + EXPLAIN + 统计信息 + 索引建议 + 连表重写。

### 3.2 原则
权限结论必须来自权限中心，LLM 不自行判断。
角色含义必须来自角色元数据或知识库，并标注来源。
一键提单必须二次确认，不能直接授权。
审批 Agent 只给建议，审批动作由人完成。
SQL 优化只给建议，不直接执行 DDL。
所有查询、提单、审批查看、SQL优化都写审计日志。

## 4. 功能需求
### 4.1 使用用户侧
#### 4.1.1 权限查询
输入：
资源：库、表、字段、数据域、API、指标。
动作：select、insert、update、delete、export、download。
环境：prod、staging、dev。
用户：默认当前用户，也支持管理员代查。

输出：
是否有权限。
权限过期时间。
来源角色/策略。
匹配到的授权记录。
无权限时，推荐申请模板。

#### 4.1.2 权限过期时间查询
单权限过期时间。
批量权限过期时间。
永久/长期有效标识。

#### 4.1.3 一键提单申请权限
支持自然语言：
“我要申请**表 30 天查询权限，用于 618 复盘。”
Agent 解析：资源、动作、期限、理由、环境、审批人。
生成申请预览卡片。
用户确认后提交工单。
返回工单号、状态、审批链接。

#### 4.1.4 SQL 索引与连表优化
输入：
SQL。

数据库类型。
表 DDL、现有索引、数据量、EXPLAIN。

可选：慢查询日志、执行计划。
输出：
问题总结。

索引建议：字段、顺序、类型、DDL、依据。
连表优化：驱动表、被驱动表、连接顺序、连接条件、避免笛卡尔积。

SQL 重写建议。
风险提示：写入放大、索引过多、统计信息过期。

不直接执行，需 DBA 审核。
### 4.2 审批用户侧
#### 4.2.1 查看申请人角色
展示：
申请人基本信息。
本次申请使用的 role。
申请人所有 role 列表。
每个 role 的： role_id role_name role 含义 业务域 职责 权限边界 风险等级 Owner 有效期

#### 4.2.2 角色含义解释
例如：
role_name：销售域数据分析师
meaning：可查询销售域非敏感明细与汇总表，不可导出手机号、身份证等敏感字段。
scope：销售域 dwd/dws/ads 层只读。
boundary：生产环境 select，30 天有效，禁止 export。
risk：中风险，涉及订单明细。
来源：角色元数据表 + 制度文档 RAG。

#### 4.2.3 该 role 历史申请权限
按“申请人 + role + 资源”聚合展示：
历史工单号。
申请资源。
动作。
状态：审批中、已通过、已拒绝、已过期、已回收。
生效时间。
过期时间。
是否永久。
是否重复申请。

默认口径：
当前申请人在当前 role 下的历史申请。
可切换为“该 role 下全部用户历史申请”。

#### 4.2.4 审批建议
Agent 汇总：
是否有重复权限。
是否已有相同权限且未过期。
申请期限是否合理。
是否涉及敏感字段/生产环境。
历史审批记录。
建议：通过/拒绝/缩短期限/降级为只读。
必须注明“仅供参考，最终由审批人决定”。

#### 4.2.5 审批操作
通过。
拒绝。
转交。
修改期限。
添加审批意见。

## 5. 数据模型与权限模型
### 5.1 权限模型
User - Role - Permission - Resource - Action - Env - ValidTime

字段	说明
user_id	用户
role_id	角色
resource_type	table/column/api/metric/domain
resource_id	资源唯一标识
action	select/export/update
env	prod/staging
effect	allow/deny
valid_from	生效时间
valid_to	过期时间
source	角色/策略/临时授权

### 5.2 角色元数据表 role_meta
字段	说明
role_id	角色ID
role_name	角色名称
meaning	角色含义
description	详细说明
business_domain	业务域
responsibilities	职责
permission_boundary	权限边界
risk_level	风险等级
owner	角色负责人
docs	关联文档

### 5.3 工单表 permission_ticket
字段	说明
ticket_id	工单号
applicant_id	申请人
role_id	申请角色
resource	资源
action	动作
env	环境
duration_days	期限
reason	理由
status	状态
approver_id	审批人
created_at	创建时间
approved_at	审批时间
grant_id	授权记录ID

### 5.4 历史授权表 grant_history
字段	说明
grant_id	授权ID
user_id	用户
role_id	角色
resource	资源
action	动作
granted_at	生效时间
expires_at	过期时间
status	有效/过期/回收
ticket_id	来源工单
## 6. 接口设计
### 6.1 统一 Agent 入口
POST /api/v1/agent/chat

请求：

json
{
  "user_id": "u123",
  "session_id": "s001",
  "message": "我有没有销售订单表的查询权限？什么时候过期？",
  "context": {
    "env": "prod",
    "current_role": "data_analyst_sales"
  }
}
响应：

json
{
  "type": "permission_check",
  "answer": "你有权限，2026-12-31 23:59:59 过期，来源角色：销售域数据分析师。",
  "cards": [
    {
      "card_type": "permission_result",
      "has_permission": true,
      "expires_at": "2026-12-31T23:59:59+08:00",
      "role_name": "销售域数据分析师",
      "role_meaning": "可查询销售域非敏感表，不可导出敏感字段"
    }
  ],
  "actions": [
    {"label": "申请延长", "action": "create_ticket"},
    {"label": "查看角色说明", "action": "explain_role"}
  ],
  "tool_calls": ["check_permission"]
}
### 6.2 权限检查接口
POST /api/v1/tools/permission/check

请求：

json
{
  "user_id": "u123",
  "resource": {
    "type": "table",
    "db": "dw",
    "name": "dwd_order"
  },
  "action": "select",
  "env": "prod"
}
响应：

json
{
  "has_permission": true,
  "expires_at": "2026-12-31T23:59:59+08:00",
  "grant_source": "role:data_analyst_sales",
  "role_id": "r_sales_analyst",
  "role_name": "销售域数据分析师",
  "role_meaning": "可查询销售域非敏感明细与汇总表，不可导出敏感字段",
  "matched_policy": "prod_sales_readonly",
  "reason": "用户通过角色 data_analyst_sales 获得 select 权限"
}
批量检查：
POST /api/v1/tools/permission/batch-check

### 6.3 一键提单接口
POST /api/v1/tools/permission/tickets

请求：

json
{
  "applicant_id": "u123",
  "role_id": "r_sales_analyst",
  "resource": {
    "type": "table",
    "db": "dw",
    "name": "dwd_order"
  },
  "action": "select",
  "env": "prod",
  "duration_days": 30,
  "reason": "用于618销售复盘",
  "auto_fill": true
}
响应：

json
{
  "ticket_id": "T20260910001",
  "status": "pending",
  "approval_url": "https://approval.example.com/ticket/T20260910001",
  "preview": {
    "applicant": "张三",
    "role_name": "销售域数据分析师",
    "resource": "dw.dwd_order",
    "action": "select",
    "duration_days": 30,
    "reason": "用于618销售复盘"
  }
}
### 6.4 SQL 优化接口
POST /api/v1/tools/sql/optimize

请求：

json
{
  "db_type": "mysql",
  "sql": "SELECT ... FROM dwd_order o JOIN dim_user u ON o.user_id=u.id WHERE o.dt='2026-09-01'",
  "schema": "dw",
  "explain": "...",
  "table_ddl": ["CREATE TABLE dwd_order (...)"],
  "indexes": ["idx_dt"],
  "row_counts": {
    "dwd_order": 100000000,
    "dim_user": 5000000
  }
}
响应：

json
{
  "summary": "dwd_order 过滤条件 dt 已有索引，但 join 字段 user_id 无索引，可能导致大表扫描。",
  "index_suggestions": [
    {
      "table": "dwd_order",
      "columns": ["dt", "user_id"],
      "type": "composite",
      "reason": "先按 dt 过滤，再按 user_id 关联，提升连表效率",
      "ddl": "ALTER TABLE dwd_order ADD INDEX idx_dt_user(dt, user_id);"
    }
  ],
  "join_optimization": [
    {
      "issue": "dim_user 作为被驱动表，关联字段 id 是主键，问题不大；dwd_order 的 user_id 缺索引。",
      "suggestion": "为 dwd_order.user_id 建索引，或使用 dt+user_id 联合索引。"
    }
  ],
  "rewritten_sql": "SELECT ...",
  "risk": ["新增索引会影响写入性能，建议低峰期执行"]
}
### 6.5 审批上下文接口
GET /api/v1/tools/approval/tickets/{ticket_id}/context

响应：

json
{
  "ticket": {
    "ticket_id": "T20260910001",
    "resource": "dw.dwd_order",
    "action": "select",
    "duration_days": 30,
    "reason": "用于618销售复盘",
    "status": "pending"
  },
  "applicant": {
    "user_id": "u123",
    "name": "张三",
    "department": "销售运营"
  },
  "roles": [
    {
      "role_id": "r_sales_analyst",
      "role_name": "销售域数据分析师",
      "meaning": "可查询销售域非敏感明细与汇总表，不可导出敏感字段",
      "scope": "销售域 dwd/dws/ads 只读",
      "boundary": "生产环境 select，30天有效，禁止 export",
      "risk_level": "medium",
      "owner": "销售数据Owner"
    }
  ],
  "role_permission_history": [
    {
      "ticket_id": "T20260101008",
      "role_id": "r_sales_analyst",
      "resource": "dw.dwd_order",
      "action": "select",
      "status": "approved",
      "granted_at": "2026-01-01T00:00:00+08:00",
      "expires_at": "2026-01-31T23:59:59+08:00"
    },
    {
      "ticket_id": "T20260301012",
      "role_id": "r_sales_analyst",
      "resource": "dw.dws_sales_summary",
      "action": "select",
      "status": "expired",
      "granted_at": "2026-03-01T00:00:00+08:00",
      "expires_at": "2026-03-31T23:59:59+08:00"
    }
  ],
  "duplicate_check": {
    "has_active_same_permission": false,
    "reason": "历史权限已过期"
  },
  "risk": {
    "level": "medium",
    "reasons": ["涉及生产订单明细", "申请期限30天合理", "无敏感字段导出"]
  },
  "agent_recommendation": "建议通过，期限30天，仅 select，禁止 export。"
}
### 6.6 审批操作接口
POST /api/v1/tools/approval/tickets/{ticket_id}/decision

请求：

json
{
  "approver_id": "m001",
  "decision": "approve",
  "duration_days": 30,
  "comment": "同意，禁止导出"
}
响应：

json
{
  "ticket_id": "T20260910001",
  "status": "approved",
  "grant_id": "g20260910001"
}
### 6.7 角色解释与历史权限接口
GET /api/v1/tools/roles/{role_id}/explain

GET /api/v1/tools/users/{user_id}/roles/{role_id}/permission-history?status=all&limit=50

历史权限响应：

json
{
  "user_id": "u123",
  "role_id": "r_sales_analyst",
  "history": [
    {
      "resource": "dw.dwd_order",
      "action": "select",
      "status": "approved",
      "granted_at": "2026-01-01T00:00:00+08:00",
      "expires_at": "2026-01-31T23:59:59+08:00",
      "is_expired": true
    }
  ]
}
## 7. Prompt 设计
### 7.1 系统 Prompt
text
你是数据权限 Agent，服务于数据使用用户和审批用户。

你的能力：
1. 查询用户是否有权限、权限过期时间、来源角色。
2. 帮助用户一键提单申请权限。
3. 优化 SQL 索引和连表查询。
4. 为审批用户汇总申请人角色含义、历史权限、过期时间和风险建议。

硬性规则：
- 权限结论必须调用权限中心工具，不能编造。
- 角色含义必须来自角色元数据或知识库，并标注来源。
- 一键提单必须先生成预览，用户确认后才能提交。
- 审批场景只给建议，不能自动批准或拒绝。
- SQL 优化只给建议，不能直接执行 DDL。
- 输出必须简洁、结构化，包含资源、动作、环境、过期时间。
- 涉及敏感字段、生产环境、导出权限时，必须提示风险。
### 7.2 意图路由 Prompt
text
请判断用户意图，只输出 JSON：
{
  "intent": "permission_check | permission_apply | sql_optimize | approval_context | role_explain | permission_history | unknown",
  "confidence": 0.0-1.0,
  "entities": {
    "resource": "",
    "action": "",
    "env": "",
    "duration_days": null,
    "role_id": "",
    "user_id": "",
    "ticket_id": ""
  }
}
### 7.3 权限查询 Prompt
text
用户问题：{query}
用户ID：{user_id}
上下文：{context}

请调用 check_permission 工具查询权限。
工具返回后，按以下格式回答：
- 是否有权限：是/否
- 资源：{resource}
- 动作：{action}
- 环境：{env}
- 过期时间：{expires_at}
- 来源角色：{role_name}
- 角色含义：{role_meaning}
- 如无权限，给出申请建议。
不要编造未返回的权限。
### 7.4 一键提单 Prompt
text
用户想申请权限：{message}
已知信息：{entities}

请完成：
1. 补全资源、动作、环境、期限、理由。
2. 如果缺失期限，默认 30 天。
3. 如果缺失理由，提示用户补充。
4. 调用 create_permission_ticket 前，先生成预览卡片。
5. 只有用户确认后才提交。

输出 JSON：
{
  "need_confirm": true,
  "preview": {
    "resource": "",
    "action": "",
    "env": "",
    "duration_days": 30,
    "reason": ""
  }
}
### 7.5 审批上下文 Prompt
text
你是审批辅助 Agent。请根据以下信息生成审批摘要：
申请人：{applicant}
本次申请：{ticket}
申请人角色：{roles}
角色历史权限：{role_permission_history}
重复检查：{duplicate_check}
风险规则：{risk}

请输出：
1. 申请人属于哪个 role。
2. 该 role 表示什么意思，权限边界是什么。
3. 该 role 之前申请过哪些权限。
4. 之前权限的过期时间是多久，是否已过期。
5. 本次申请是否重复。
6. 风险等级和建议。
7. 注明“仅供参考，最终由审批人决定”。

要求：只基于输入数据，不编造历史记录。
7.6 SQL 优化 Prompt
text
你是 SQL 优化专家。请根据以下信息优化 SQL：
数据库类型：{db_type}
SQL：{sql}
表结构：{ddl}
现有索引：{indexes}
EXPLAIN：{explain}
数据量：{row_counts}

请输出 JSON：
{
  "summary": "",
  "index_suggestions": [
    {
      "table": "",
      "columns": [],
      "type": "single|composite|covering",
      "reason": "",
      "ddl": ""
    }
  ],
  "join_optimization": [
    {
      "issue": "",
      "suggestion": "",
      "driving_table": "",
      "driven_table": ""
    }
  ],
  "rewritten_sql": "",
  "risk": []
}

规则：
- 索引建议要考虑最左前缀、选择性、覆盖索引、写入成本。
- 连表优化要考虑小表驱动大表、关联字段索引、避免笛卡尔积。
- 不确定时说明需要更多统计信息，不要编造。
- 不直接执行 DDL。
## 8. 关键流程
### 8.1 权限查询流程
用户自然语言提问。

Agent 识别意图和实体。

调用权限中心 check_permission。

调用角色元数据解释 role。

生成回答：是否有权限、过期时间、来源角色、角色含义。

无权限时推荐一键提单。

### 8.2 一键提单流程
用户说“申请权限”。

Agent 解析资源、动作、期限、理由。

生成预览卡片。

用户确认。

调用工单接口创建工单。

返回工单号和审批链接。

### 8.3 审批辅助流程
审批人打开工单。

Agent 调用 approval_context。

聚合申请人 role、role 含义、历史权限、过期时间。

调用规则引擎检查重复、敏感、风险。

生成审批建议。

审批人决策。

### 8.4 SQL 优化流程
用户输入 SQL。

Agent 获取 DDL、索引、EXPLAIN。

SQL Parser 解析。

规则引擎检查索引失效、连表顺序。

LLM 汇总建议和重写 SQL。

返回建议，不执行。

## 9. 非功能需求
### 9.1 安全
Agent 服务账号只读权限中心，不能直接授权。

提单以用户身份提交。

审批操作需审批人 token。

敏感字段脱敏。

全链路审计：谁查了谁、查了什么、申请了什么、审批看了什么。

### 9.2 性能
权限检查 P99 < 500ms。

审批上下文聚合 P99 < 2s。

SQL 优化 P99 < 5s，复杂 SQL 可异步。

角色元数据、权限检查结果可短 TTL 缓存。

### 9.3 准确性
权限结论 100% 来自权限中心。

历史权限展示必须带工单号和过期时间。

角色含义必须带来源。

SQL 建议必须带依据和风险。

## 10. 指标与迭代
### 10.1 指标
权限查询准确率。

自助提单率。

审批平均耗时。

重复申请下降率。

SQL 建议采纳率。

用户满意度。

### 10.2 迭代
MVP：权限查询、过期时间、一键提单、审批上下文，SQL 索引优化、连表优化、批量权限查询。

三期：NL2SQL介入。

## 11. 总结
这个数据权限 Agent 的核心是：

对使用用户：查权限、查过期、一键提单、SQL 优化。

对审批用户：看懂 role、看懂历史权限、看懂过期时间、获得风险建议。

技术上：LLM 做编排和解释，权限中心做判定，工单系统做申请审批，SQL 引擎做优化，所有结论可追溯、可审计、不越权。