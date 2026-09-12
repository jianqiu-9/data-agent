from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai"))


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _asset(
    *,
    name: str,
    description: str,
    grain: str,
    owner: str,
    keywords: list[str],
    score: int,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "asset_id": f"asset.{name}",
        "asset_name": name,
        "qualified_name": f"dw.{name}",
        "asset_type": "table",
        "business_domain": "销售",
        "description": description,
        "grain": grain,
        "owner": owner,
        "update_frequency": "每日 08:00",
        "data_range": "2025-01-01 至今",
        "source_table": f"dw.{name}",
        "quality_level": "A",
        "sensitivity_level": "medium" if name == "dwd_order" else "low",
        "recommendation_score": score,
        "keywords": keywords,
        "fields": fields,
    }


ASSETS: dict[str, dict[str, Any]] = {
    "dw.dwd_order": _asset(
        name="dwd_order",
        description="销售订单明细表，记录订单级事实。",
        grain="一条订单一条记录",
        owner="销售数据 Owner",
        keywords=["订单", "销售", "明细", "订单明细", "订单状态", "dwd_order"],
        score=95,
        fields=[
            {
                "name": "order_id",
                "type": "string",
                "description": "订单唯一标识",
                "sensitive": False,
            },
            {
                "name": "user_id",
                "type": "string",
                "description": "用户唯一标识",
                "sensitive": True,
            },
            {
                "name": "pay_amount",
                "type": "decimal(18,2)",
                "description": "用户支付金额，包含退款前的支付流水金额",
                "sensitive": False,
            },
            {
                "name": "settle_amount",
                "type": "decimal(18,2)",
                "description": "订单结算金额，已扣除退款、优惠和平台佣金",
                "sensitive": False,
            },
            {
                "name": "gmv",
                "type": "decimal(18,2)",
                "description": "支付成功订单商品金额，口径以 GMV 指标定义为准",
                "sensitive": False,
            },
            {
                "name": "order_status",
                "type": "string",
                "description": "订单当前状态",
                "sensitive": False,
            },
            {
                "name": "dt",
                "type": "date",
                "description": "业务日期，分区字段",
                "sensitive": False,
            },
        ],
    ),
    "dw.dws_sales_daily": _asset(
        name="dws_sales_daily",
        description="销售日汇总表，预聚合每日订单和销售指标。",
        grain="业务日期 + 区域",
        owner="销售数据 Owner",
        keywords=["每天", "每日", "日报", "销售额", "销售汇总", "日汇总", "sales", "daily"],
        score=98,
        fields=[
            {
                "name": "dt",
                "type": "date",
                "description": "统计日期",
                "sensitive": False,
            },
            {
                "name": "region",
                "type": "string",
                "description": "销售区域",
                "sensitive": False,
            },
            {
                "name": "order_count",
                "type": "bigint",
                "description": "支付成功订单数",
                "sensitive": False,
            },
            {
                "name": "gmv",
                "type": "decimal(18,2)",
                "description": "支付成功订单商品金额",
                "sensitive": False,
            },
        ],
    ),
    "dw.dim_user": _asset(
        name="dim_user",
        description="用户维度表，提供用户属性、注册信息和会员等级。",
        grain="一个用户一条记录",
        owner="用户数据 Owner",
        keywords=["用户", "客户", "会员", "用户维度", "dim_user"],
        score=85,
        fields=[
            {
                "name": "user_id",
                "type": "string",
                "description": "用户唯一标识",
                "sensitive": True,
            },
            {
                "name": "user_name",
                "type": "string",
                "description": "用户姓名",
                "sensitive": True,
            },
            {
                "name": "member_level",
                "type": "string",
                "description": "会员等级",
                "sensitive": False,
            },
        ],
    ),
    "dw.ads_sales_report": _asset(
        name="ads_sales_report",
        description="销售业务日报，面向管理层展示固定报表口径。",
        grain="业务日报",
        owner="销售数据 Owner",
        keywords=["销售报表", "业务日报", "管理层", "ads_sales_report"],
        score=80,
        fields=[
            {
                "name": "report_date",
                "type": "date",
                "description": "报表日期",
                "sensitive": False,
            },
            {
                "name": "sales_amount",
                "type": "decimal(18,2)",
                "description": "报表销售收入",
                "sensitive": False,
            },
        ],
    ),
}

