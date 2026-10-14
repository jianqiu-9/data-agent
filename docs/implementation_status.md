# 三份未提交 PRD 的实现状态

对应 `prd_model_tool_calling.md`、`prd_rag.md` 和
`proposals/data-agent-bigdata-prd.md`。本次交付是可在 mock 平台运行的增量实现；
PRD 中的量化指标和生产发布门槛仍须用真实环境及标注数据验收。

| 需求 | 本次代码入口 | 当前状态与待完成项 |
| --- | --- | --- |
| 模型选工具 P0 | `tool_harness.py`、`tooling.py`、`nodes.py` | 已接入五个只读资产/元数据工具的严格参数校验、阶段白名单、预算、拒绝审计和关闭降级。P1 多阶段权限/SQL 工具与 P2 高影响工具仍待实现。 |
| RAG P0/P1/P2 | `rag.py`、`nodes.py`、`routing.py` | 已有受控 Markdown/TXT 入库、租户和 ACL 检索、撤销/版本切换、引用校验、知识问答路由及资产/指标/SQL 示例辅助。当前索引仅在内存中；Embedding 需部署方注入，未接生产向量存储、权限系统与重排模型。 |
| 数据分析 | `analysis.py`、`nodes.py` | 已有基于完整查询结果的 Decimal 汇总和查询 ID 溯源。同比环比、下钻、图表及真实指标口径验收未完成。 |
| SQL 开发 / Text-to-SQL | `nodes.py`、现有平台 SQL 工具 | 已有模型生成只读 SQL 草稿，并调用平台解析与校验；草稿不会自动执行。真实 PostgreSQL/Spark、AST 级策略、Schema Linking 与等价性评测未完成。 |
| Coding Agent | `coding.py`、`cli.py` | 已有独立测试、最多两轮修复和固定镜像 Docker 隔离参数。需要真实 Docker 环境进行隔离攻击测试；补丁工作区、PySpark 与产物存储未接入。 |
| 查询/计算排障 | `diagnostics.py`、`adapters/http.py` | 已有查询状态归属检查、EXPLAIN 及同一次运行日志/指标证据的 OOM 判定；证据不足会明确返回。真实作业、日志、指标、告警接口与标注故障集未接入。 |
| 规划和多步执行 | `planning.py` | 已有只读 DAG 校验、拓扑执行、预算与部分结果保留。尚未接入 Graph 的自动重规划、持久检查点和副作用幂等恢复。 |
| 标准化工具 | `tool_harness.py`、`tooling.py` | 五个候选工具使用严格输入契约；新增可选日志/指标/查询计划能力。其余平台工具尚未统一为完整的版本化输入输出契约。 |
| 上下文和记忆 | `context_memory.py` | 已有预算裁剪和显式同意、TTL 隔离的内存组件；尚未接入运行图与持久存储。 |
| Evaluation / LLMOps | `evaluation.py`、现有工具审计 | 已有确定性任务成功率与 Recall@K 计算及版本元数据。大规模标注集、Trace/Span、看板、告警、灰度和 14 天试点尚未完成。 |

## 本地验证

执行 `.venv/bin/pytest -q`，当前 131 个测试通过。测试使用 mock/伪模型和
HTTP 本地服务，未运行真实 LLM、PostgreSQL、Spark 或 Docker 容器。

## 生产联调输入

需提供 SQL 引擎和方言、计算平台、作业日志/指标 API、身份认证及租户/ACL 来源，
并指定可用于验收的业务域、指标定义和标注任务集。拿到这些信息后才能完成真实接入、
安全评审、性能和 PRD 中的成功率门槛验证。
