# Agent 开发学习与实践手册

> 目标：以 `agents-from-scratch`、LangGraph 101、LangGraph 官方示例，以及后续的 OpenHands / Research Agent 为学习主线，把 Agent 从“会调用 LLM”提升到“能设计、开发、排障和上线 Agent 系统”。
>
> 适合：有 Python / Java 后端经验、刚系统学习 Agent 的开发者。
>
> 核心学习原则：**先跑通 → 画架构 → 追调用链 → 改 Tool → 改 State → 自己重写 → 再做真实项目。**

---

## 0. 推荐学习项目与源码阅读顺序

### 第一阶段：agents-from-scratch

建议作为第一份完整学习材料。

重点关注：

- LangGraph 基础
- Agent Loop
- Tool Calling
- Evaluation
- Human-in-the-loop
- Memory
- 邮件类真实 Agent

学习方式不是从头读到尾，而是围绕一个请求追调用链：

```text
用户请求
  ↓
Agent 入口
  ↓
State
  ↓
LLM
  ↓
是否产生 Tool Call
  ├── 否 → Final Answer
  └── 是
       ↓
      Tool
       ↓
   Tool Result
       ↓
      LLM
       ↓
   继续 / 结束
```

### 第二阶段：LangGraph 101 / 官方示例

重点搞懂：

- State
- Node
- Edge
- Conditional Edge
- Tool Node
- Checkpoint
- Memory
- Human-in-the-loop
- Evaluation

### 第三阶段：自己写一个极简 Agent

只保留：

```text
main.py
agent.py
state.py
tools.py
```

实现：

```text
User
 ↓
LLM
 ↓
Tool Call
 ↓
Tool
 ↓
Tool Result
 ↓
LLM
 ↓
Answer
```

### 第四阶段：Research Agent

增加：

```text
Planner
Researcher
Search Tool
Document Retriever
Analyst
Writer
```

最终演化为：

```text
ResearchOS
├── Planner
├── Researcher
├── Analyst
├── Writer
├── Search Tool
├── Financial Tool
├── RAG
├── Memory
├── Evaluation
└── Observability
```

### 第五阶段：OpenHands

等基础 Agent 理解以后，再看复杂 Coding Agent。

重点研究：

- Agent Loop
- Tool / Action
- Terminal
- Browser
- State
- 长流程任务
- 错误恢复
- 复杂工具编排

---

# 一、Agent 基本设计

## Q1：ReAct 和 Plan-and-Execute 差在哪？实际项目为什么选这个不选那个？

### ReAct

ReAct 可以理解成：

```text
思考当前要做什么
    ↓
调用工具
    ↓
观察结果
    ↓
继续判断
    ↓
调用下一个工具
    ↓
最终回答
```

它的特点是：

- 动态
- 边走边决定
- 对不确定任务比较灵活
- 可以根据工具结果随时改变路线

例如：

```text
用户：帮我分析某家公司最近为什么上涨

LLM
 ↓
搜索新闻
 ↓
发现财报数据重要
 ↓
查财报
 ↓
发现行业因素重要
 ↓
查行业数据
 ↓
综合分析
```

### Plan-and-Execute

Plan-and-Execute 更像：

```text
用户问题
 ↓
Planner
 ↓
生成完整计划
 ↓
┌──────────┬──────────┬──────────┐
任务1       任务2       任务3
 ↓           ↓           ↓
执行         执行         执行
 ↓           ↓           ↓
└──────────┴──────────┴──────────┘
             ↓
          汇总结果
```

优点：

- 长任务更容易管理
- 可以展示任务计划
- 可以并行执行相互独立的任务
- 更适合复杂 Workflow

缺点：

- 初始计划可能错误
- 环境变化后需要重新规划
- 简单任务使用它会增加复杂度

### 实际怎么选？

不要问“哪个更高级”，而应该问：

> **任务是否需要提前知道整体步骤？**

| 场景 | 推荐 |
|---|---|
| 简单问答 | 普通 LLM |
| 查一个数据 | ReAct |
| 动态搜索 | ReAct |
| 工具结果高度不确定 | ReAct |
| 长流程研究 | Plan-and-Execute |
| 多个独立子任务 | Plan-and-Execute |
| 可以并行执行 | Plan-and-Execute |
| 强流程业务 | Workflow / Graph |
| 既需要计划又需要动态调整 | Plan + ReAct |

对于 Research Agent：

