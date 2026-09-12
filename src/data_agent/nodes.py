from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from langgraph.types import interrupt

from data_agent import formatting
from data_agent.models import Intent
from data_agent.routing import IntentRouter, RuleBasedIntentRouter
from data_agent.state import AgentState
from data_agent.tooling import ToolBatch, ToolRegistry


def _now() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


class AgentNodes:
    def __init__(
        self,
        tools: ToolRegistry,
        router: IntentRouter | None = None,
    ) -> None:
        self.tools = tools
        self.router = router or RuleBasedIntentRouter()

    def prepare(self, state: AgentState) -> dict[str, Any]:
        previous_task_id = state.get("task_id")
        message = state.get("message", "").strip()
        return {
            "task_id": previous_task_id or uuid4().hex,
            "message": message,
            "business_goal": message,
            "response": {},
            "created_at": state.get("created_at") or _now(),
            "updated_at": _now(),
        }

    def route(self, state: AgentState) -> dict[str, Any]:
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
        batch = self._batch(state)
        goal = state.get("message", "")
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
            data={"recommendation": recommendation},
        )
        return {
            "response": response,
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

    def explain_table(self, state: AgentState) -> dict[str, Any]:
        table = self._resource_name(state)
        if not table:
            return self._ask_for(
                state,
                "table_explain",
                "请提供需要解释的表名，例如 dwd_order。",
            )
        batch = self._batch(state)
        metadata = batch.call("get_table_metadata", table=table)
        lineage = batch.call("get_data_lineage", table=table)
        answer = formatting.format_table_metadata(metadata)
        upstream = "、".join(lineage.get("lineage", {}).get("upstream", [])) or "无"
        downstream = "、".join(lineage.get("lineage", {}).get("downstream", [])) or "无"
        answer += f"\n\n血缘：\n- 上游：{upstream}\n- 下游：{downstream}"
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
            data={"metadata": metadata, "lineage": lineage},
        )
        return {"response": response, **batch.state_update()}

    def explain_columns(self, state: AgentState) -> dict[str, Any]:
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
        for column in columns:
            result = batch.call(
                "get_column_metadata",
                table=table,
                column=column,
            )
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
        return {"response": response, **batch.state_update()}

    def explain_metric(self, state: AgentState) -> dict[str, Any]:
        metric_name = state.get("entities", {}).get("metric")
        if not metric_name:
            return self._ask_for(
                state,
                "metric_explain",
                "请提供需要解释的指标名称，例如 GMV 或订单量。",
            )
        batch = self._batch(state)
        result = batch.call("get_metric_definition", metric=metric_name)
        if result.get("found"):
            metric = result["metric"]
            answer = formatting.format_metric(metric)
            cards = [{"card_type": "metric_definition", "metric": metric}]
        else:
            search = batch.call("search_metrics", query=metric_name, limit=5)
            metric = None
            answer = "未找到该指标的标准定义，请确认名称。"
            cards = [{"card_type": "metric_search", "metrics": search.get("metrics", [])}]
        response = self._response(
            "metric_explain",
            answer,
            cards=cards,
            data={"metric": metric},
        )
        return {"response": response, **batch.state_update()}

    def check_permission(self, state: AgentState) -> dict[str, Any]:
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
            answer += "\n\n" + formatting.format_permission_preview(preview)
        response = self._response(
            "permission_check",
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
            "required_permissions": [
                {"resource": resource, "action": action, "env": env}
            ],
            **batch.state_update(),
        }

    def apply_permission(self, state: AgentState) -> dict[str, Any]:
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
                "type": "permission_confirmation",
                "preview": preview,
                "message": "确认提交权限申请吗？",
            }
        )
        confirmed = confirmation is True or (
            isinstance(confirmation, dict) and confirmation.get("approved") is True
        )
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

        application = {
            "resource": preview["resource"],
            "action": preview.get("action", action),
            "env": preview.get("env", env),
            "duration_days": preview.get("duration_days", 30),
            "reason": preview.get("reason", state.get("business_goal", "")),
            "role_id": preview.get("role_id"),
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
            **batch.state_update(),
        }

    def permission_history(self, state: AgentState) -> dict[str, Any]:
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
        response = self._response(
            "sql_analyze",
            answer,
            cards=[{"card_type": "sql_analysis", **analysis}],
            actions=[
                {"label": "优化 SQL", "action": "sql_optimize"},
                {"label": "重写 SQL", "action": "sql_rewrite"},
            ],
            data=analysis,
        )
        return {
            "response": response,
            "generated_sql": sql,
            "sql_context": context,
            "sql_analysis": analysis,
            **batch.state_update(),
        }

    def optimize_sql(self, state: AgentState, *, rewrite_only: bool = False) -> dict[str, Any]:
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
        return self.optimize_sql(state, rewrite_only=True)

    def prepare_query(self, state: AgentState) -> dict[str, Any]:
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
            **batch.state_update(),
        }

    def execute_query(self, state: AgentState) -> dict[str, Any]:
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

    def approval_context(self, state: AgentState) -> dict[str, Any]:
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

    def unknown(self, state: AgentState) -> dict[str, Any]:
        answer = (
            "我可以帮助你：查找和理解数据资产、解释字段和指标、查询或申请权限、"
            "解释角色、分析并优化 SQL、执行只读查询、解释查询结果以及辅助审批。"
        )
        response = self._response("unknown", answer)
        return {"response": response}

    def finalize(self, state: AgentState) -> dict[str, Any]:
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
        return ToolBatch(
            self.tools,
            user_id=state["user_id"],
            session_id=state["session_id"],
            task_id=state["task_id"],
            intent=state.get("intent"),
        )

    def _resource_name(self, state: AgentState) -> str | None:
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
        return state.get("entities", {}).get("sql") or state.get("generated_sql")

    @staticmethod
    def _infer_table_for_columns(columns: list[str]) -> str | None:
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
        return {"response": self._response(response_type, answer)}
