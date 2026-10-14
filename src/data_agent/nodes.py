from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from langgraph.types import interrupt

from data_agent import formatting
from data_agent.models import Intent
from data_agent.routing import IntentRouter, RuleBasedIntentRouter, is_general_sql_optimization_question
from data_agent.state import AgentState
from data_agent.tooling import ToolBatch, ToolRegistry


def _now() -> str:

    """作用：负责 `_now` 对应的处理。
    上游：AgentNodes.finalize, AgentNodes.prepare, InMemoryPlatformAdapter.approve_ticket, InMemoryPlatformAdapter.check_permission, InMemoryPlatformAdapter.create_permission_ticket, InMemoryPlatformAdapter.execute_query。
    下游：无项目内直接调用（通过参数、属性或外部库完成）。
    """
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


class AgentNodes:
    def __init__(
        self,
        tools: ToolRegistry,
        router: IntentRouter | None = None,
        knowledge_qa: Any | None = None,
        access_scope: Any | None = None,
        tool_candidate_model: Any | None = None,
        sql_generation_model: Any | None = None,
        coding_agent: Any | None = None,
        code_tests: Any | None = None,
    ) -> None:
        """作用：负责 `__init__` 对应的处理。
        上游：PlatformAPIError.__init__。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        self.tools = tools
        self.router = router or RuleBasedIntentRouter()
        # knowledge_qa、access_scope 和 tool_candidate_model 均由可信 Runtime 注入。
        self.knowledge = knowledge_qa
        self.access_scope = access_scope
        self.tool_candidate_model = tool_candidate_model
        self.sql_generation_model = sql_generation_model
        self.coding_agent = coding_agent
        self.code_tests = code_tests

    def prepare(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `prepare` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_now。
        """
        previous_task_id = state.get("task_id")
        message = state.get("message", "").strip()
        return {
            "task_id": previous_task_id or uuid4().hex,
            "message": message,
            "business_goal": message,
            "response": {},
            "rag_status": "",
            "citations": [],
            "retrieval_results": [],
            "tool_stage": "",
            "candidate_call": {},
            "candidate_validation": {},
            "candidate_retry_count": 0,
            "created_at": state.get("created_at") or _now(),
            "updated_at": _now(),
        }

    def route(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `route` 对应的处理。
        上游：AgentNodes.route, LlmIntentRouter.route。
        下游：route。
        """
        result = self.router.route(
            state.get("message", ""),
            state.get("context", {}),
            state,
        )
        resources = result.entities.get("resources") or (
            [result.entities["resource"]] if result.entities.get("resource") else []
        )
        return {
            "intent": result.intent.value,
            "intent_confidence": result.confidence,
            "entities": result.entities,
            "identified_resources": resources,
        }

    def discover_assets(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `discover_assets` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_batch, _response, call, format_asset_search, state_update。
        """
        batch = self._batch(state)
        goal = state.get("message", "")
        candidate_state: dict[str, Any] = {}
        search = None
        if self.tool_candidate_model is not None:
            # 模型仅看到 discover 阶段的一项只读契约，不能更改后续权限流程。
            from data_agent.tool_harness import CandidateError, ToolHarness

            harness = ToolHarness(self.tools)
            allowed = {"search_data_assets"}
            prompt = (
                "只输出单个 JSON 对象 {name, arguments}。当前阶段 discover。"
                f"可调用 Schema：{harness.schemas(allowed)}。用户目标：{goal}"
            )
            candidate_state["tool_stage"] = "discover"
            try:
                candidate = self.tool_candidate_model.invoke(prompt)
                content = getattr(candidate, "content", candidate)
                executed = harness.execute(
                    content,
                    allowed=allowed,
                    stage="discover",
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    task_id=state["task_id"],
                    intent=state.get("intent"),
                )
                search = executed.value
                batch.events.append(executed.event)
                batch.names.append(executed.tool)
                candidate_state["candidate_call"] = {"name": executed.tool}
                candidate_state["candidate_validation"] = {"status": "passed"}
            except CandidateError as exc:
                candidate_state["candidate_validation"] = {"status": "rejected", "code": exc.code}
                if exc.event:
                    batch.events.append(exc.event)
            except Exception:
                candidate_state["candidate_validation"] = {"status": "fallback", "code": "model_unavailable"}
        if search is None:
            search = batch.call("search_data_assets", query=goal, limit=5)
        assets = search.get("assets", [])
        for asset in assets[:3]:
            permission = batch.call(
                "check_permission",
                user_id=state["user_id"],
                resource={
                    "type": "table",
                    "database": "dw",
                    "name": asset["asset_name"],
                },
                action="select",
                env=state.get("context", {}).get("env", "prod"),
            )
            asset["permission"] = permission
        recommendation = batch.call(
            "recommend_data_asset",
            goal=goal,
            resources=state.get("identified_resources", []),
        )
        top = assets[0] if assets else {}
        answer = formatting.format_asset_search(search)
        knowledge = self._supporting_knowledge(state, document_type="asset", resource_ids={asset["qualified_name"] for asset in assets[:3]})
        if knowledge["snippets"]:
            answer += "\n\n已授权业务资料：\n" + "\n".join(knowledge["snippets"])
        if recommendation.get("recommended_asset"):
            answer += (
                f"\n\n优先推荐：{recommendation['recommended_asset']}\n"
                f"原因：{recommendation['reason']}"
            )
        response = self._response(
            "data_discovery",
            answer,
            cards=[{"card_type": "asset_search", "assets": assets}],
            actions=[
                {
                    "label": f"查看 {asset['qualified_name']}",
                    "action": "table_explain",
                    "resource": asset["qualified_name"],
                }
                for asset in assets[:3]
            ],
            data={"recommendation": recommendation, "citations": knowledge["citations"]},
        )
        return {
            "response": response,
            **candidate_state,
            "identified_resources": [
                {
                    "type": "table",
                    "database": asset["qualified_name"].split(".", 1)[0],
                    "name": asset["asset_name"],
                }
                for asset in assets[:3]
            ],
            **batch.state_update(),
        }

    def knowledge_qa(self, state: AgentState) -> dict[str, Any]:
        """用当前用户可访问的知识回答；每一轮都重新解析访问范围。"""
        if self.knowledge is None or self.access_scope is None:
            answer = "知识问答尚未启用或未配置可信访问范围。"
            return {"rag_status": "unavailable", "response": self._response("knowledge_qa", answer, data={"rag_status": "unavailable", "citations": []})}
        try:
            scope = self.access_scope(state["user_id"])
            result = self.knowledge.answer(state["message"], scope=scope)
        except Exception:
            # 检索服务失败与空结果不同；不把失败伪装成无资料。
            return {"rag_status": "unavailable", "response": self._response("knowledge_qa", "知识检索当前不可用。", data={"rag_status": "unavailable", "citations": []})}
        data = {"rag_status": result.status, "citations": result.citations, "index_version": result.index_version}
        return {"rag_status": result.status, "citations": result.citations, "response": self._response("knowledge_qa", result.answer, data=data)}

    def query_diagnose(self, state: AgentState) -> dict[str, Any]:
        """排查已有查询 ID；展示平台证据和尚缺的验证材料。"""
        query_id = state.get("entities", {}).get("query_id")
        if not query_id:
            return self._ask_for(state, "query_diagnose", "请提供需要排查的查询 ID。")
        from data_agent.diagnostics import DiagnosisAgent

        diagnosis = DiagnosisAgent(self.tools).query(query_id, user_id=state["user_id"], session_id=state["session_id"], task_id=state["task_id"])
        cause_lines = [item["candidate"] + "：" + item["basis"] for item in diagnosis["causes"]]
        answer = "查询诊断：" + diagnosis["status"] + "。\n" + "\n".join(cause_lines + diagnosis["limitations"])
        return {"response": self._response("query_diagnose", answer, data={"diagnosis": diagnosis})}

    def job_diagnose(self, state: AgentState) -> dict[str, Any]:
        """排查 DAG 运行状态；缺少日志或指标时明确标记证据不足。"""
        dag_id = state.get("entities", {}).get("dag_id")
        if not dag_id:
            return self._ask_for(state, "job_diagnose", "请提供需要排查的 DAG ID。")
        from data_agent.diagnostics import DiagnosisAgent

        diagnosis = DiagnosisAgent(self.tools).job(dag_id, user_id=state["user_id"], session_id=state["session_id"], task_id=state["task_id"])
        answer = "计算任务诊断：" + diagnosis["status"] + "。\n" + "\n".join(diagnosis["limitations"])
        return {"response": self._response("job_diagnose", answer, data={"diagnosis": diagnosis})}

    def code_generate(self, state: AgentState) -> dict[str, Any]:
        """只有可信测试提供者和隔离执行器就绪时才生成并运行代码。"""
        if self.coding_agent is None or self.code_tests is None:
            return {"response": self._response("code_generate", "代码执行环境或独立测试尚未配置。", data={"coding": {"status": "unavailable"}})}
        from data_agent.coding import CodeTask

        goal = state["message"]
        try:
            tests = self.code_tests(goal)
            outcome = self.coding_agent.run(CodeTask(goal=goal, test_source=tests))
        except Exception:
            outcome = {"status": "unavailable", "code": "", "stderr": "生成或沙箱执行失败"}
        answer = "代码测试状态：" + str(outcome["status"])
        return {"response": self._response("code_generate", answer, data={"coding": outcome})}

    def text_to_sql(self, state: AgentState) -> dict[str, Any]:
        """用实时表结构生成只读草稿，验证后展示；本节点不执行查询。"""
        if self.sql_generation_model is None:
            return {"response": self._response("text_to_sql", "SQL 生成模型尚未启用。", data={"draft_status": "unavailable"})}
        import json

        batch = self._batch(state)
        search = batch.call("search_data_assets", query=state["message"], limit=3)
        assets = search.get("assets", [])[:3]
        if not assets:
            return {"response": self._response("text_to_sql", "没有找到可用于生成 SQL 的表，请补充业务对象。", data={"draft_status": "insufficient_schema"}), **batch.state_update()}
        schemas = [batch.call("get_table_metadata", table=asset["qualified_name"]) for asset in assets]
        prompt = (
            "仅输出一条 SELECT 或 WITH 查询 SQL，不要 Markdown。"
            "只能使用给定表和字段。生成的是草稿，不得执行。\n"
            + json.dumps({"goal": state["message"], "tables": schemas}, ensure_ascii=False, default=str)[:16000]
        )
        try:
            answer = self.sql_generation_model.invoke(prompt)
            sql = getattr(answer, "content", answer)
            if not isinstance(sql, str) or len(sql) > 10000 or not sql.strip():
                raise ValueError("模型没有返回有效 SQL")
            sql = sql.strip()
            validation = batch.call("validate_sql", sql=sql)
            if not validation.get("valid"):
                return {"response": self._response("text_to_sql", "生成的 SQL 未通过只读校验，已拒绝展示为可执行草稿。", data={"draft_status": "rejected", "validation": validation}), **batch.state_update()}
            parsed = batch.call("parse_sql", sql=sql)
            allowed_tables = {asset["qualified_name"] for asset in assets}
            if not set(parsed.get("tables", [])).issubset(allowed_tables):
                return {"response": self._response("text_to_sql", "SQL 引用了未提供元数据的表，已拒绝。", data={"draft_status": "rejected"}), **batch.state_update()}
        except Exception:
            return {"response": self._response("text_to_sql", "SQL 生成或校验失败，请补充需求后重试。", data={"draft_status": "unavailable"}), **batch.state_update()}
        data = {"draft_status": "validated_draft", "sql": sql, "validation": validation, "tables": sorted(allowed_tables), "executed": False}
        return {"response": self._response("text_to_sql", "已生成并完成平台只读校验的 SQL 草稿，尚未执行：\n" + sql, data=data), "generated_sql": sql, **batch.state_update()}

    def explain_table(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `explain_table` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _resource_name, _response, call, format_table_metadata, state_update。
        """
        table = self._resource_name(state)
        if not table:
            return self._ask_for(
                state,
                "table_explain",
                "请提供需要解释的表名，例如 dwd_order。",
            )
        batch = self._batch(state)
        metadata, candidate_state = self._candidate_read(state, batch, stage="table_explain", tool="get_table_metadata", fixed_arguments={"table": table})
        lineage = batch.call("get_data_lineage", table=table)
        answer = formatting.format_table_metadata(metadata)
        upstream = "、".join(lineage.get("lineage", {}).get("upstream", [])) or "无"
        downstream = "、".join(lineage.get("lineage", {}).get("downstream", [])) or "无"
        answer += f"\n\n血缘：\n- 上游：{upstream}\n- 下游：{downstream}"
        knowledge = self._supporting_knowledge(state, document_type="asset", resource_ids={metadata.get("qualified_name", "")})
        if knowledge["snippets"]:
            answer += "\n\n背景资料：\n" + "\n".join(knowledge["snippets"])
        response = self._response(
            "table_explain",
            answer,
            cards=[
                {"card_type": "table_metadata", "table": metadata},
                {"card_type": "data_lineage", "lineage": lineage},
            ],
            actions=[
                {"label": "查权限", "action": "permission_check", "resource": table},
                {"label": "搜索相似表", "action": "recommend_asset", "resource": table},
            ],
            data={"metadata": metadata, "lineage": lineage, "citations": knowledge["citations"]},
        )
        return {"response": response, **candidate_state, **batch.state_update()}

    def explain_columns(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `explain_columns` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _infer_table_for_columns, _resource_name, _response, call, format_columns, state_update。
        """
        entities = state.get("entities", {})
        columns = entities.get("columns", [])
        table = self._resource_name(state) or self._infer_table_for_columns(columns)
        if not table or not columns:
            return self._ask_for(
                state,
                "column_explain",
                "请提供字段名和表名，例如 pay_amount 与 settle_amount 在 dwd_order 中有什么区别。",
            )
        batch = self._batch(state)
        metadata = batch.call("get_table_metadata", table=table)
        column_results = []
        candidate_state: dict[str, Any] = {}
        for column in columns:
            result, candidate_state = self._candidate_read(state, batch, stage="column_explain", tool="get_column_metadata", fixed_arguments={"table": table, "column": column})
            if result.get("column"):
                column_results.append(result["column"])
        answer = formatting.format_columns(table, column_results, columns)
        response = self._response(
            "column_explain",
            answer,
            cards=[
                {
                    "card_type": "column_metadata",
                    "table": metadata,
                    "columns": column_results,
                }
            ],
            data={"table": metadata, "columns": column_results},
        )
        return {"response": response, **candidate_state, **batch.state_update()}

    def explain_metric(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `explain_metric` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, call, format_metric, state_update。
        """
        metric_name = state.get("entities", {}).get("metric")
        if not metric_name:
            return self._ask_for(
                state,
                "metric_explain",
                "请提供需要解释的指标名称，例如 GMV 或订单量。",
            )
        batch = self._batch(state)
        result, candidate_state = self._candidate_read(state, batch, stage="metric_explain", tool="get_metric_definition", fixed_arguments={"metric": metric_name})
        if result.get("found"):
            metric = result["metric"]
            answer = formatting.format_metric(metric)
            cards = [{"card_type": "metric_definition", "metric": metric}]
            knowledge = self._supporting_knowledge(state, document_type="metric", resource_ids={metric_name})
            if knowledge["snippets"]:
                answer += "\n\n背景资料（口径以平台实时定义为准）：\n" + "\n".join(knowledge["snippets"])
        else:
            search, candidate_state = self._candidate_read(state, batch, stage="metric_search", tool="search_metrics", fixed_arguments={"query": metric_name, "limit": 5})
            metric = None
            answer = "未找到该指标的标准定义，请确认名称。"
            cards = [{"card_type": "metric_search", "metrics": search.get("metrics", [])}]
            knowledge = {"snippets": [], "citations": []}
        response = self._response(
            "metric_explain",
            answer,
            cards=cards,
            data={"metric": metric, "citations": knowledge["citations"]},
        )
        return {"response": response, **candidate_state, **batch.state_update()}

    def check_permission(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `check_permission` 对应的处理。
        上游：InMemoryPlatformAdapter.batch_check_permission, InMemoryPlatformAdapter.check_duplicate_permission。
        下游：_ask_for, _batch, _resource, _response, call, format_permission, state_update。
        """
        resource = self._resource(state)
        if not resource:
            return self._ask_for(
                state,
                "permission_check",
                "请提供资源名称，例如 dwd_order。",
            )
        action = state.get("entities", {}).get("action", "select")
        env = state.get("entities", {}).get("env", "prod")
        batch = self._batch(state)
        result = batch.call(
            "check_permission",
            user_id=state["user_id"],
            resource=resource,
            action=action,
            env=env,
        )
        preview = None
        history = None
        if not result["has_permission"]:
            recommendation = batch.call(
                "recommend_permission",
                user_id=state["user_id"],
                resource=resource,
                action=action,
                env=env,
                task_goal=state.get("business_goal", ""),
            )
            history = batch.call(
                "get_permission_history",
                user_id=state["user_id"],
                role_id=result.get("role_id"),
                resource=resource,
            )
            preview = {
                **recommendation,
                "resource": resource,
                "applicant_id": state["user_id"],
            }
        answer = formatting.format_permission(result)
        if preview:
            answer += (
                f"\n\n当前没有 {result['resource']} 的 "
                f"{result['env']} 环境 {result['action'].upper()} 权限，"
                "是否同意一键提单？"
            )
        response = self._response(
            "permission_required" if preview else "permission_check",
            answer,
            cards=[
                {"card_type": "permission_result", **result},
                *(
                    [{"card_type": "permission_history", **history}]
                    if history
                    else []
                ),
            ],
            actions=(
                [
                    {"label": "提交权限申请", "action": "permission_apply"},
                    {
                        "label": "查看权限历史",
                        "action": "permission_history",
                        "resource": resource,
                    },
                ]
                if preview
                else [{"label": "查看角色说明", "action": "role_explain"}]
            ),
            data={"permission": result, "history": history},
        )
        return {
            "response": response,
            "permission_result": result,
            "permission_preview": preview,
            "_permission_offer_required": bool(preview),
            "required_permissions": [
                {"resource": resource, "action": action, "env": env}
            ],
            **batch.state_update(),
        }

    def apply_permission(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `apply_permission` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _confirmed, _duration_decision, _resource, _response, _role_decision, call, state_update。
        """
        preview = state.get("permission_preview")
        entities = state.get("entities", {})
        resource = self._resource(state)
        action = entities.get("action", "select")
        env = entities.get("env", "prod")
        if not resource and not preview:
            return self._ask_for(
                state,
                "permission_apply",
                "请提供需要申请权限的资源名称。",
            )

        batch = self._batch(state)
        if not preview:
            recommendation = batch.call(
                "recommend_permission",
                user_id=state["user_id"],
                resource=resource,
                action=action,
                env=env,
                task_goal=state.get("business_goal", ""),
            )
            preview = {
                **recommendation,
                "resource": resource,
                "applicant_id": state["user_id"],
            }
        else:
            preview = dict(preview)
        if entities.get("duration_days"):
            preview["duration_days"] = entities["duration_days"]
        if entities.get("reason"):
            preview["reason"] = entities["reason"]

        confirmation = interrupt(
            {
                "type": "one_click_ticket_confirmation",
                "preview": preview,
                "message": "是否同意一键提单？",
                "options": ["yes", "no"],
            }
        )
        confirmed = self._confirmed(confirmation)
        if not confirmed:
            response = self._response(
                "permission_apply",
                "已取消权限申请，未创建工单。",
                data={"cancelled": True, "preview": preview},
            )
            return {
                "response": response,
                "permission_preview": None,
                **batch.state_update(),
            }

        duration_decision = interrupt(
            {
                "type": "permission_duration",
                "options": [7, 15, 30],
                "recommended": preview.get("duration_days", 7),
                "message": "请选择申请期限",
            }
        )
        duration_days = self._duration_decision(
            duration_decision,
            recommended=preview.get("duration_days", 7),
        )
        preview["duration_days"] = duration_days

        role_result = batch.call("get_user_roles", user_id=state["user_id"])
        roles = role_result.get("roles", [])
        if not roles:
            response = self._response(
                "permission_apply",
                "当前用户没有可用角色，无法自动创建权限工单。"
                "请先联系管理员绑定角色后重试。",
                data={"reason": "no_available_role", "preview": preview},
            )
            return {
                "response": response,
                "permission_preview": preview,
                "_permission_offer_required": False,
                **batch.state_update(),
            }
        selected_role_id = preview.get("role_id")
        if len(roles) > 1:
            role_decision = interrupt(
                {
                    "type": "permission_role",
                    "roles": [
                        {
                            "role_id": role["role_id"],
                            "role_name": role["role_name"],
                            "meaning": role.get("meaning", ""),
                            "business_domain": role.get("business_domain", ""),
                        }
                        for role in roles
                    ],
                    "message": "请选择为哪个角色申请权限",
                }
            )
            selected_role_id = self._role_decision(role_decision, roles)
        elif roles:
            selected_role_id = roles[0]["role_id"]

        if selected_role_id:
            preview["role_id"] = selected_role_id
            selected_role = next(
                (
                    role
                    for role in roles
                    if role.get("role_id") == selected_role_id
                ),
                None,
            )
            if selected_role:
                preview["role_name"] = selected_role.get("role_name")

        application = {
            "resource": preview["resource"],
            "action": preview.get("action", action),
            "env": preview.get("env", env),
            "duration_days": duration_days,
            "reason": preview.get("reason", state.get("business_goal", "")),
            "role_id": selected_role_id,
            "approver": preview.get("approver"),
        }
        ticket = batch.call(
            "create_permission_ticket",
            applicant_id=state["user_id"],
            application=application,
        )
        pending_task = state.get("pending_task") or {}
        answer = (
            f"已创建权限工单 {ticket['ticket_id']}。\n\n"
            f"当前状态：{ticket['status']}\n"
            f"审批链接：{ticket['approval_url']}\n\n"
            "审批完成后，可以让我查询工单状态；如果存在原查询任务，我会继续执行。"
        )
        response = self._response(
            "permission_apply",
            answer,
            cards=[
                {
                    "card_type": "permission_ticket",
                    "ticket": ticket,
                    "application": application,
                }
            ],
            actions=[
                {
                    "label": "查询工单状态",
                    "action": "ticket_status",
                    "ticket_id": ticket["ticket_id"],
                }
            ],
            data={"ticket": ticket, "pending_task": pending_task},
        )
        return {
            "response": response,
            "ticket": ticket,
            "permission_preview": None,
            "_permission_offer_required": False,
            **batch.state_update(),
        }

    def permission_history(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `permission_history` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_batch, _resource, _response, call, format_permission_history, state_update。
        """
        batch = self._batch(state)
        resource = self._resource(state)
        result = batch.call(
            "get_permission_history",
            user_id=state["user_id"],
            role_id=state.get("entities", {}).get("role_id"),
            resource=resource,
        )
        response = self._response(
            "permission_history",
            formatting.format_permission_history(result),
            cards=[{"card_type": "permission_history", **result}],
            data={"history": result},
        )
        return {"response": response, **batch.state_update()}

    def ticket_status(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `ticket_status` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, call, format_ticket_status, state_update。
        """
        ticket_id = state.get("entities", {}).get("ticket_id") or (
            state.get("ticket") or {}
        ).get("ticket_id")
        if not ticket_id:
            return self._ask_for(
                state,
                "ticket_status",
                "请提供工单号，例如 T202609120001。",
            )
        batch = self._batch(state)
        ticket = batch.call("get_ticket_status", ticket_id=ticket_id)
        pending_task = state.get("pending_task") or {}
        continue_query = (
            ticket.get("status") == "approved"
            and pending_task.get("intent") == Intent.QUERY_EXECUTE.value
            and bool(pending_task.get("sql"))
        )
        answer = formatting.format_ticket_status(ticket)
        if continue_query:
            answer += "\n\n权限已通过，正在继续执行原查询任务。"
        response = self._response(
            "ticket_status",
            answer,
            cards=[{"card_type": "ticket_status", "ticket": ticket}],
            data={"ticket": ticket, "continue_query": continue_query},
        )
        update: dict[str, Any] = {
            "response": response,
            "ticket_status": ticket,
            "_continue_query": continue_query,
            **batch.state_update(),
        }
        if continue_query:
            update["generated_sql"] = pending_task["sql"]
        return update

    def explain_role(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `explain_role` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, call, format_role, state_update。
        """
        role_id = state.get("entities", {}).get("role_id")
        if not role_id:
            return self._ask_for(
                state,
                "role_explain",
                "请提供角色名称或 role_id，例如 r_sales_analyst。",
            )
        batch = self._batch(state)
        result = batch.call("get_role_detail", role_id=role_id)
        answer = (
            formatting.format_role(result["role"])
            if result.get("found") and result.get("role")
            else result.get("message", f"未找到角色 {role_id}。")
        )
        response = self._response(
            "role_explain",
            answer,
            cards=[{"card_type": "role_detail", **result}],
            data={"role": result},
        )
        return {"response": response, **batch.state_update()}

    def analyze_sql(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `analyze_sql` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _load_sql_context, _response, _sql, call, format_sql_analysis, state_update。
        """
        sql = self._sql(state)
        if not sql:
            return self._ask_for(
                state,
                "sql_analyze",
                "请提供需要分析的 SQL。",
            )
        batch = self._batch(state)
        validation = batch.call("validate_sql", sql=sql)
        parsed = batch.call("parse_sql", sql=sql)
        context = self._load_sql_context(batch, parsed.get("tables", []))
        explain = batch.call("explain_sql", sql=sql)
        analysis = {
            "validation": validation,
            "parsed": parsed,
            "context": context,
            "explain": explain,
        }
        answer = formatting.format_sql_analysis(
            sql, validation, parsed, context, explain
        )
        knowledge = self._supporting_knowledge(state, document_type="sql_example", resource_ids=set(parsed.get("tables", [])), sql_dialect=state.get("context", {}).get("sql_dialect"))
        if knowledge["snippets"]:
            answer += "\n\n审核 SQL 示例（仅供参考，未执行）：\n" + "\n".join(knowledge["snippets"])
        response = self._response(
            "sql_analyze",
            answer,
            cards=[{"card_type": "sql_analysis", **analysis}],
            actions=[
                {"label": "优化 SQL", "action": "sql_optimize"},
                {"label": "重写 SQL", "action": "sql_rewrite"},
            ],
            data={**analysis, "citations": knowledge["citations"]},
        )
        return {
            "response": response,
            "generated_sql": sql,
            "sql_context": context,
            "sql_analysis": analysis,
            **batch.state_update(),
        }

    def optimize_sql(self, state: AgentState, *, rewrite_only: bool = False) -> dict[str, Any]:
        """作用：负责 `optimize_sql` 对应的处理。
        上游：AgentNodes.rewrite_sql, InMemoryPlatformAdapter.rewrite_sql。
        下游：_ask_for, _batch, _load_sql_context, _response, _sql, call, format_optimization, state_update。
        """
        if (
            not rewrite_only
            and not state.get("entities", {}).get("sql")
            and is_general_sql_optimization_question(state.get("message", ""))
        ):
            return {
                "response": self._response(
                    "sql_optimize",
                    formatting.format_general_sql_optimization(),
                )
            }
        sql = self._sql(state)
        if not sql:
            return self._ask_for(
                state,
                "sql_rewrite" if rewrite_only else "sql_optimize",
                "请提供需要优化的 SQL。",
            )
        batch = self._batch(state)
        validation = batch.call("validate_sql", sql=sql)
        if not validation["valid"]:
            response = self._response(
                "sql_rewrite" if rewrite_only else "sql_optimize",
                "SQL 校验未通过：\n"
                + "\n".join(f"- {error}" for error in validation["errors"]),
                data={"validation": validation},
            )
            return {"response": response, **batch.state_update()}
        parsed = batch.call("parse_sql", sql=sql)
        context = self._load_sql_context(batch, parsed.get("tables", []))
        explain = batch.call("explain_sql", sql=sql)
        context["explain"] = explain
        if rewrite_only:
            result = batch.call("rewrite_sql", sql=sql, context=context)
            analysis = {
                **result,
                "sql": sql,
                "issues": result.get("changes", []),
                "index_suggestions": [],
                "join_optimization": [],
            }
            answer = (
                "SQL 重写结果：\n"
                f"```sql\n{result['rewritten_sql']}\n```\n\n"
                "变化：\n"
                + ("\n".join(f"- {item}" for item in result.get("changes", [])) or "- 无结构性变化")
                + "\n\n风险：\n"
                + "\n".join(f"- {item}" for item in result.get("risk", []))
            )
            response_type = "sql_rewrite"
        else:
            analysis = batch.call("optimize_sql", sql=sql, context=context)
            answer = formatting.format_optimization(analysis)
            response_type = "sql_optimize"
        response = self._response(
            response_type,
            answer,
            cards=[{"card_type": "sql_optimization", **analysis}],
            actions=[
                {"label": "执行优化后的 SQL", "action": "query_execute"},
            ],
            data=analysis,
        )
        return {
            "response": response,
            "generated_sql": analysis.get("rewritten_sql", sql),
            "sql_context": context,
            "sql_analysis": analysis,
            **batch.state_update(),
        }

    def rewrite_sql(self, state: AgentState) -> dict[str, Any]:

        """作用：负责 `rewrite_sql` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：optimize_sql。
        """
        return self.optimize_sql(state, rewrite_only=True)

    def prepare_query(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `prepare_query` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, _sql, call, format_permission_preview, state_update。
        """
        sql = self._sql(state)
        if not sql:
            return self._ask_for(
                state,
                "query_execute",
                "请提供需要执行的只读 SQL。",
            )
        batch = self._batch(state)
        validation = batch.call("validate_sql", sql=sql)
        if not validation["valid"]:
            response = self._response(
                "query_execute",
                "查询未执行，SQL 校验失败：\n"
                + "\n".join(f"- {error}" for error in validation["errors"]),
                data={"validation": validation},
            )
            return {
                "response": response,
                "_query_ready": False,
                **batch.state_update(),
            }
        parsed = batch.call("parse_sql", sql=sql)
        tables = parsed.get("tables", [])
        env = state.get("entities", {}).get("env", "prod")
        checks = [
            {
                "resource": {
                    "type": "table",
                    "database": table.split(".", 1)[0],
                    "name": table.split(".", 1)[-1],
                },
                "action": "select",
                "env": env,
            }
            for table in tables
        ]
        permission = batch.call(
            "batch_check_permission",
            user_id=state["user_id"],
            checks=checks,
        )
        if permission["all_granted"]:
            response = self._response(
                "query_execute",
                "SQL 与权限检查已通过，正在执行查询。",
                data={"validation": validation, "permissions": permission},
            )
            return {
                "response": response,
                "generated_sql": sql,
                "required_permissions": checks,
                "permission_result": permission,
                "_query_ready": True,
                **batch.state_update(),
            }

        missing = next(
            item for item in permission["results"] if not item["has_permission"]
        )
        resource = {
            "type": "table",
            "database": missing["resource"].split(".", 1)[0],
            "name": missing["resource"].split(".", 1)[-1],
        }
        recommendation = batch.call(
            "recommend_permission",
            user_id=state["user_id"],
            resource=resource,
            action="select",
            env=env,
            task_goal=state.get("business_goal", "SQL 查询"),
        )
        preview = {
            **recommendation,
            "resource": resource,
            "applicant_id": state["user_id"],
        }
        answer = (
            f"SQL 校验通过，但当前没有 {missing['resource']} 的 {env} 环境 "
            "SELECT 权限，未执行查询。\n\n"
            + formatting.format_permission_preview(preview)
        )
        response = self._response(
            "permission_required",
            answer,
            cards=[
                {"card_type": "permission_required", **missing},
                {"card_type": "permission_application_preview", "preview": preview},
            ],
            actions=[{"label": "提交权限申请", "action": "permission_apply"}],
            data={"permission": missing, "preview": preview},
        )
        return {
            "response": response,
            "generated_sql": sql,
            "required_permissions": checks,
            "permission_result": permission,
            "permission_preview": preview,
            "pending_task": {
                "intent": Intent.QUERY_EXECUTE.value,
                "sql": sql,
                "resources": tables,
                "pending_action": "query",
            },
            "_query_ready": False,
            "_permission_offer_required": True,
            **batch.state_update(),
        }

    def execute_query(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `execute_query` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, _sql, call, format_query_result, state_update。
        """
        sql = self._sql(state)
        if not sql:
            return self._ask_for(
                state,
                "query_execute",
                "没有可执行的 SQL。",
            )
        batch = self._batch(state)
        result = batch.call(
            "execute_query",
            user_id=state["user_id"],
            sql=sql,
            env=state.get("entities", {}).get("env", "prod"),
        )
        response = self._response(
            "query_execute",
            formatting.format_query_result(result),
            cards=[{"card_type": "query_result", "query": result}],
            actions=[
                {"label": "继续追问结果", "action": "query_explain"},
            ],
            data={"query": result},
        )
        return {
            "response": response,
            "generated_sql": sql,
            "query_status": {
                "query_id": result.get("query_id"),
                "status": result.get("status"),
            },
            "result_reference": result,
            "pending_task": None,
            **batch.state_update(),
        }

    def explain_query_result(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `explain_query_result` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, call, format_query_explanation, state_update。
        """
        reference = state.get("result_reference") or {}
        query_id = reference.get("query_id")
        if not query_id:
            return self._ask_for(
                state,
                "query_explain",
                "当前会话没有可解释的查询结果，请先执行一条查询。",
            )
        batch = self._batch(state)
        result = batch.call("get_query_result", query_id=query_id)
        answer = formatting.format_query_explanation(result, state.get("message", ""))
        response = self._response(
            "query_explain",
            answer,
            cards=[{"card_type": "query_explanation", "query": result}],
            data={"query": result},
        )
        return {"response": response, **batch.state_update()}

    def analyze_query_result(self, state: AgentState) -> dict[str, Any]:
        """对已授权查询的完整结果计算摘要，并保留查询 ID 作为证据。"""
        from data_agent.analysis import DataAnalysisAgent

        measures = state.get("context", {}).get("measures", [])
        if not isinstance(measures, list) or any(not isinstance(item, str) for item in measures):
            measures = []
        analysis = DataAnalysisAgent().summarize(state.get("result_reference") or {}, measures=measures)
        answer = "数据分析状态：" + analysis["status"] + "。\n查询 ID：" + str(analysis.get("query_id"))
        if analysis.get("totals"):
            answer += "\n度量汇总：" + "；".join(f"{name}={value}" for name, value in analysis["totals"].items())
        answer += "\n" + "；".join(analysis.get("limitations", []))
        return {"response": self._response("data_analysis", answer, data={"analysis": analysis, "query": state.get("result_reference")})}

    def approval_context(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `approval_context` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, call, format_approval_context, state_update。
        """
        ticket_id = state.get("entities", {}).get("ticket_id")
        if not ticket_id:
            return self._ask_for(
                state,
                "approval_context",
                "请提供需要辅助审批的工单号。",
            )
        batch = self._batch(state)
        context = batch.call("get_ticket_context", ticket_id=ticket_id)
        response = self._response(
            "approval_context",
            formatting.format_approval_context(context),
            cards=[{"card_type": "approval_context", **context}],
            actions=[
                {"label": "分析审批风险", "action": "approval_risk", "ticket_id": ticket_id}
            ]
            if context.get("found")
            else [],
            data={"approval": context},
        )
        return {
            "response": response,
            "approval_context": context,
            **batch.state_update(),
        }

    def approval_risk(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `approval_risk` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _response, call, format_approval_context, state_update。
        """
        ticket_id = state.get("entities", {}).get("ticket_id") or (
            state.get("approval_context", {}).get("ticket") or {}
        ).get("ticket_id")
        if not ticket_id:
            return self._ask_for(
                state,
                "approval_risk",
                "请提供需要分析风险的工单号。",
            )
        batch = self._batch(state)
        context = batch.call("get_ticket_context", ticket_id=ticket_id)
        if not context.get("found"):
            response = self._response(
                "approval_risk",
                formatting.format_approval_context(context),
                data={"approval": context},
            )
            return {"response": response, **batch.state_update()}
        risk = batch.call(
            "analyze_risk",
            ticket=context["ticket"],
            context={
                "role": context["roles"][0] if context.get("roles") else None,
                "history": context.get("role_permission_history", []),
            },
        )
        history = batch.call("get_approval_history", ticket_id=ticket_id)
        role_name = (
            context["roles"][0]["role_name"] if context.get("roles") else "未知角色"
        )
        answer = (
            f"审批风险等级：{risk['level']}\n\n"
            f"申请人角色：{role_name}\n\n"
            f"风险原因：\n"
            + "\n".join(f"- {item}" for item in risk["reasons"])
            + f"\n\n审批建议：{context['agent_recommendation']}\n\n"
            f"审批历史记录数：{len(history.get('history', []))}"
        )
        response = self._response(
            "approval_risk",
            answer,
            cards=[
                {"card_type": "approval_risk", "risk": risk},
                {"card_type": "approval_history", **history},
            ],
            data={"risk": risk, "history": history},
        )
        return {
            "response": response,
            "approval_context": context,
            **batch.state_update(),
        }

    def generate_dag(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `generate_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_batch, _dag_schedule, _response, call, state_update。
        """
        batch = self._batch(state)
        message = state.get("message", "")
        schedule = self._dag_schedule(message)
        dag = batch.call(
            "generate_dag",
            goal=state.get("business_goal", message),
            schedule=schedule,
            owner=state.get("user_id"),
            resources=state.get("identified_resources", []),
        )
        tasks = "、".join(
            task["task_id"] for task in dag.get("tasks", [])
        )
        answer = (
            f"已生成 DAG：{dag['dag_id']}\n"
            f"调度：{dag.get('schedule', '未指定')}\n"
            f"任务：{tasks or '无'}\n"
            "下一步可以校验、提交或触发运行。"
        )
        response = self._response(
            "dag_generate",
            answer,
            cards=[{"card_type": "dag_definition", "dag": dag}],
            actions=[
                {"label": "校验 DAG", "action": "dag_validate"},
                {"label": "提交 DAG", "action": "dag_submit"},
            ],
            data={"dag": dag},
        )
        return {
            "response": response,
            "dag_definition": dag["dag_definition"],
            "dag_id": dag["dag_id"],
            "dag_status": dag,
            **batch.state_update(),
        }

    def validate_dag(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `validate_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _dag_definition, _response, call, state_update。
        """
        dag_definition = self._dag_definition(state)
        if not dag_definition:
            return self._ask_for(
                state,
                "dag_validate",
                "当前没有可校验的 DAG 定义，请先生成或提供 DAG。",
            )
        batch = self._batch(state)
        result = batch.call(
            "validate_dag",
            dag_definition=dag_definition,
            env=state.get("entities", {}).get("env", "prod"),
        )
        answer = (
            f"DAG 校验结果：{'通过' if result.get('valid') else '未通过'}\n"
            f"错误：{'；'.join(result.get('errors', [])) or '无'}\n"
            f"警告：{'；'.join(result.get('warnings', [])) or '无'}"
        )
        response = self._response(
            "dag_validate",
            answer,
            cards=[{"card_type": "dag_validation", "validation": result}],
            actions=(
                [{"label": "提交 DAG", "action": "dag_submit"}]
                if result.get("valid")
                else []
            ),
            data={"validation": result},
        )
        return {"response": response, **batch.state_update()}

    def submit_dag(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `submit_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _dag_definition, _response, call, state_update。
        """
        dag_definition = self._dag_definition(state)
        if not dag_definition:
            return self._ask_for(
                state,
                "dag_submit",
                "当前没有可提交的 DAG 定义，请先生成或提供 DAG。",
            )
        batch = self._batch(state)
        env = state.get("entities", {}).get("env", "prod")
        validation = batch.call(
            "validate_dag",
            dag_definition=dag_definition,
            env=env,
        )
        if not validation.get("valid"):
            response = self._response(
                "dag_submit",
                "DAG 校验未通过，已阻止提交。\n错误："
                + ("；".join(validation.get("errors", [])) or "未知错误"),
                data={"validation": validation},
            )
            return {"response": response, **batch.state_update()}
        submission = batch.call(
            "submit_dag",
            dag_definition=dag_definition,
            env=env,
        )
        response = self._response(
            "dag_submit",
            f"DAG 已提交：{submission['dag_id']}\n"
            f"状态：{submission['status']}\n"
            f"环境：{submission['env']}\n"
            f"版本：{submission.get('version', '未返回')}",
            cards=[{"card_type": "dag_submission", "submission": submission}],
            actions=[
                {
                    "label": "触发 DAG",
                    "action": "dag_trigger",
                    "dag_id": submission["dag_id"],
                }
            ],
            data={"submission": submission},
        )
        return {
            "response": response,
            "dag_id": submission["dag_id"],
            "dag_status": submission,
            **batch.state_update(),
        }

    def trigger_dag(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `trigger_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _dag_id, _response, call, state_update。
        """
        dag_id = self._dag_id(state)
        if not dag_id:
            return self._ask_for(
                state,
                "dag_trigger",
                "请提供需要触发的 DAG ID，例如 dag_orders。",
            )
        batch = self._batch(state)
        run = batch.call(
            "trigger_dag",
            dag_id=dag_id,
            logical_date=state.get("entities", {}).get("logical_date"),
            conf={},
        )
        response = self._response(
            "dag_trigger",
            f"DAG 已触发：{dag_id}\n"
            f"Run ID：{run['run_id']}\n"
            f"状态：{run['status']}",
            cards=[{"card_type": "dag_run", "run": run}],
            actions=[
                {
                    "label": "查询状态",
                    "action": "dag_status",
                    "dag_id": dag_id,
                }
            ],
            data={"run": run},
        )
        return {
            "response": response,
            "dag_id": dag_id,
            "dag_run": run,
            **batch.state_update(),
        }

    def dag_status(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `dag_status` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _dag_id, _response, call, state_update。
        """
        dag_id = self._dag_id(state)
        if not dag_id:
            return self._ask_for(
                state,
                "dag_status",
                "请提供需要查询的 DAG ID，例如 dag_orders。",
            )
        batch = self._batch(state)
        status = batch.call("get_dag_status", dag_id=dag_id)
        response = self._response(
            "dag_status",
            f"DAG：{dag_id}\n"
            f"当前状态：{status.get('status', 'unknown')}\n"
            f"最近 Run：{status.get('last_run_id', '未返回')}\n"
            f"最近 Run 状态：{status.get('last_run_status', '未知')}",
            cards=[{"card_type": "dag_status", "status": status}],
            data={"dag_status": status},
        )
        return {
            "response": response,
            "dag_id": dag_id,
            "dag_status": status,
            **batch.state_update(),
        }

    def backfill_dag(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `backfill_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_ask_for, _batch, _dag_id, _response, call, state_update。
        """
        dag_id = self._dag_id(state)
        start_date = state.get("entities", {}).get("start_date")
        end_date = state.get("entities", {}).get("end_date")
        if not dag_id or not start_date or not end_date:
            return self._ask_for(
                state,
                "dag_backfill",
                "请提供 DAG ID、开始日期和结束日期，例如 "
                "dag_orders 回填 2026-09-01 到 2026-09-03。",
            )
        batch = self._batch(state)
        result = batch.call(
            "backfill_dag",
            dag_id=dag_id,
            start_date=start_date,
            end_date=end_date,
        )
        response = self._response(
            "dag_backfill",
            f"DAG：{dag_id}\n"
            f"回填区间：{start_date} 至 {end_date}\n"
            f"任务 ID：{result['backfill_id']}\n"
            f"状态：{result['status']}",
            cards=[{"card_type": "dag_backfill", "backfill": result}],
            data={"dag_backfill": result},
        )
        return {
            "response": response,
            "dag_id": dag_id,
            "dag_backfill": result,
            **batch.state_update(),
        }

    def unknown(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `unknown` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_response。
        """
        answer = (
            "我可以帮助你：查找和理解数据资产、解释字段和指标、查询或申请权限、"
            "解释角色、分析并优化 SQL、执行只读查询、解释查询结果以及辅助审批。"
        )
        response = self._response("unknown", answer)
        return {"response": response}

    def finalize(self, state: AgentState) -> dict[str, Any]:
        """作用：负责 `finalize` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_now。
        """
        response = state.get("response") or {
            "type": "unknown",
            "answer": "任务未产生结果。",
            "cards": [],
            "actions": [],
            "data": {},
        }
        return {
            "messages": [
                {"role": "assistant", "content": response.get("answer", "")}
            ],
            "updated_at": _now(),
        }

    def _load_sql_context(
        self, batch: ToolBatch, tables: list[str]
    ) -> dict[str, Any]:
        """作用：负责 `_load_sql_context` 对应的处理。
        上游：AgentNodes.analyze_sql, AgentNodes.optimize_sql。
        下游：call。
        """
        context: dict[str, Any] = {"ddl": {}, "indexes": {}, "statistics": {}}
        for table in tables:
            ddl = batch.call("get_table_ddl", table=table)
            indexes = batch.call("get_indexes", table=table)
            statistics = batch.call("get_statistics", table=table)
            context["ddl"][table] = ddl.get("ddl", ddl)
            context["indexes"][table] = indexes.get("indexes", [])
            context["statistics"][table] = statistics.get(
                "statistics", statistics
            )
        return context

    def _batch(self, state: AgentState) -> ToolBatch:
        """作用：负责 `_batch` 对应的处理。
        上游：AgentNodes.analyze_sql, AgentNodes.apply_permission, AgentNodes.approval_context, AgentNodes.approval_risk, AgentNodes.backfill_dag, AgentNodes.check_permission, AgentNodes.dag_status, AgentNodes.discover_assets, AgentNodes.execute_query, AgentNodes.explain_columns, AgentNodes.explain_metric, AgentNodes.explain_query_result, AgentNodes.explain_role, AgentNodes.explain_table, AgentNodes.generate_dag, AgentNodes.optimize_sql, AgentNodes.permission_history, AgentNodes.prepare_query, AgentNodes.submit_dag, AgentNodes.ticket_status, AgentNodes.trigger_dag, AgentNodes.validate_dag。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return ToolBatch(
            self.tools,
            user_id=state["user_id"],
            session_id=state["session_id"],
            task_id=state["task_id"],
            intent=state.get("intent"),
        )

    def _candidate_read(self, state: AgentState, batch: ToolBatch, *, stage: str, tool: str, fixed_arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        """尝试阶段受限候选调用；参数或模型失败时保留原固定读路径。"""
        if self.tool_candidate_model is None:
            return batch.call(tool, **fixed_arguments), {}
        from data_agent.tool_harness import CandidateError, ToolHarness

        harness = ToolHarness(self.tools)
        candidate_state: dict[str, Any] = {"tool_stage": stage}
        prompt = (
            "只输出单个 JSON 对象 {name, arguments}。"
            f"当前阶段：{stage}；允许 Schema：{harness.schemas({tool})}。"
            f"已确认参数：{fixed_arguments}；用户问题：{state.get('message', '')}"
        )
        try:
            response = self.tool_candidate_model.invoke(prompt)
            content = getattr(response, "content", response)
            executed = harness.execute(content, allowed={tool}, stage=stage, user_id=state["user_id"], session_id=state["session_id"], task_id=state["task_id"], intent=state.get("intent"), required_arguments=fixed_arguments)
            batch.events.append(executed.event)
            batch.names.append(executed.tool)
            candidate_state["candidate_call"] = {"name": executed.tool}
            candidate_state["candidate_validation"] = {"status": "passed"}
            return executed.value, candidate_state
        except CandidateError as exc:
            candidate_state["candidate_validation"] = {"status": "rejected", "code": exc.code}
            if exc.event:
                batch.events.append(exc.event)
        except Exception:
            candidate_state["candidate_validation"] = {"status": "fallback", "code": "model_unavailable"}
        return batch.call(tool, **fixed_arguments), candidate_state

    def _supporting_knowledge(self, state: AgentState, *, document_type: str, resource_ids: set[str], sql_dialect: str | None = None) -> dict[str, Any]:
        """仅附加映射到实时平台对象的本轮授权资料，不让文档改写平台事实。"""
        empty: dict[str, Any] = {"snippets": [], "citations": []}
        if self.knowledge is None or self.access_scope is None or not resource_ids:
            return empty
        try:
            scope = self.access_scope(state["user_id"])
            found = self.knowledge.index.search(state.get("message", ""), scope=scope, document_type=document_type, sql_dialect=sql_dialect)
        except Exception:
            return empty
        chunks = [chunk for chunk in found.results if set(chunk.resource_ids) & resource_ids][:3]
        return {
            "snippets": [f"[{index}] {chunk.content[:300]}" for index, chunk in enumerate(chunks, 1)],
            "citations": [
                {"citation_id": str(index), "document_id": chunk.document_id, "chunk_id": chunk.chunk_id, "title": chunk.title, "section": chunk.section, "source_uri": chunk.source_uri, "version": chunk.version}
                for index, chunk in enumerate(chunks, 1)
            ],
        }

    def _resource_name(self, state: AgentState) -> str | None:
        """作用：负责 `_resource_name` 对应的处理。
        上游：AgentNodes.explain_columns, AgentNodes.explain_table。
        下游：_resource。
        """
        resource = self._resource(state)
        if not resource:
            return None
        return resource.get("qualified_name") or (
            f"{resource.get('database', 'dw')}.{resource['name']}"
            if resource.get("name")
            else None
        )

    @staticmethod
    def _resource(state: AgentState) -> dict[str, Any] | None:
        """作用：负责 `_resource` 对应的处理。
        上游：AgentNodes._resource_name, AgentNodes.apply_permission, AgentNodes.check_permission, AgentNodes.permission_history。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        resource = state.get("entities", {}).get("resource")
        if resource:
            return resource
        preview_resource = (state.get("permission_preview") or {}).get("resource")
        if isinstance(preview_resource, dict):
            return preview_resource
        resources = state.get("identified_resources") or []
        return resources[0] if resources else None

    @staticmethod
    def _sql(state: AgentState) -> str | None:

        """作用：负责 `_sql` 对应的处理。
        上游：AgentNodes.analyze_sql, AgentNodes.execute_query, AgentNodes.optimize_sql, AgentNodes.prepare_query。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return state.get("entities", {}).get("sql") or state.get("generated_sql")

    @staticmethod
    def _dag_id(state: AgentState) -> str | None:
        """作用：负责 `_dag_id` 对应的处理。
        上游：AgentNodes.backfill_dag, AgentNodes.dag_status, AgentNodes.trigger_dag。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return (
            state.get("entities", {}).get("dag_id")
            or state.get("dag_id")
        )

    @staticmethod
    def _dag_definition(state: AgentState) -> str | None:
        """作用：负责 `_dag_definition` 对应的处理。
        上游：AgentNodes.submit_dag, AgentNodes.validate_dag。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        definition = state.get("dag_definition")
        if definition:
            return definition
        message = state.get("message", "").strip()
        return message or None

    @staticmethod
    def _dag_schedule(message: str) -> str:
        """作用：负责 `_dag_schedule` 对应的处理。
        上游：AgentNodes.generate_dag。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        if "凌晨 2" in message or "凌晨2" in message:
            return "0 2 * * *"
        if "每天" in message or "每日" in message:
            return "0 0 * * *"
        if "每周" in message:
            return "0 0 * * 1"
        if "每月" in message:
            return "0 0 1 * *"
        return "0 0 * * *"

    @staticmethod
    def _infer_table_for_columns(columns: list[str]) -> str | None:
        """作用：负责 `_infer_table_for_columns` 对应的处理。
        上游：AgentNodes.explain_columns。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        order_columns = {
            "order_id",
            "user_id",
            "pay_amount",
            "settle_amount",
            "gmv",
            "order_status",
            "dt",
        }
        if any(column in order_columns for column in columns):
            return "dwd_order"
        if any(column in {"region", "order_count"} for column in columns):
            return "dws_sales_daily"
        if any(column in {"member_level"} for column in columns):
            return "dim_user"
        return None

    @staticmethod
    def _response(
        response_type: str,
        answer: str,
        *,
        cards: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `_response` 对应的处理。
        上游：AgentNodes._ask_for, AgentNodes.analyze_sql, AgentNodes.apply_permission, AgentNodes.approval_context, AgentNodes.approval_risk, AgentNodes.backfill_dag, AgentNodes.check_permission, AgentNodes.dag_status, AgentNodes.discover_assets, AgentNodes.execute_query, AgentNodes.explain_columns, AgentNodes.explain_metric, AgentNodes.explain_query_result, AgentNodes.explain_role, AgentNodes.explain_table, AgentNodes.generate_dag, AgentNodes.optimize_sql, AgentNodes.permission_history, AgentNodes.prepare_query, AgentNodes.submit_dag, AgentNodes.ticket_status, AgentNodes.trigger_dag, AgentNodes.unknown, AgentNodes.validate_dag。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return {
            "type": response_type,
            "answer": answer,
            "cards": cards or [],
            "actions": actions or [],
            "data": data or {},
        }

    def _ask_for(
        self, state: AgentState, response_type: str, answer: str
    ) -> dict[str, Any]:

        """作用：负责 `_ask_for` 对应的处理。
        上游：AgentNodes.analyze_sql, AgentNodes.apply_permission, AgentNodes.approval_context, AgentNodes.approval_risk, AgentNodes.backfill_dag, AgentNodes.check_permission, AgentNodes.dag_status, AgentNodes.execute_query, AgentNodes.explain_columns, AgentNodes.explain_metric, AgentNodes.explain_query_result, AgentNodes.explain_role, AgentNodes.explain_table, AgentNodes.optimize_sql, AgentNodes.prepare_query, AgentNodes.submit_dag, AgentNodes.ticket_status, AgentNodes.trigger_dag, AgentNodes.validate_dag。
        下游：_response。
        """
        return {"response": self._response(response_type, answer)}

    @staticmethod
    def _confirmed(decision: Any) -> bool:
        """作用：负责 `_confirmed` 对应的处理。
        上游：AgentNodes._confirmed, AgentNodes.apply_permission。
        下游：_confirmed。
        """
        if decision is True:
            return True
        if isinstance(decision, str):
            return decision.strip().lower() in {"yes", "y", "true", "同意", "确认"}
        if isinstance(decision, dict):
            value = decision.get("approved", decision.get("confirmed"))
            return AgentNodes._confirmed(value)
        return False

    @staticmethod
    def _duration_decision(decision: Any, *, recommended: int) -> int:
        """作用：负责 `_duration_decision` 对应的处理。
        上游：AgentNodes.apply_permission。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        allowed = {7, 15, 30}
        if isinstance(decision, dict):
            decision = decision.get("duration_days")
        try:
            duration = int(decision)
        except (TypeError, ValueError):
            duration = 0
        fallback = int(recommended)
        if fallback not in allowed:
            fallback = 7
        return duration if duration in allowed else fallback

    @staticmethod
    def _role_decision(decision: Any, roles: list[dict[str, Any]]) -> str:
        """作用：负责 `_role_decision` 对应的处理。
        上游：AgentNodes.apply_permission。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        if isinstance(decision, dict):
            decision = decision.get("role_id")
        value = str(decision or "").strip()
        role_ids = {str(role["role_id"]) for role in roles}
        if value in role_ids:
            return value
        if value.isdigit():
            index = int(value) - 1
            if 0 <= index < len(roles):
                return str(roles[index]["role_id"])
        return str(roles[0]["role_id"]) if roles else ""