```text
Planner
 ↓
定义研究问题
 ↓
Research Agent 动态搜索
 ↓
Analyst
 ↓
Writer
```

通常比纯 ReAct 更容易控制。

**核心原则：能用 Workflow 解决的问题，不要强行交给 Agent 自由发挥。**

---

## Q2：Agent 从接问题到调工具再到出结果，中间具体走了哪几步？

典型流程：

```text
1. 接收用户请求
        ↓
2. 加载当前会话 State
        ↓
3. 构建 Prompt / Context
        ↓
4. 调用 LLM
        ↓
5. 判断 LLM 输出
        ↓
6. 如果没有 Tool Call
        ↓
7. 直接返回答案

如果有 Tool Call：

        ↓
8. 校验 Tool 名称
        ↓
9. 校验参数 Schema
        ↓
10. 权限检查
        ↓
11. 执行 Tool
        ↓
12. Tool 返回结果
        ↓
13. 把 Tool Result 写回 State
        ↓
14. 再次调用 LLM
        ↓
15. 判断继续还是结束
        ↓
16. 最终 Answer
```

因此 Agent 最核心的循环是：

```text
LLM
 ↓
Tool Call
 ↓
Tool
 ↓
Observation
 ↓
LLM
```

这就是理解 Agent 的第一条主线。

---

## Q3：怎么判断该继续调工具，还是直接收尾给答案？

可以分成三层判断。

### 第一层：LLM 是否返回 Tool Call

```text
LLM
 ├── tool_calls != empty → 执行 Tool
 └── tool_calls == empty → Final Answer
```

### 第二层：业务状态判断

即使 LLM 想调用 Tool，也应该检查：

```text
是否还有必要？
是否已经得到足够证据？
是否超过最大 Tool 次数？
是否超时？
是否已经满足任务完成条件？
```

例如：

```python
if state.tool_calls >= MAX_TOOL_CALLS:
    return FINAL

if state.elapsed_time > TIMEOUT:
    return FINAL

if state.required_evidence_complete:
    return FINAL
```

### 第三层：任务完成判定

复杂 Agent 最好定义明确的 `done` 条件。

例如 Research Agent：

```text
company_basic_info = True
financial_data = True
industry_info = True
competitor_info = True
risk_analysis = True
```

全部满足后：

```text
done = True
```

而不是无限依赖 LLM 自己决定。

---

## Q4：多轮对话的 State 怎么存？哪些信息该放进当前上下文？

建议把 State 分成：

```text
Conversation State
├── messages
├── user_query
├── current_task
├── tool_results
├── intermediate_results
├── current_step
├── user_preferences
└── execution_metadata
```

不要把所有历史数据都塞给 LLM。

### 当前上下文应该放什么？

优先级：

1. 当前用户问题
2. 当前任务目标
3. 当前步骤需要的信息
4. 最近几轮必要对话
5. 必要的 Tool Result
6. 与任务相关的长期记忆

例如：

```text
当前任务：
分析某公司

当前步骤：
分析竞争格局

当前上下文：
- 公司名称
- 已知竞争对手
- 最近搜索结果
- 用户要求的分析角度
```

而不是把过去几个月所有聊天记录全部塞进去。

---

## Q5：单 Agent 调多个工具，和 Multi-Agent 协作，实际用起来区别在哪？

### 单 Agent + 多 Tool

```text
                 Agent
                   │
       ┌───────────┼───────────┐
       ↓           ↓           ↓
    Search      Database      Calculator
```

优点：

- 简单
- 状态集中
- 调试容易
- Token 成本较低
- 延迟通常较低

适合：

- Research
- 客服
- 数据查询
- 简单自动化

### Multi-Agent

```text
              Manager
             /   |    \
            /    |     \
     Research  Analyst  Writer
```

每个 Agent 有自己的角色。

优点：

- 专业职责隔离
- 复杂任务更清晰
- 可以让不同 Agent 使用不同模型 / Prompt / Tool
- 可以并行执行

缺点：

- State 更复杂
- Agent 之间通信复杂
- Token 成本增加
- 调试困难
- 更容易出现重复工作

### 实际选择

优先：

```text
Single Agent + Tools
```

只有出现明确的职责边界时再 Multi-Agent。

一个很好的判断方法：

> **如果把第二个 Agent 换成一个 Tool 就能解决，就不要 Multi-Agent。**

---

