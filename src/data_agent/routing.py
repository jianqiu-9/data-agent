from __future__ import annotations

import json
import re
from typing import Any, Protocol

from langchain_core.language_models.chat_models import BaseChatModel

from data_agent.models import Intent, IntentResult
from data_agent.prompts import render_intent_prompt


TABLE_PATTERN = re.compile(
    r"(?<![\w])(?:dw\.)?((?:dwd|dws|ads|dim|ods)_[a-zA-Z0-9_]+)\b",
    re.IGNORECASE,
)
SQL_BLOCK_PATTERN = re.compile(
    r"```(?:sql)?\s*(.*?)```",
    re.IGNORECASE | re.DOTALL,
)
SQL_START_PATTERN = re.compile(r"\b(select|with)\b", re.IGNORECASE)
ROLE_PATTERN = re.compile(r"\b(r_[a-zA-Z0-9_]+)\b")
TICKET_PATTERN = re.compile(r"\b(T\d{8,})\b", re.IGNORECASE)
DURATION_PATTERN = re.compile(r"(\d+)\s*(?:天|日|days?)", re.IGNORECASE)


class IntentRouter(Protocol):
    def route(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        previous_state: dict[str, Any] | None = None,
    ) -> IntentResult: ...


class RuleBasedIntentRouter:
    """Deterministic router suitable for tests and operation without an LLM."""

    def route(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        previous_state: dict[str, Any] | None = None,
    ) -> IntentResult:
        context = context or {}
        previous_state = previous_state or {}
        text = message.strip()
        lower = text.lower()
        sql = self._extract_sql(text, previous_state)
        tables = self._extract_tables(text)
        columns = self._extract_columns(text)
        metric = self._extract_metric(text)
        role_id = self._extract_role(text)
        ticket_id = self._extract_ticket(text)
        action = self._extract_action(lower)
        env = self._extract_env(lower, context)
        duration_days = self._extract_duration(text, previous_state)

        entities: dict[str, Any] = {
            "resources": [
                {"type": "table", "database": "dw", "name": table} for table in tables
            ],
            "resource": (
                {"type": "table", "database": "dw", "name": tables[0]}
                if tables
                else None
            ),
            "columns": columns,
            "metric": metric,
            "role_id": role_id,
            "ticket_id": ticket_id,
            "action": action,
            "env": env,
            "duration_days": duration_days,
            "sql": sql,
            "reason": self._extract_reason(text),
        }

        if (
            previous_state.get("permission_preview")
            and self._is_confirmation(text)
        ):
            return IntentResult(
                intent=Intent.PERMISSION_APPLY,
                confidence=0.99,
                entities=entities,
                reasoning="上一轮已生成权限申请预览，当前消息是确认提交。",
            )

        intent, confidence, reasoning = self._classify(
            text=text,
            lower=lower,
            sql=sql,
            tables=tables,
            columns=columns,
            metric=metric,
            role_id=role_id,
            ticket_id=ticket_id,
            previous_state=previous_state,
        )
        return IntentResult(
            intent=intent,
            confidence=confidence,
            entities=entities,
            reasoning=reasoning,
        )

    @staticmethod
    def _extract_tables(text: str) -> list[str]:
        result: list[str] = []
        for match in TABLE_PATTERN.findall(text):
            name = match.lower()
            if name not in result:
                result.append(name)
        return result

    @staticmethod
    def _extract_sql(text: str, previous_state: dict[str, Any]) -> str | None:
        block = SQL_BLOCK_PATTERN.search(text)
        if block:
            return block.group(1).strip()
        start = SQL_START_PATTERN.search(text)
        if start:
            candidate = text[start.start() :].strip()
            if candidate.lower() in {"select", "with"} and previous_state.get("generated_sql"):
                return previous_state["generated_sql"]
            return candidate
        if re.fullmatch(r"\s*(?:优化|重写|执行|分析)一下\s*", text):
            return previous_state.get("generated_sql")
        return None

    @staticmethod
    def _extract_columns(text: str) -> list[str]:
        quoted = re.findall(r"`([a-zA-Z_][a-zA-Z0-9_]*)`", text)
        if quoted:
            return list(dict.fromkeys(quoted))
        pair = re.search(
            r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:和|与|跟|vs\.?|对比)\s*"
            r"([a-zA-Z_][a-zA-Z0-9_]*)\b",
            text,
            re.IGNORECASE,
        )
        if pair:
            return [pair.group(1), pair.group(2)]
        known = re.findall(
            r"\b(pay_amount|settle_amount|order_status|order_id|user_id|gmv|dt|region|"
            r"order_count|member_level)\b",
            text,
            re.IGNORECASE,
        )
        return list(dict.fromkeys(known))

    @staticmethod
    def _extract_metric(text: str) -> str | None:
        lower = text.lower()
        if re.search(r"\bgmv\b", lower):
            return "gmv"
        if "订单量" in text or "订单数" in text:
            return "order_count"
        if "销售收入" in text or "销售额" in text:
            return "sales_amount"
        return None

    @staticmethod
    def _extract_role(text: str) -> str | None:
        role = ROLE_PATTERN.search(text)
        if role:
            return role.group(1)
        if "销售域数据分析师" in text:
            return "r_sales_analyst"
        if "用户域数据管理员" in text:
            return "r_user_admin"
        return None

    @staticmethod
    def _extract_ticket(text: str) -> str | None:
        ticket = TICKET_PATTERN.search(text)
        return ticket.group(1) if ticket else None

    @staticmethod
    def _extract_action(lower: str) -> str:
        if "export" in lower or "导出" in lower:
            return "export"
        if "download" in lower or "下载" in lower:
            return "download"
        if "update" in lower or "更新" in lower or "修改" in lower:
            return "update"
        if "delete" in lower or "删除" in lower:
            return "delete"
        return "select"

    @staticmethod
    def _extract_env(lower: str, context: dict[str, Any]) -> str:
        if any(token in lower for token in ["生产", "线上", "prod"]):
            return "prod"
        if any(token in lower for token in ["预发", "staging", "stage"]):
            return "staging"
        if any(token in lower for token in ["开发", "dev", "测试"]):
            return "dev"
        return str(context.get("env", "prod"))

    @staticmethod
    def _extract_duration(text: str, previous_state: dict[str, Any]) -> int | None:
        match = DURATION_PATTERN.search(text)
        if match:
            return int(match.group(1))
        preview = previous_state.get("permission_preview") or {}
        return preview.get("duration_days")

    @staticmethod
    def _extract_reason(text: str) -> str:
        match = re.search(r"(?:用于|用途是|申请理由[:：])\s*(.+)$", text)
        if match:
            return match.group(1).strip("。 ")
        return text.strip()

    @staticmethod
    def _is_confirmation(text: str) -> bool:
        return bool(
            re.fullmatch(
                r"\s*(?:(?:确认|同意)(?:提交)?|提交|申请|好的|可以|是|yes|y|ok)[。！!]?\s*",
                text,
                re.IGNORECASE,
            )
        )

    def _classify(
        self,
        *,
        text: str,
        lower: str,
        sql: str | None,
        tables: list[str],
        columns: list[str],
        metric: str | None,
        role_id: str | None,
        ticket_id: str | None,
        previous_state: dict[str, Any],
    ) -> tuple[Intent, float, str]:
        has_sql = bool(sql and SQL_START_PATTERN.search(sql))
        has_slow_word = any(word in lower for word in ["慢", "性能", "explain", "扫描", "瓶颈"])
        has_optimize_word = any(word in lower for word in ["优化", "重写", "改写"])
        has_execute_word = any(word in lower for word in ["执行", "跑一下", "运行", "查询一下"])

        if has_sql and has_optimize_word:
            return Intent.SQL_REWRITE if "重写" in text or "改写" in text else Intent.SQL_OPTIMIZE, 0.97, "检测到 SQL 和优化要求。"
        if has_sql and has_slow_word:
            return Intent.SQL_OPTIMIZE, 0.96, "检测到 SQL 和性能问题描述。"
        if has_sql and has_execute_word:
            return Intent.QUERY_EXECUTE, 0.96, "检测到 SQL 和执行要求。"
        if has_sql and not any(word in text for word in ["权限", "审批", "角色"]):
            return Intent.SQL_ANALYZE, 0.86, "检测到用户直接提供了 SQL。"
        if has_slow_word and previous_state.get("generated_sql"):
            return Intent.SQL_OPTIMIZE, 0.88, "基于上一轮 SQL 继续性能分析。"
        if has_optimize_word and previous_state.get("generated_sql"):
            return Intent.SQL_REWRITE if "重写" in text or "改写" in text else Intent.SQL_OPTIMIZE, 0.9, "基于上一轮 SQL 继续优化。"

        if any(word in text for word in ["工单状态", "审批好了吗", "审批进度", "工单进度"]):
            return Intent.TICKET_STATUS, 0.95, "检测到工单状态查询。"
        if ticket_id and ("风险" in text or "审批建议" in text):
            return Intent.APPROVAL_RISK, 0.97, "检测到工单和风险分析要求。"
        if ticket_id or any(word in text for word in ["审批上下文", "审批辅助", "审批一下"]):
            return Intent.APPROVAL_CONTEXT, 0.94, "检测到审批上下文请求。"

        if any(word in text for word in ["申请权限", "帮我申请", "开通权限", "开权限", "申请一下", "授权"]):
            return Intent.PERMISSION_APPLY, 0.96, "检测到权限申请意图。"
        if "权限" in text and any(word in text for word in ["历史", "之前", "以前", "曾经"]):
            return Intent.PERMISSION_HISTORY, 0.94, "检测到历史权限查询。"
        if any(word in text for word in ["为什么查不了", "没有权限", "权限吗", "有没有权限", "查权限", "能查"]):
            return Intent.PERMISSION_CHECK, 0.95, "检测到权限检查意图。"
        if "权限" in text and tables:
            return Intent.PERMISSION_CHECK, 0.9, "检测到资源权限询问。"

        if role_id or any(word in lower for word in ["role", "角色"]):
            return Intent.ROLE_EXPLAIN, 0.94, "检测到角色解释请求。"
        if any(word in text for word in ["结果说明", "这个结果", "为什么下降", "结果说明什么", "解释结果"]):
            return Intent.QUERY_EXPLAIN, 0.92, "检测到查询结果解释请求。"
        if any(word in text for word in ["指标", "口径", "定义"]) and metric:
            return Intent.METRIC_EXPLAIN, 0.94, "检测到指标解释请求。"
        if metric and any(word in text for word in ["是什么", "什么意思", "解释"]):
            return Intent.METRIC_EXPLAIN, 0.9, "检测到指标名称和解释请求。"
        if len(columns) >= 2 and any(
            word in text for word in ["区别", "差异", "对比", "不同", "关系"]
        ):
            return Intent.COLUMN_EXPLAIN, 0.97, "检测到两个字段的对比解释。"
        if columns and any(word in text for word in ["字段", "什么意思", "定义"]):
            return Intent.COLUMN_EXPLAIN, 0.9, "检测到字段解释请求。"
        if tables and any(
            word in text for word in ["干嘛", "是什么", "介绍", "含义", "解释", "做什么"]
        ):
            return Intent.TABLE_EXPLAIN, 0.96, "检测到表解释请求。"
        if any(
            word in text
            for word in ["找表", "哪张表", "哪个表", "用哪张", "用什么表", "推荐表", "有什么表", "适合"]
        ):
            return Intent.DATA_DISCOVERY, 0.94, "检测到数据资产发现请求。"
        if any(word in text for word in ["我要查", "想看", "查一下", "每天", "销售额"]):
            return Intent.DATA_DISCOVERY, 0.78, "从业务目标中识别数据资产发现任务。"
        return Intent.UNKNOWN, 0.35, "没有命中已支持的意图规则。"