METRICS: dict[str, dict[str, Any]] = {
    "gmv": {
        "metric_id": "metric.gmv",
        "metric_name": "GMV",
        "definition": "支付成功订单商品金额",
        "formula": "SUM(pay_amount)",
        "time_dimension": "pay_time",
        "filter_condition": "order_status = 'PAID'",
        "source_asset": "dw.dws_sales_daily",
        "owner": "销售数据 Owner",
        "version": "v2",
    },
    "order_count": {
        "metric_id": "metric.order_count",
        "metric_name": "订单量",
        "definition": "支付成功的去重订单数量",
        "formula": "COUNT(DISTINCT order_id)",
        "time_dimension": "pay_time",
        "filter_condition": "order_status = 'PAID'",
        "source_asset": "dw.dws_sales_daily",
        "owner": "销售数据 Owner",
        "version": "v1",
    },
    "sales_amount": {
        "metric_id": "metric.sales_amount",
        "metric_name": "销售收入",
        "definition": "扣除退款、优惠和平台佣金后的收入",
        "formula": "SUM(settle_amount)",
        "time_dimension": "settle_time",
        "filter_condition": "is_settled = 1",
        "source_asset": "dw.ads_sales_report",
        "owner": "财务数据 Owner",
        "version": "v3",
    },
}

ROLES: dict[str, dict[str, Any]] = {
    "r_sales_analyst": {
        "role_id": "r_sales_analyst",
        "role_name": "销售域数据分析师",
        "meaning": "可查询销售域非敏感明细与汇总表，不可导出敏感字段。",
        "description": "面向销售运营和数据分析岗位的生产只读角色。",
        "business_domain": "销售",
        "responsibilities": ["销售分析", "订单分析", "经营日报"],
        "permission_boundary": "销售域 dwd/dws/ads 层只读；默认 30 天；禁止 export。",
        "risk_level": "medium",
        "owner": "销售数据 Owner",
        "docs": "https://docs.example.com/roles/r_sales_analyst",
    },
    "r_user_admin": {
        "role_id": "r_user_admin",
        "role_name": "用户域数据管理员",
        "meaning": "可查询用户维度及用户域汇总数据。",
        "description": "负责用户域数据治理与查询。",
        "business_domain": "用户",
        "responsibilities": ["用户分析", "数据治理"],
        "permission_boundary": "用户域只读，敏感字段默认脱敏。",
        "risk_level": "high",
        "owner": "用户数据 Owner",
        "docs": "https://docs.example.com/roles/r_user_admin",
    },
}

USER_ROLES = {"u123": ["r_sales_analyst"], "u456": ["r_user_admin"]}

GRANTS: list[dict[str, Any]] = [
    {
        "grant_id": "g20260101001",
        "user_id": "u123",
        "role_id": "r_sales_analyst",
        "resource": "dw.dws_sales_daily",
        "action": "select",
        "env": "prod",
        "effect": "allow",
        "valid_from": "2026-01-01T00:00:00+08:00",
        "valid_to": "2026-12-31T23:59:59+08:00",
        "source": "role:r_sales_analyst",
    },
    {
        "grant_id": "g20260101002",
        "user_id": "u123",
        "role_id": "r_sales_analyst",
        "resource": "dw.dim_user",
        "action": "select",
        "env": "prod",
        "effect": "allow",
        "valid_from": "2026-01-01T00:00:00+08:00",
        "valid_to": "2027-01-31T23:59:59+08:00",
        "source": "role:r_sales_analyst",
    },
]

PERMISSION_HISTORY: dict[str, list[dict[str, Any]]] = {
    "u123": [
        {
            "ticket_id": "T20260101008",
            "role_id": "r_sales_analyst",
            "resource": "dw.dwd_order",
            "action": "select",
            "status": "expired",
            "granted_at": "2026-01-01T00:00:00+08:00",
            "expires_at": "2026-01-31T23:59:59+08:00",
            "is_expired": True,
        },
        {
            "ticket_id": "T20260301012",
            "role_id": "r_sales_analyst",
            "resource": "dw.dws_sales_daily",
            "action": "select",
            "status": "approved",
            "granted_at": "2026-01-01T00:00:00+08:00",
            "expires_at": "2026-12-31T23:59:59+08:00",
            "is_expired": False,
        },
    ]
}