## Q6：碰到需要人工确认的操作，Human-in-the-Loop 怎么设计才不卡流程？

典型流程：

```text
Agent
 ↓
准备执行敏感操作
 ↓
暂停
 ↓
生成 Approval Request
 ↓
等待人工
 ├── Approve → 继续
 ├── Reject → 结束 / 改路线
 └── Edit → 修改参数后继续
```

关键不是简单地：

```python
input("确认？")
```

而是要把人工审批做成一个**可持久化的状态**。

例如：

```text
Approval
├── approval_id
├── task_id
├── user_id
├── action
├── parameters
├── risk_level
├── status
├── created_at
└── expires_at
```

Agent 被暂停以后：

```text
State 持久化
    ↓
等待人工
    ↓
用户审批
    ↓
恢复 State
    ↓
继续执行
```

这样服务重启也不会丢任务。

---

# 二、工具调用

## Q7：Function Calling 到底解决了啥？为啥不让模型直接吐 JSON？

让模型直接输出 JSON：

```json
{
  "tool": "search",
  "query": "xxx"
}
```

存在的问题：

- JSON 格式可能错误
- 工具名称可能拼错
- 参数类型可能错误
- 模型可能在 JSON 之外输出废话
- 应用层需要自己解析

Function Calling 提供的是一种更明确的：

```text
LLM
 ↓
Structured Tool Call
 ↓
应用程序
 ↓
Tool
```

它解决的是：

> **让“模型想调用什么”和“程序实际执行什么”之间有稳定的结构化接口。**

但要注意：

**Function Calling 不是安全边界。**

最终执行 Tool 前仍然需要：

```text
Schema Validation
+
Permission Check
+
Business Validation
```

---

## Q8：工具描述和参数 Schema 怎么写，模型才不容易选错？

工具描述要回答四件事：

```text
1. 什么时候使用？
2. 什么时候不要使用？
3. 参数是什么意思？
4. 返回什么？
```

例如：

```python
@tool
def search_news(
    company: str,
    days: int
):
    """
    Search recent news about a public company.

    Use when the user asks about recent events,
    news, announcements, or market catalysts.

    Do not use for historical financial statements.
    """
```

参数要写清楚：

```text
company:
- 公司名称
- 不接受股票代码时不要传代码

days:
- 最近多少天
- 必须是 1~90
```

工具设计原则：

### 好 Tool

```text
search_news()
get_financial_report()
get_stock_price()
```

### 差 Tool

```text
do_everything()
process_data()
execute()
```

工具越清晰，模型越容易选择。

---

## Q9：两个工具都能干同一件事，Agent 怎么决定调哪个？

不要完全依赖模型。

可以通过：

### 1. Tool Description

明确优先级：

```text
Tool A：
用于实时数据

Tool B：
用于历史数据
```

### 2. 参数约束

让两个 Tool 的输入范围不同。

### 3. Router

增加一个工具选择节点：

```text
User
 ↓
Router
 ├── Real-time → Tool A
 └── Historical → Tool B
```

### 4. 规则优先于模型

例如：

```python
if sensitive_operation:
    use_secure_tool()
```

### 5. 统一抽象

如果两个工具本质上是同一个能力，只是底层实现不同：

```text
get_stock_price()
        ↓
Provider Router
   ├── Provider A
   └── Provider B
```

不要把底层实现差异暴露给 LLM。

---

## Q10：工具报错、缺参数或者超时，是直接重试还是换条路？

不要“一律重试”。

应该先分类：

```text
Tool Error
    │
    ├── 参数错误
    │      ↓
    │   修正参数
    │
    ├── 临时网络错误
    │      ↓
    │   Retry
    │
    ├── 超时
    │      ↓
    │   Retry / Fallback
    │
    ├── 权限错误
    │      ↓
    │   不要 Retry
    │
    └── 业务错误
           ↓
       换路线 / 返回用户
```

### 推荐策略

```text
Retry：
- Timeout
- Connection reset
- 429
- 5xx

Don't Retry：
- 401
- 403
- 参数校验失败
- 明确业务失败
```

同时设置：

```text
max_retry = 2~3
exponential backoff
timeout
fallback
```

不要让 Agent 无限重试。

---

## Q11：涉及用户权限、敏感操作，怎么防止 Agent 乱调工具？

必须建立：

```text
LLM
 ↓
Tool Call
 ↓
Permission Layer
 ↓
Business Validation
 ↓
Tool
```

而不是：