class LlmIntentRouter:
    """Prompt-driven router with deterministic fallback for reliability."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        fallback: IntentRouter | None = None,
        minimum_confidence: float = 0.55,
    ) -> None:
        self.model = model
        self.fallback = fallback or RuleBasedIntentRouter()
        self.minimum_confidence = minimum_confidence

    def route(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        previous_state: dict[str, Any] | None = None,
    ) -> IntentResult:
        context = context or {}
        previous_state = previous_state or {}
        prompt = render_intent_prompt(
            message=message,
            user_id=str(previous_state.get("user_id", "")),
            session_id=str(previous_state.get("session_id", "")),
            context=json.dumps(context, ensure_ascii=False, default=str),
            task_state=json.dumps(
                _routing_state(previous_state),
                ensure_ascii=False,
                default=str,
            ),
        )
        try:
            response = self.model.invoke(prompt)
            content = _message_content(response)
            payload = _extract_json_object(content)
            result = IntentResult.model_validate(payload)
            if result.confidence < self.minimum_confidence:
                raise ValueError("LLM intent confidence is below threshold")
            return result
        except Exception:
            return self.fallback.route(message, context, previous_state)


def _routing_state(state: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "intent",
        "entities",
        "business_goal",
        "identified_resources",
        "permission_preview",
        "pending_task",
        "generated_sql",
        "query_status",
    )
    return {key: state[key] for key in keys if key in state}


def _message_content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("No JSON object found in model output")
        text = text[start : end + 1]
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Model output must be a JSON object")
    return payload
