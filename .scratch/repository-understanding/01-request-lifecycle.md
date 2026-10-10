# 请求生命周期

## 输入与身份

**事实**：CLI 的 `ask/chat` 或 HTTP 的 `/v1/chat` 最终调用 `DataAgentRuntime.chat(user_id, session_id, message, context)`。HTTP 请求用 Pydantic 检查非空身份、消息及环境，按会话绑定用户；HTTP `/v1/resume` 只接受已中断的同一用户会话。Runtime 把输入写入图 State，并将用户消息追加到 `messages`。

## 路由

**事实**：`prepare` 整理消息并设置任务信息。`route` 默认调用规则路由器，按关键词及正则提取 SQL、表、字段、角色、工单、DAG 等实体，并给出一个意图。可选 LLM 路由要求输出能通过 `IntentResult` 校验，置信度低于阈值或报错时回退规则路由。图通过 `INTENT_TO_NODE` 进入固定业务节点。

## 工具

**事实**：`ToolRegistry` 要求平台适配器实现 `TOOL_NAMES` 的 37 个方法。节点通过 `ToolBatch.call` 调用，批次汇总工具名及审计事件。可选 `audit_sink` 可以接外部审计；默认工具记录进入图 State。内存适配器供演示，HTTP 适配器转发至数据平台并用 `X-User-Id` 传身份。

## 记忆

**事实**：`AgentState` 留存消息、意图、资源、SQL、权限预览、工单、待续任务、查询结果引用及审计数据。`messages/audit_events/tool_calls` 使用累加 reducer。图默认 `MemorySaver`，同一 `session_id` 可续上下文；要跨进程恢复，需要注入持久化 checkpointer。LLM 路由只接收 `_routing_state` 选出的状态摘要。

## 终止与恢复

**事实**：业务节点通常到 `finalize → END`。`prepare_query` 按 SQL 校验和权限检查决定执行、转申请或结束；`ticket_status` 只在工单已批准且有待续 SQL 时转 `prepare_query`。申请流程依次中断确认、期限、可能的角色选择。CLI 的循环用于接收下一轮输入和逐次恢复中断，不是自主无限工具循环。

## 结果回写

**事实**：业务节点写入 `response` 和相关 State，`finalize` 将 `response.answer` 追加为 assistant 消息并更新时刻。Runtime 返回完整 `state`、`response`、意图、工具名和审计事件；HTTP 对外只返回 `session_id/status/response/intent` 或中断信息。真正的平台写操作（如创建工单、提交或触发 DAG）发生在对应工具调用，不是在 `finalize`。

## 失败场景

**事实（测试覆盖，并非已证实线上事故）**：LLM 输出非法 JSON 回退规则路由；缺权限时不执行查询、保存原 SQL 并申请；无角色时不创建工单；多角色时中断要求选择；HTTP 阻止跨用户复用会话、非法请求和未授权访问。另有只读 SQL 校验及缺参数询问。

**推断（代码风险）**：默认 MemorySaver 及 HTTP 的会话所有者表都是进程内状态，服务重启后不能仅靠同一个 session_id 续跑；Runtime 的直接调用接口本身没有 HTTP 层的会话用户绑定检查。生产接入应特别验证持久化、身份绑定及写操作审计。