```text
LLM → Tool
```

例如：

```python
if not permission_service.can_execute(
    user_id,
    tool_name,
    resource
):
    raise PermissionDenied()
```

对于高风险操作增加：

```text
Permission
+
Human Approval
+
Audit Log
```

例如：

```text
Agent
 ↓
删除数据
 ↓
权限检查
 ↓
风险等级 HIGH
 ↓
人工确认
 ↓
执行
```

**LLM 永远不能成为最终权限判断者。**

---

# 三、上下文和记忆

## Q12：短期记忆和长期记忆分别解决什么？项目里都怎么存？

### Short-term Memory

解决：

> 当前任务需要记住什么？

典型内容：

```text
messages
current task
tool result
intermediate state
```

通常：

```text
Redis
PostgreSQL
Checkpoint Store
```

### Long-term Memory

解决：

> 用户长期稳定的信息是什么？

例如：

```text
用户偏好
研究方向
常用设置
长期项目
明确要求记住的信息
```

可以：

```text
PostgreSQL
+
Vector DB
```

但不是所有长期信息都应该进向量库。

---

## Q13：聊天记录越堆越长，上下文塞不下了怎么办？

常见方法：

```text
完整历史
   ↓
截断
   ↓
最近 N 轮
   ↓
摘要
   ↓
重要信息提取
   ↓
长期记忆
```

可以采用：

```text
Current Context
=
System Prompt
+
Current Task
+
Recent Messages
+
Summary
+
Retrieved Memory
+
Current Tool Results
```

而不是：

```text
Current Context = 所有历史消息
```

---

## Q14：为什么有时候做历史消息摘要，而不是一直保留完整对话？

因为上下文窗口不是无限的。

而且历史消息存在：

```text
Token 成本
延迟
噪声
注意力稀释
```

例如 100 轮对话：

```text
真正重要信息：10%
无关信息：90%
```

摘要的目的不是简单压缩文字，而是：

> **保留未来任务可能继续使用的事实、决定和约束。**

好的 Summary 应该包含：

```text
用户目标
关键事实
已经做出的决定
未解决问题
用户偏好
重要约束
```

---

## Q15：长期记忆用向量库，什么内容值得存？怎么别召回一堆没用的？

不是：

```text
聊天记录全部 Embedding
```

而是：

```text
值得复用的信息
```

例如：

```text
用户明确偏好
长期项目背景
稳定的工作方式
明确要求记住的事实
重要历史决策
```

不值得存：

```text
今天问了一个什么小问题
临时搜索结果
一次性的闲聊
过期信息
```

### 防止召回噪声

采用：

```text
Metadata Filter
 ↓
Vector Search
 ↓
Top-K
 ↓
Rerank
 ↓
Relevance Threshold
 ↓
最终 Context
```

例如：

```text
user_id = xxx
memory_type = preference
status = active
```

再做语义检索。

---

# 四、RAG 和 Agent

## Q16：Agent + RAG 跟普通 RAG 问答，最大的区别是什么？

普通 RAG：

```text
User
 ↓
Query
 ↓
Retriever
 ↓
Documents
 ↓
LLM
 ↓
Answer
```

流程相对固定。

Agent + RAG：

```text
User
 ↓
Agent
 ↓
判断是否需要知识库
 ↓
Retriever
 ↓
结果
 ↓
Agent 判断是否足够
 ├── 足够 → Answer
 └── 不足 → 换 Query / 再检索 / 调其他 Tool
```

因此最大的区别：

> **普通 RAG 是固定检索链路；Agent + RAG 可以把检索当成一种可决策、可迭代的工具。**

---

## Q17：什么时候走向量检索，什么时候关键词检索更合适？

### Vector Search

适合：

```text
语义相似
自然语言问题
概念匹配
表达方式不同
```

例如：

```text
“这家公司为什么赚钱能力变强了？”
```

### Keyword / BM25

适合：

```text
精确关键词
公司名
产品名
股票代码
合同编号
错误码
专业术语
```

例如：

```text
“世运电路 2025 年 ROE”
```

### 实际生产系统

通常推荐 Hybrid Search：

```text
Query
 ├── Vector Search
 └── Keyword Search
        ↓
      Merge
        ↓
      Rerank
        ↓
      Top-K
```

---

## Q18：检索结果不靠谱，先查哪块？切片、Embedding、Top-K 还是 Rerank？

建议按这个顺序排查：