class InMemoryPlatformAdapter:
    """Deterministic local implementation of the platform gateway contracts."""

    def __init__(self) -> None:
        self._tickets: dict[str, dict[str, Any]] = {}
        self._queries: dict[str, dict[str, Any]] = {}
        self._ticket_sequence = 1
        self._query_sequence = 1

    @staticmethod
    def _canonical_name(name: str) -> str:
        value = name.strip().strip("`")
        if "." in value:
            return value
        return f"dw.{value}"

    @staticmethod
    def _public_asset(asset: dict[str, Any]) -> dict[str, Any]:
        return {key: deepcopy(value) for key, value in asset.items() if key != "keywords"}

    def search_data_assets(self, query: str, limit: int = 5) -> dict[str, Any]:
        query_lower = query.lower()
        matches: list[tuple[int, dict[str, Any]]] = []
        for asset in ASSETS.values():
            keyword_score = 0
            for keyword in asset["keywords"]:
                if keyword.lower() in query_lower or query_lower in keyword.lower():
                    keyword_score += 40
            if asset["asset_name"].lower() in query_lower:
                keyword_score += 80
            if keyword_score:
                result = self._public_asset(asset)
                result["match_score"] = keyword_score + asset["recommendation_score"]
                matches.append((result["match_score"], result))

        if not matches:
            matches = [
                (asset["recommendation_score"], self._public_asset(asset))
                for asset in ASSETS.values()
            ]

        assets = [asset for _, asset in sorted(matches, key=lambda item: item[0], reverse=True)]
        return {"assets": assets[:limit], "total": min(len(assets), limit)}

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        canonical = self._canonical_name(table)
        asset = ASSETS.get(canonical)
        if asset is None:
            return {
                "found": False,
                "resource": canonical,
                "message": f"未在数据目录中找到 {canonical}",
            }
        result = self._public_asset(asset)
        result["found"] = True
        return result

    def get_column_metadata(
        self, table: str, column: str | None = None
    ) -> dict[str, Any]:
        metadata = self.get_table_metadata(table)
        if not metadata["found"]:
            return metadata
        fields = metadata["fields"]
        if column:
            field = next(
                (item for item in fields if item["name"].lower() == column.lower()),
                None,
            )
            return {
                "found": field is not None,
                "resource": metadata["qualified_name"],
                "column": field,
                "message": None if field else f"字段 {column} 不存在",
            }
        return {
            "found": True,
            "resource": metadata["qualified_name"],
            "columns": fields,
        }

    def get_data_lineage(self, table: str) -> dict[str, Any]:
        canonical = self._canonical_name(table)
        lineage = {
            "dw.dwd_order": {
                "upstream": ["ods.order"],
                "downstream": ["dw.dws_sales_daily", "dw.ads_sales_report"],
            },
            "dw.dws_sales_daily": {
                "upstream": ["dw.dwd_order"],
                "downstream": ["dw.ads_sales_report"],
            },
            "dw.dim_user": {"upstream": ["ods.user"], "downstream": ["dw.dwd_order"]},
        }
        return {
            "resource": canonical,
            "found": canonical in lineage,
            "lineage": lineage.get(canonical, {"upstream": [], "downstream": []}),
        }

    def search_metrics(self, query: str, limit: int = 5) -> dict[str, Any]:
        query_lower = query.lower()
        matches = []
        for metric in METRICS.values():
            haystack = " ".join(
                [
                    metric["metric_id"],
                    metric["metric_name"],
                    metric["definition"],
                    metric["formula"],
                ]
            ).lower()
            if query_lower in haystack or any(
                token and token in haystack
                for token in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", query_lower)
            ):
                matches.append(deepcopy(metric))
        return {"metrics": matches[:limit], "total": min(len(matches), limit)}

    def get_metric_definition(self, metric: str) -> dict[str, Any]:
        key = metric.strip().lower()
        definition = METRICS.get(key)
        if definition is None:
            definition = next(
                (
                    item
                    for item in METRICS.values()
                    if key in item["metric_name"].lower()
                    or key in item["definition"].lower()
                ),
                None,
            )
        return {
            "found": definition is not None,
            "metric": deepcopy(definition),
            "message": None if definition else f"未找到指标 {metric} 的定义",
        }

    def recommend_data_asset(
        self, goal: str, resources: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        if any(word in goal for word in ["日报", "每天", "每日", "日汇总"]):
            recommended = "dw.dws_sales_daily"
            reason = "已聚合到日粒度，并包含标准销售指标，查询成本低于订单明细表。"
        elif any(word in goal for word in ["订单状态", "订单明细", "明细"]):
            recommended = "dw.dwd_order"
            reason = "保留订单级明细和状态，适合订单明细分析。"
        elif any(word in goal for word in ["用户", "会员", "客户"]):
            recommended = "dw.dim_user"
            reason = "提供标准用户维度属性。"
        else:
            search = self.search_data_assets(goal, limit=1)
            top = search["assets"][0]
            recommended = top["qualified_name"]
            reason = f"与业务目标的元数据匹配度最高，当前推荐度为 {top['recommendation_score']}。"
        return {
            "recommended_asset": recommended,
            "reason": reason,
            "metadata": self.get_table_metadata(recommended),
        }

    def check_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
    ) -> dict[str, Any]:
        resource_name = self._canonical_name(
            resource.get("qualified_name")
            or resource.get("name")
            or resource.get("resource")
            or ""
        )
        action = action.lower()
        env = env.lower()
        now = _now()
        matched = None
        for grant in GRANTS:
            valid_to = datetime.fromisoformat(grant["valid_to"])
            if (
                grant["user_id"] == user_id
                and grant["resource"] == resource_name
                and grant["action"] == action
                and grant["env"] == env
                and grant["effect"] == "allow"
                and valid_to > now
            ):
                matched = grant
                break

        role_ids = USER_ROLES.get(user_id, [])
        role = deepcopy(ROLES[role_ids[0]]) if role_ids else None
        if matched:
            return {
                "has_permission": True,
                "resource": resource_name,
                "action": action,
                "env": env,
                "expires_at": matched["valid_to"],
                "grant_source": matched["source"],
                "role_id": matched["role_id"],
                "role_name": role["role_name"] if role else matched["role_id"],
                "role_meaning": role["meaning"] if role else "",
                "matched_policy": f"{env}_{role['business_domain'] if role else 'custom'}_readonly",
                "reason": f"用户通过角色 {matched['role_id']} 获得 {action} 权限。",
            }

        role_boundary = role["permission_boundary"] if role else "当前用户没有可解释的角色。"
        return {
            "has_permission": False,
            "resource": resource_name,
            "action": action,
            "env": env,
            "expires_at": None,
            "grant_source": None,
            "role_id": role["role_id"] if role else None,
            "role_name": role["role_name"] if role else None,
            "role_meaning": role["meaning"] if role else None,
            "matched_policy": None,
            "reason": (
                f"当前角色为“{role['role_name'] if role else '未知'}”，"
                f"权限边界为：{role_boundary}；该边界不包含 {resource_name} 的 "
                f"{env} 环境 {action} 权限。"
            ),
        }

    def batch_check_permission(
        self, user_id: str, checks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        results = [
            self.check_permission(
                user_id=user_id,
                resource=item["resource"],
                action=item.get("action", "select"),
                env=item.get("env", "prod"),
            )
            for item in checks
        ]
        return {
            "all_granted": all(item["has_permission"] for item in results),
            "results": results,
        }

    def get_user_roles(self, user_id: str) -> dict[str, Any]:
        role_ids = USER_ROLES.get(user_id, [])
        return {
            "user_id": user_id,
            "roles": [deepcopy(ROLES[role_id]) for role_id in role_ids if role_id in ROLES],
        }

    def get_role_detail(self, role_id: str) -> dict[str, Any]:
        role = ROLES.get(role_id)
        if role is None:
            role = next(
                (item for item in ROLES.values() if item["role_name"] == role_id),
                None,
            )
        return {
            "found": role is not None,
            "role": deepcopy(role),
            "message": None if role else f"未找到角色 {role_id}",
        }

    def get_permission_history(
        self,
        user_id: str,
        role_id: str | None = None,
        resource: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        history = deepcopy(PERMISSION_HISTORY.get(user_id, []))
        if role_id:
            history = [item for item in history if item["role_id"] == role_id]
        if resource:
            resource_name = self._canonical_name(
                resource.get("qualified_name")
                or resource.get("name")
                or resource.get("resource")
                or ""
            )
            history = [item for item in history if item["resource"] == resource_name]
        return {"user_id": user_id, "role_id": role_id, "history": history}

    def recommend_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
        task_goal: str,
    ) -> dict[str, Any]:
        if any(word in task_goal for word in ["长期", "持续", "长期项目"]):
            duration_days = 90
            task_type = "长期项目"
        elif any(word in task_goal for word in ["每天", "每日", "每周", "周期", "复盘"]):
            duration_days = 30
            task_type = "周期性分析"
        else:
            duration_days = 7 if action != "select" else 30
            task_type = "一次性分析" if action != "select" else "常规分析"

        role_result = self.get_user_roles(user_id)
        role = role_result["roles"][0] if role_result["roles"] else None
        resource_name = self._canonical_name(
            resource.get("qualified_name") or resource.get("name") or ""
        )
        metadata = self.get_table_metadata(resource_name)
        approver = metadata.get("owner") or (role["owner"] if role else "数据 Owner")
        return {
            "resource": resource_name,
            "action": action,
            "env": env,
            "duration_days": duration_days,
            "task_type": task_type,
            "reason": task_goal,
            "role_id": role["role_id"] if role else None,
            "role_name": role["role_name"] if role else None,
            "approver": approver,
            "risk": "medium" if action in {"export", "download"} else "low",
        }

    def create_permission_ticket(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]:
        ticket_id = f"T{_now():%Y%m%d}{self._ticket_sequence:04d}"
        self._ticket_sequence += 1
        application = deepcopy(application)
        resource = application.get("resource", {})
        resource_name = self._canonical_name(
            resource.get("qualified_name") or resource.get("name") or resource
        )
        application["resource"] = resource_name
        ticket = {
            "ticket_id": ticket_id,
            "applicant_id": applicant_id,
            "resource": resource_name,
            "resource_type": resource.get("type", "table"),
            "role_id": application.get("role_id"),
            "action": application.get("action", "select"),
            "env": application.get("env", "prod"),
            "duration_days": application.get("duration_days", 30),
            "reason": application.get("reason", ""),
            "approver_id": application.get("approver") or "data_owner",
            "status": "pending",
            "created_at": _iso(_now()),
            "approved_at": None,
            "grant_id": None,
        }
        self._tickets[ticket_id] = ticket
        return {
            "ticket_id": ticket_id,
            "status": ticket["status"],
            "approval_url": f"https://approval.example.com/ticket/{ticket_id}",
            "preview": application,
        }

    def approve_ticket(self, ticket_id: str) -> dict[str, Any]:
        """Test/demo helper representing a downstream approval workflow."""
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return {"ticket_id": ticket_id, "status": "not_found"}
        if ticket["status"] == "approved":
            return deepcopy(ticket)
        ticket["status"] = "approved"
        ticket["approved_at"] = _iso(_now())
        ticket["grant_id"] = f"g{ticket_id[1:]}"
        GRANTS.append(
            {
                "grant_id": ticket["grant_id"],
                "user_id": ticket["applicant_id"],
                "role_id": ticket.get("role_id"),
                "resource": ticket["resource"],
                "action": ticket["action"],
                "env": ticket["env"],
                "effect": "allow",
                "valid_from": ticket["approved_at"],
                "valid_to": _iso(
                    _now() + timedelta(days=int(ticket["duration_days"]))
                ),
                "source": f"ticket:{ticket_id}",
            }
        )
        return deepcopy(ticket)

    def get_ticket_status(self, ticket_id: str) -> dict[str, Any]:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            return {"ticket_id": ticket_id, "status": "not_found"}
        return deepcopy(ticket)

    def parse_sql(self, sql: str) -> dict[str, Any]:
        table_matches = re.findall(
            r"\b(?:from|join)\s+([`\w.]+)(?:\s+(?:as\s+)?([a-zA-Z_]\w*))?",
            sql,
            flags=re.IGNORECASE,
        )
        tables: list[str] = []
        aliases: dict[str, str] = {}
        reserved = {
            "where",
            "join",
            "left",
            "right",
            "inner",
            "outer",
            "group",
            "order",
            "limit",
            "on",
        }
        for table, alias in table_matches:
            canonical = self._canonical_name(table)
            if canonical not in tables:
                tables.append(canonical)
            if alias and alias.lower() not in reserved:
                aliases[alias] = canonical
            aliases[canonical.split(".")[-1]] = canonical

        select_match = re.search(r"\bselect\s+(.*?)\s+\bfrom\b", sql, re.I | re.S)
        selected = []
        if select_match:
            for expression in select_match.group(1).split(","):
                expression = expression.strip()
                if expression == "*":
                    selected.append("*")
                    continue
                alias_match = re.search(r"\bas\s+([a-zA-Z_]\w*)$", expression, re.I)
                if alias_match:
                    expression = expression[: alias_match.start()].strip()
                selected.append(expression)
        return {
            "sql": sql.strip(),
            "statement_type": "select" if re.search(r"\bselect\b", sql, re.I) else "other",
            "tables": tables,
            "aliases": aliases,
            "selected_columns": selected,
            "has_where": bool(re.search(r"\bwhere\b", sql, re.I)),
            "has_join": bool(re.search(r"\bjoin\b", sql, re.I)),
            "has_aggregate": bool(re.search(r"\b(count|sum|avg|min|max)\s*\(", sql, re.I)),
        }

    def get_table_ddl(self, table: str) -> dict[str, Any]:
        metadata = self.get_table_metadata(table)
        if not metadata["found"]:
            return metadata
        lines = [
            f"  {field['name']} {field['type']}"
            + (" NOT NULL" if field["name"] in {"order_id", "user_id", "dt"} else "")
            for field in metadata["fields"]
        ]
        return {
            "resource": metadata["qualified_name"],
            "ddl": f"CREATE TABLE {metadata['qualified_name']} (\n"
            + ",\n".join(lines)
            + "\n);",
        }

    def get_indexes(self, table: str) -> dict[str, Any]:
        canonical = self._canonical_name(table)
        indexes = {
            "dw.dwd_order": [
                {"name": "idx_dt", "columns": ["dt"], "type": "normal"},
                {"name": "PRIMARY", "columns": ["order_id"], "type": "primary"},
            ],
            "dw.dws_sales_daily": [
                {"name": "PRIMARY", "columns": ["dt", "region"], "type": "primary"},
            ],
            "dw.dim_user": [
                {"name": "PRIMARY", "columns": ["user_id"], "type": "primary"},
            ],
        }
        return {"resource": canonical, "indexes": deepcopy(indexes.get(canonical, []))}

    def get_statistics(self, table: str) -> dict[str, Any]:
        canonical = self._canonical_name(table)
        stats = {
            "dw.dwd_order": {"row_count": 100_000_000, "size_gb": 420, "last_analyzed": "2026-09-12"},
            "dw.dws_sales_daily": {"row_count": 12_000, "size_gb": 2, "last_analyzed": "2026-09-12"},
            "dw.dim_user": {"row_count": 5_000_000, "size_gb": 8, "last_analyzed": "2026-09-11"},
            "dw.ads_sales_report": {"row_count": 800, "size_gb": 1, "last_analyzed": "2026-09-12"},
        }
        return {
            "resource": canonical,
            "statistics": deepcopy(stats.get(canonical, {"row_count": 0, "size_gb": 0})),
        }

    def explain_sql(self, sql: str) -> dict[str, Any]:
        parsed = self.parse_sql(sql)
        steps = []
        estimated_scan = 0
        for table in parsed["tables"]:
            stats = self.get_statistics(table)["statistics"]
            row_count = stats["row_count"]
            has_partition_filter = bool(re.search(r"\bdt\b", sql, re.I))
            access_type = "range" if has_partition_filter else "ALL"
            rows = row_count if access_type == "ALL" else max(row_count // 365, 1)
            estimated_scan += rows
            steps.append(
                {
                    "table": table,
                    "access_type": access_type,
                    "estimated_rows": rows,
                    "key": "idx_dt" if access_type == "range" and table == "dw.dwd_order" else None,
                    "extra": "Using where" if parsed["has_where"] else "Full table scan",
                }
            )
        return {
            "sql": sql,
            "tables": parsed["tables"],
            "plan": steps,
            "estimated_scan_rows": estimated_scan,
            "has_full_scan": any(step["access_type"] == "ALL" for step in steps),
        }

    def validate_sql(self, sql: str) -> dict[str, Any]:
        normalized = sql.strip()
        errors: list[str] = []
        warnings: list[str] = []
        if not normalized:
            errors.append("SQL 不能为空")
        if ";" in normalized.rstrip(";"):
            errors.append("不允许一次提交多条 SQL")
        if re.search(
            r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|replace)\b",
            normalized,
            re.I,
        ):
            errors.append("仅允许 SELECT 只读查询")
        if normalized and not re.search(r"^\s*(select|with)\b", normalized, re.I):
            errors.append("SQL 必须以 SELECT 或 WITH 开头")
        if re.search(r"\bselect\s+\*", normalized, re.I):
            warnings.append("建议明确列出所需字段，避免 SELECT *")
        if not re.search(r"\bwhere\b", normalized, re.I):
            warnings.append("SQL 没有 WHERE 条件，可能触发大范围扫描")
        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "read_only": not errors,
        }

    def optimize_sql(
        self, sql: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        parsed = self.parse_sql(sql)
        context = context or {}
        ddl = context.get("ddl") or {}
        indexes = context.get("indexes") or {}
        explain = context.get("explain") or self.explain_sql(sql)
        issues: list[str] = []
        index_suggestions: list[dict[str, Any]] = []
        join_suggestions: list[dict[str, Any]] = []

        if any(column == "*" for column in parsed["selected_columns"]):
            issues.append("查询返回字段过多，存在不必要的数据读取。")
        if not parsed["has_where"]:
            issues.append("缺少过滤条件，可能发生全表扫描。")
        elif "dw.dwd_order" in parsed["tables"] and not re.search(r"\bdt\b", sql, re.I):
            issues.append("dwd_order 未使用 dt 分区条件，扫描范围过大。")
        if explain.get("has_full_scan"):
            issues.append("EXPLAIN 显示至少一张表使用 ALL 访问方式。")

        join_columns = re.findall(
            r"([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\s*=\s*([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)",
            sql,
        )
        aliases = parsed["aliases"]
        used_dwd_order_join = False
        for left_alias, left_col, right_alias, right_col in join_columns:
            left_table = aliases.get(left_alias)
            right_table = aliases.get(right_alias)
            if left_table == "dw.dwd_order" and left_col == "user_id":
                used_dwd_order_join = True
            if right_table == "dw.dwd_order" and right_col == "user_id":
                used_dwd_order_join = True
            for table, column in ((left_table, left_col), (right_table, right_col)):
                if not table or not column:
                    continue
                table_indexes = indexes.get(table) or self.get_indexes(table)["indexes"]
                if not any(column in item["columns"] for item in table_indexes):
                    join_suggestions.append(
                        {
                            "table": table,
                            "issue": f"JOIN 字段 {column} 没有可用索引。",
                            "suggestion": f"评估为 {table}.{column} 增加索引。",
                        }
                    )

        has_dt_filter = bool(re.search(r"\bdt\b\s*(?:=|between|>=|>|<=|<)", sql, re.I))
        if (
            "dw.dwd_order" in parsed["tables"]
            and has_dt_filter
            and used_dwd_order_join
        ):
            existing = indexes.get("dw.dwd_order")
            if existing is None:
                existing = self.get_indexes("dw.dwd_order")["indexes"]
            if not any(item["columns"][:2] == ["dt", "user_id"] for item in existing):
                index_suggestions.append(
                    {
                        "table": "dw.dwd_order",
                        "columns": ["dt", "user_id"],
                        "type": "composite",
                        "reason": "先用 dt 做时间过滤，再按 user_id 完成 JOIN，减少扫描和回表。",
                        "ddl": (
                            "ALTER TABLE dw.dwd_order "
                            "ADD INDEX idx_dt_user(dt, user_id);"
                        ),
                    }
                )

        rewritten_sql = self._rewrite_order_select(sql, parsed)
        risks = []
        if index_suggestions:
            risks.append("新增索引会增加写入成本，需由 DBA 在低峰期评估执行。")
        if "dw.dwd_order" in parsed["tables"]:
            risks.append("dwd_order 为大规模订单明细表，查询应优先绑定 dt 分区条件。")
        if not risks:
            risks.append("优化前应结合实际执行计划与最新统计信息复测。")

        return {
            "sql": sql,
            "summary": "；".join(dict.fromkeys(issues)) if issues else "未发现明显结构性问题。",
            "issues": list(dict.fromkeys(issues)),
            "index_suggestions": index_suggestions,
            "join_optimization": join_suggestions,
            "rewritten_sql": rewritten_sql,
            "explain": explain,
            "ddl": ddl,
            "indexes": indexes,
            "risk": risks,
        }

    def rewrite_sql(
        self, sql: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        optimized = self.optimize_sql(sql, context)
        return {
            "original_sql": sql,
            "rewritten_sql": optimized["rewritten_sql"],
            "changes": optimized["issues"],
            "risk": optimized["risk"],
        }

    def _rewrite_order_select(self, sql: str, parsed: dict[str, Any]) -> str:
        if parsed["selected_columns"] != ["*"] or parsed["tables"] != ["dw.dwd_order"]:
            return sql.strip()
        columns = ", ".join(field["name"] for field in ASSETS["dw.dwd_order"]["fields"])
        return re.sub(
            r"\bselect\s+\*\s+from\b",
            f"SELECT {columns}\nFROM",
            sql.strip(),
            count=1,
            flags=re.IGNORECASE,
        )

    def execute_query(
        self, user_id: str, sql: str, env: str
    ) -> dict[str, Any]:
        validation = self.validate_sql(sql)
        if not validation["valid"]:
            return {
                "query_id": None,
                "status": "rejected",
                "errors": validation["errors"],
            }

        query_id = f"Q{_now():%Y%m%d}{self._query_sequence:04d}"
        self._query_sequence += 1
        parsed = self.parse_sql(sql)
        rows: list[dict[str, Any]]
        if re.search(r"\bcount\s*\(", sql, re.I):
            rows = [{"order_count": 125_430}]
        elif "region" in sql.lower() and "group by" in sql.lower():
            rows = [
                {"region": "上海", "order_count": 42_300, "gmv": "32680000.00"},
                {"region": "杭州", "order_count": 31_240, "gmv": "24150000.00"},
                {"region": "南京", "order_count": 20_100, "gmv": "15690000.00"},
            ]
        elif "dw.dws_sales_daily" in parsed["tables"]:
            rows = [
                {"dt": "2026-09-01", "region": "华东", "order_count": 12_450, "gmv": "9860000.00"},
                {"dt": "2026-09-02", "region": "华东", "order_count": 12_980, "gmv": "10120000.00"},
                {"dt": "2026-09-03", "region": "华东", "order_count": 13_260, "gmv": "10480000.00"},
            ]
        else:
            rows = [
                {
                    "order_id": "O202609010001",
                    "user_id": "u_1001",
                    "pay_amount": "899.00",
                    "settle_amount": "812.00",
                    "gmv": "899.00",
                    "order_status": "PAID",
                    "dt": "2026-09-01",
                }
            ]
        result = {
            "query_id": query_id,
            "status": "succeeded",
            "user_id": user_id,
            "env": env,
            "sql": sql,
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows,
            "row_count": len(rows),
            "elapsed_ms": 842,
            "scanned_rows": 2_450_000,
            "scanned_bytes": 128_974_848,
        }
        self._queries[query_id] = result
        return deepcopy(result)

    def get_query_status(self, query_id: str) -> dict[str, Any]:
        result = self._queries.get(query_id)
        if result is None:
            return {"query_id": query_id, "status": "not_found"}
        return {
            "query_id": query_id,
            "status": result["status"],
            "elapsed_ms": result["elapsed_ms"],
        }

    def get_query_result(self, query_id: str) -> dict[str, Any]:
        return deepcopy(self._queries.get(query_id, {"query_id": query_id, "status": "not_found"}))

    def cancel_query(self, query_id: str) -> dict[str, Any]:
        result = self._queries.get(query_id)
        if result is None:
            return {"query_id": query_id, "status": "not_found"}
        result["status"] = "cancelled"
        return {"query_id": query_id, "status": "cancelled"}

    def get_ticket_context(self, ticket_id: str) -> dict[str, Any]:
        ticket = self.get_ticket_status(ticket_id)
        if ticket["status"] == "not_found":
            return {"found": False, "ticket_id": ticket_id}
        role = deepcopy(ROLES.get(ticket.get("role_id") or "", {})) or None
        history = self.get_permission_history(
            ticket["applicant_id"],
            role_id=ticket.get("role_id"),
            resource={"name": ticket["resource"]},
        )["history"]
        duplicate = self.check_duplicate_permission(
            ticket["applicant_id"],
            {
                "resource": {"name": ticket["resource"]},
                "action": ticket["action"],
                "env": ticket["env"],
            },
        )
        risk = self.analyze_risk(ticket, {"role": role, "history": history})
        return {
            "found": True,
            "ticket": ticket,
            "applicant": {
                "user_id": ticket["applicant_id"],
                "name": "张三" if ticket["applicant_id"] == "u123" else ticket["applicant_id"],
                "department": "销售运营" if ticket["applicant_id"] == "u123" else "未知",
            },
            "roles": [role] if role else [],
            "role_permission_history": history,
            "duplicate_check": duplicate,
            "risk": risk,
            "agent_recommendation": (
                f"建议{'谨慎审批' if risk['level'] in {'high', 'critical'} else '通过'}，"
                f"期限 {ticket['duration_days']} 天，仅 {ticket['action']}。"
                "仅供参考，最终由审批人决定。"
            ),
        }

    def check_duplicate_permission(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]:
        resource = application.get("resource", {})
        resource_name = self._canonical_name(
            resource.get("qualified_name") or resource.get("name") or resource
        )
        action = application.get("action", "select")
        env = application.get("env", "prod")
        existing = self.check_permission(
            applicant_id,
            {"name": resource_name},
            action,
            env,
        )
        return {
            "has_active_same_permission": existing["has_permission"],
            "reason": existing["reason"],
        }

    def analyze_risk(
        self, ticket: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        reasons: list[str] = []
        level = "low"
        if ticket.get("env") == "prod":
            level = "medium"
            reasons.append("涉及生产环境。")
        if ticket.get("action") in {"export", "download"}:
            level = "high"
            reasons.append("申请包含高风险导出动作。")
        if int(ticket.get("duration_days", 0)) > 90:
            level = "high"
            reasons.append("申请期限超过 90 天。")
        elif int(ticket.get("duration_days", 0)) <= 30:
            reasons.append("申请期限处于常规范围。")
        resource = ticket.get("resource", "")
        metadata = self.get_table_metadata(resource)
        if metadata.get("sensitivity_level") == "medium":
            reasons.append("资源包含中敏感度字段。")
        role = context.get("role") or {}
        if role and role.get("business_domain") not in {"销售", "通用"}:
            reasons.append("申请资源可能超出当前角色业务域。")
        return {"level": level, "reasons": reasons}

    def get_approval_history(self, ticket_id: str) -> dict[str, Any]:
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return {"ticket_id": ticket_id, "history": []}
        return {
            "ticket_id": ticket_id,
            "history": (
                [
                    {
                        "status": ticket["status"],
                        "at": ticket.get("approved_at") or ticket["created_at"],
                        "comment": "演示适配器审批记录",
                    }
                ]
                if ticket["status"] != "pending"
                else []
            ),
        }