```text
① 数据是否正确
        ↓
② Chunk 是否合理
        ↓
③ Query 是否正确
        ↓
④ Embedding 是否合适
        ↓
⑤ Top-K 是否合理
        ↓
⑥ Rerank 是否需要
        ↓
⑦ Prompt 是否正确使用检索结果
```

不要一上来就换 Embedding。

### 一个典型 Bad Case

用户问：

> “公司 2025 年收入增长多少？”

检索不到。

应该逐层检查：

```text
原文有没有？
 ↓
Chunk 是否把年份和收入切开了？
 ↓
Query 是否包含“2025 / revenue / growth”？
 ↓
Keyword Search 是否能命中？
 ↓
Vector Top-K 是否包含目标 Chunk？
 ↓
Rerank 有没有把正确 Chunk 排掉？
 ↓
LLM 有没有正确使用 Chunk？
```

---

## Q19：模型回答里的知识来源，怎么做可追溯？

必须保留：

```text
Document ID
Chunk ID
Source URL / File
Page
Timestamp
Retriever Score
Rerank Score
```

最终：

```text
Answer
 ↓
Citation
 ↓
Source
 ↓
Document
 ↓
Original Content
```

例如：

```text
[1] 公司 2025 年年报，第 87 页
[2] 公司公告，2026-08-12
[3] 行业报告，第 23 页
```

内部结构可以：

```json
{
  "answer": "...",
  "citations": [
    {
      "document_id": "xxx",
      "chunk_id": "xxx",
      "page": 87
    }
  ]
}
```

这样才能做到：

> **回答可解释、可审计、可回溯。**

---

# 五、效果与上线

## Q20：怎么判断一个 Agent 好不好？除了“看着还行”，还有哪些硬指标？

建议至少看 6 类：

### 1. Task Success Rate

```text
成功完成任务数 / 总任务数
```

### 2. Tool Success Rate

```text
成功 Tool Call / 总 Tool Call
```

### 3. Answer Accuracy

答案是否正确。

### 4. Citation Accuracy

引用是否真的支持答案。

### 5. Latency

```text
P50
P95
P99
```

### 6. Cost

```text
平均 Token
平均请求成本
单任务成本
```

进一步还可以看：

```text
Tool Calls / Task
Turns / Task
Retry Rate
Fallback Rate
Human Approval Rate
Abandonment Rate
```

---

## Q21：工具调用成功率怎么统计？任务完成率又怎么算？

### Tool Success Rate

不要只看 HTTP 200。

建议：

```text
Tool Success
=
请求成功
+
参数有效
+
返回结果有效
+
业务操作成功
```

指标：

```text
tool_success_rate
=
successful_tool_calls / total_tool_calls
```

按工具拆：

```text
search_success_rate
database_success_rate
financial_api_success_rate
```

### Task Completion Rate

定义一个任务的成功标准。

例如 Research Task：

```text
报告生成
+
关键章节存在
+
引用数量达到要求
+
事实检查通过
```

然后：

```text
task_completion_rate
=
completed_tasks / total_tasks
```

注意：

> **Tool 成功 ≠ Task 成功。**

一个 Agent 可以调用 20 个 Tool 全成功，但最终报告仍然错误。

---

## Q22：Agent 响应很慢，一般从哪些地方开始排查？

建议：

```text
总耗时
 ↓
├── LLM
├── Tool
├── RAG
├── Database
├── Network
└── Agent Loop
```

重点看：

### 1. LLM Latency

```text
time_to_first_token
total_generation_time
```

### 2. Tool Latency

```text
search = 2s
financial_api = 5s
database = 0.2s
```

### 3. Tool 是否串行

原来：

```text
Search A → 2s
Search B → 2s
Search C → 2s

总计 = 6s
```

如果独立：

```text
A ─┐
B ─┼→ 并行
C ─┘

总计 ≈ 2s
```

### 4. Agent 是否循环过多

```text
LLM → Tool → LLM → Tool → LLM → Tool...
```

应该限制：

```text
max_steps
max_tool_calls
timeout
```

---

## Q23：Token 烧得太快，你会从哪些环节压成本？

优先级：

```text
① 减少无意义 Agent Loop
② 减少 Context
③ 压缩 Tool Result
④ 减少 RAG Chunk
⑤ Tool Result 结构化
⑥ 简化 System Prompt
⑦ 小模型处理简单任务
⑧ 缓存
⑨ 批量 / 并行调用
```

典型架构：

```text
Router
 ├── 简单任务 → Small Model
 └── 复杂任务 → Large Model
```

不要：

```text
所有问题
 ↓
最贵模型
```

### 特别容易浪费 Token 的地方

```text
搜索结果原文全部塞给 LLM
数据库返回几万行
历史消息全部保留
Tool Result 没有限制
Agent 无限制循环
```

---

## Q24：线上出 Bad Case，怎么定位是 Prompt、模型、工具还是 RAG 的问题？

建议建立 Trace：

```text
Request
 ↓
Agent Run
 ↓
LLM Call
 ↓
Tool Call
 ↓
Tool Result
 ↓
LLM Call
 ↓
RAG Retrieval
 ↓
Final Answer
```

每一步记录：

```text
trace_id
run_id
model
prompt_version
input
output
tool_name
tool_args
tool_result
latency
token_usage
error
```

然后定位。

### 情况 A：Tool 选错

可能：

```text
Tool Description
Prompt
Model
Router
```

### 情况 B：Tool 选对，但参数错

可能：

```text
Schema
Prompt
LLM
```

### 情况 C：RAG 找错

可能：

```text
Chunk
Embedding
Retriever
Top-K
Rerank
```

### 情况 D：资料正确，但答案错

可能：

```text
Prompt
Model
Context
```

### 情况 E：答案正确但执行失败

可能：

```text
Tool
API
Permission
Database
Network
```

核心思想：

> **不要只记录最终 Answer，要记录整个 Agent Trace。**

---

## Q25：Demo 准备真上线，还要补啥？日志、监控、重试、权限、限流这些怎么落地？

Demo：

```text
User
 ↓
LLM
 ↓
Tool
 ↓
Answer
```

生产：

```text
                     ┌───────────────┐
                     │ Authentication│
                     └───────┬───────┘
                             ↓
User
 ↓
API Gateway
 ↓
Rate Limit
 ↓
Agent Service
 ↓
Permission
 ↓
Planner / Agent
 ↓
Tool Router
 ↓
Tool
 ↓
Retry / Timeout / Fallback
 ↓
State / Checkpoint
 ↓
LLM
 ↓
Citation / Validation
 ↓
Answer
```

### 1. 日志

至少记录：

```text
trace_id
user_id
session_id
task_id
agent_name
model
prompt_version
tool_name
tool_args
latency
token_usage
error
final_status
```

敏感字段必须脱敏。

### 2. Metrics

至少：

```text
agent_request_total
agent_success_total
agent_failure_total

tool_call_total
tool_success_total
tool_failure_total

task_success_rate
tool_success_rate

latency_p50
latency_p95
latency_p99

token_input
token_output
cost

retry_count
fallback_count
human_approval_count
```

### 3. Retry

```text
Timeout → Retry
429 → Backoff
5xx → Retry

401 / 403 → 不重试
参数错误 → 修参数
业务错误 → 换路线
```

限制：

```text
max_retry = 2~3
```

### 4. Timeout

每一层都应该有：

```text
HTTP Timeout
Tool Timeout
LLM Timeout
Agent Timeout
Task Timeout
```

避免：

```text
一个 Tool 卡住
 ↓
整个 Agent 一直卡住
```

### 5. 权限

必须：

```text
User
 ↓
Identity
 ↓
Permission
 ↓
Tool
```

不能：

```text
LLM → 任意 Tool
```

尤其是：

```text
删除
写数据库
转账
修改配置
发送消息
执行代码
```

必须增加权限 / 审批 / 审计。

### 6. 限流

至少控制：

```text
用户级
Session 级
Agent 级
Tool 级
LLM Provider 级
```

### 7. State 持久化

Agent 执行到一半不能因为：

```text
服务重启
网络断开
人工审批
```

就丢失。

所以复杂 Agent 要有：

```text
Checkpoint
+
Persistent State
```

### 8. Human-in-the-loop

高风险操作：

```text
Agent
 ↓
Approval
 ↓
Human
 ↓
Resume
```

不能依赖前端页面一直保持连接。

### 9. Evaluation

上线前建立固定数据集：

```text
100~1000 个真实任务
```

每次修改：

```text
Prompt
Model
Tool
RAG
Workflow
```

都重新跑。

关注：

```text
Task Success
Tool Accuracy
Answer Accuracy
Citation Accuracy
Latency
Cost
```

否则很容易出现：

> 修好了 A，结果把 B 修坏了。

---

# 六、最终形成一套 Agent 工程方法论

把上面的 25 个问题浓缩成一张图：

```text
                         Agent System
                              │
             ┌────────────────┼────────────────┐
             ↓                ↓                ↓
           Model            Tools            State
             │                │                │
             ↓                ↓                ↓
          Planning       Tool Calling       Memory
             │                │                │
             └────────────────┼────────────────┘
                              ↓
                          Workflow
                              │
                    ┌─────────┴─────────┐
                    ↓                   ↓
                   RAG              Human
                    │              Approval
                    ↓                   │
                    └─────────┬─────────┘
                              ↓
                         Validation
                              ↓
                        Final Answer
                              ↓
                 ┌────────────┼────────────┐
                 ↓            ↓            ↓
               Trace        Metrics       Cost
                 │            │            │
                 └────────────┼────────────┘
                              ↓
                       Production System
```

---

# 七、结合你的背景，推荐的实战项目

最终建议做一个：

# Research Agent / ResearchOS

输入：

```text
“分析某家公司未来两年的投资逻辑，
重点研究行业、竞争格局、财务和产业链。”
```

Agent：

```text
                    User
                      ↓
                   Planner
                      ↓
          ┌───────────┼───────────┐
          ↓           ↓           ↓
       Search       Financial    Documents
          ↓           ↓           ↓
          └───────────┼───────────┘
                      ↓
                   Research
                      ↓
                  Evidence
                      ↓
                   Analyst
                      ↓
                Bull / Bear
                      ↓
                   Writer
                      ↓
              Citation Check
                      ↓
                Research Report
```

第一版只需要：

```text
Python
FastAPI
LangGraph
LLM API
Web Search
SQLite
简单 RAG
```

第二版再增加：

```text
PostgreSQL
Qdrant
Redis
Evaluation
Observability
Human-in-the-loop
```

第三版：

```text
Planner
Researcher
Analyst
Writer

+
Multi-Agent
+
任务队列
+
并行执行
+
缓存
+
权限
+
成本控制
```

---

# 八、源码阅读 Checklist

以后打开任何 Agent GitHub 项目，可以直接按照这个顺序检查：

```text
□ 项目入口在哪里？
□ Agent 初始化在哪里？
□ LLM 初始化在哪里？
□ Prompt 在哪里？
□ Tool 在哪里？
□ Tool Schema 怎么定义？
□ Tool Call 怎么产生？
□ Tool Result 怎么返回？
□ State 定义在哪里？
□ State 如何持久化？
□ Agent Loop 在哪里？
□ Continue / END 条件在哪里？
□ Memory 在哪里？
□ RAG 在哪里？
□ Human-in-the-loop 在哪里？
□ Retry 在哪里？
□ Timeout 在哪里？
□ Permission 在哪里？
□ Trace / Log 在哪里？
□ Evaluation 在哪里？
```

如果能把这 20 个问题回答出来，基本就已经不是“看 Agent 教程”的阶段了。

---

# 九、最重要的学习顺序

```text
LLM
 ↓
Prompt
 ↓
Structured Output
 ↓
Function Calling
 ↓
Tool
 ↓
Agent Loop
 ↓
State
 ↓
LangGraph
 ↓
Memory
 ↓
RAG
 ↓
Planning
 ↓
Human-in-the-loop
 ↓
Evaluation
 ↓
Observability
 ↓
Production
 ↓
Multi-Agent
```

不要反过来从：

```text
Multi-Agent
Autonomous Agent
Agent Swarm
```

开始。

**先把一个 Agent 做明白，再做十个 Agent。**

---

# 十、最终能力目标

学完这一套以后，你应该能够独立回答：

> “为什么这里用 Agent？”

> “为什么这里不用 Agent，直接 Workflow？”

> “为什么需要 Tool Calling？”

> “为什么需要 State？”

> “什么时候 ReAct，什么时候 Plan-and-Execute？”

> “为什么不用 Multi-Agent？”

> “Tool 失败怎么办？”

> “Agent 为什么变慢？”

> “Token 为什么突然暴涨？”

> “RAG 为什么召回错？”

> “线上 Bad Case 到底是谁的问题？”

> “怎么把 Demo 变成生产系统？”

如果这些问题都能从**架构、代码、指标和线上故障**四个角度回答，那么 Agent 开发的基础就真正建立起来了。
