from __future__ import annotations

from typing import Any


def format_asset_search(result: dict[str, Any]) -> str:
    assets = result.get("assets", [])
    if not assets:
        return "数据目录中没有找到匹配的数据资产。"
    lines = [f"找到 {len(assets)} 个相关数据资产："]
    for index, asset in enumerate(assets[:5], start=1):
        permission = asset.get("permission", {})
        permission_text = "有权限" if permission.get("has_permission") else "无权限"
        lines.extend(
            [
                f"\n{index}. {asset['qualified_name']}",
                f"用途：{asset['description']}",
                f"粒度：{asset['grain']}",
                f"更新时间：{asset['update_frequency']}",
                f"当前状态：{permission_text}",
            ]
        )
    return "\n".join(lines)


def format_table_metadata(metadata: dict[str, Any]) -> str:
    if not metadata.get("found"):
        return metadata.get("message", f"未找到 {metadata.get('resource', '目标表')}。")
    fields = metadata.get("fields", [])[:8]
    field_lines = "\n".join(
        f"- {field['name']}：{field['description']}" for field in fields
    )
    return (
        f"表：{metadata['qualified_name']}\n\n"
        f"业务含义：{metadata['description']}\n\n"
        f"数据粒度：{metadata['grain']}\n"
        f"主要用途：{metadata['business_domain']}域数据分析和相关指标计算。\n"
        f"数据范围：{metadata['data_range']}\n"
        f"更新频率：{metadata['update_frequency']}\n"
        f"负责人：{metadata['owner']}\n\n"
        f"主要字段：\n{field_lines}"
    )


def format_columns(
    table: str, columns: list[dict[str, Any]], field_names: list[str]
) -> str:
    if not columns:
        return f"未找到 {table} 中字段 {', '.join(field_names)} 的元数据。"
    lines = [f"{table} 字段说明："]
    for field in columns:
        lines.append(
            f"\n- {field['name']}：{field['description']}"
            f"（类型：{field['type']}）"
        )
    if len(columns) >= 2:
        lines.append("\n两者口径不同，SQL 计算时必须按对应字段的业务定义选择。")
    return "\n".join(lines)


def format_metric(metric: dict[str, Any]) -> str:
    return (
        f"指标：{metric['metric_name']}\n"
        f"定义：{metric['definition']}\n"
        f"公式：{metric['formula']}\n"
        f"时间维度：{metric['time_dimension']}\n"
        f"过滤条件：{metric['filter_condition']}\n"
        f"来源资产：{metric['source_asset']}\n"
        f"负责人：{metric['owner']}\n"
        f"版本：{metric['version']}"
    )


def format_permission(result: dict[str, Any]) -> str:
    if result.get("has_permission"):
        return (
            f"有权限。\n\n"
            f"资源：{result['resource']}\n"
            f"动作：{result['action']}\n"
            f"环境：{result['env']}\n"
            f"有效期：{result['expires_at']}\n"
            f"来源角色：{result.get('role_name') or result.get('role_id')}\n"
            f"权限范围：{result.get('role_meaning')}"
        )
    return (
        f"当前没有 {result['resource']} 的 {result['env']} 环境 "
        f"{result['action'].upper()} 权限。\n\n"
        f"当前角色：{result.get('role_name') or '未知'}\n"
        f"原因：{result['reason']}"
    )


def format_permission_preview(preview: dict[str, Any]) -> str:
    resource = preview.get("resource", {})
    resource_name = (
        resource.get("qualified_name")
        or resource.get("name")
        or str(resource)
    )
    return (
        "权限申请预览\n\n"
        f"资源：{resource_name}\n"
        f"权限：{str(preview.get('action', 'select')).upper()}\n"
        f"环境：{str(preview.get('env', 'prod')).upper()}\n"
        f"建议期限：{preview.get('duration_days', 30)} 天\n"
        f"申请理由：{preview.get('reason', '')}\n"
        f"预计审批人：{preview.get('approver', '数据 Owner')}\n\n"
        "回复“确认提交”后，我会创建权限工单。"
    )


def format_permission_history(result: dict[str, Any]) -> str:
    history = result.get("history", [])
    if not history:
        return "没有查询到相关历史权限记录。"
    lines = ["历史权限："]
    for item in history:
        lines.append(
            f"\n- {item['resource']} / {item['action'].upper()} / {item['status']}\n"
            f"  工单：{item.get('ticket_id', '无')}\n"
            f"  生效：{item.get('granted_at', '未知')}\n"
            f"  过期：{item.get('expires_at', '长期有效')}"
        )
    return "\n".join(lines)


def format_role(role: dict[str, Any]) -> str:
    return (
        f"角色：{role['role_name']}（{role['role_id']}）\n\n"
        f"含义：{role['meaning']}\n"
        f"业务域：{role['business_domain']}\n"
        f"主要职责：{'、'.join(role['responsibilities'])}\n"
        f"权限边界：{role['permission_boundary']}\n"
        f"风险等级：{role['risk_level']}\n"
        f"负责人：{role['owner']}\n"
        f"来源：角色元数据 {role['docs']}"
    )


def format_sql_analysis(
    sql: str,
    validation: dict[str, Any],
    parsed: dict[str, Any],
    context: dict[str, Any],
    explain: dict[str, Any],
) -> str:
    if not validation.get("valid"):
        return "SQL 校验未通过：\n" + "\n".join(
            f"- {error}" for error in validation.get("errors", [])
        )
    tables = "、".join(parsed.get("tables", [])) or "未识别"
    plan_lines = []
    for step in explain.get("plan", []):
        plan_lines.append(
            f"- {step['table']}：access_type={step['access_type']}，"
            f"预计扫描 {step['estimated_rows']:,} 行，key={step.get('key') or '无'}"
        )
    warnings = validation.get("warnings", [])
    warning_text = (
        "\nSQL 风险提示：\n" + "\n".join(f"- {item}" for item in warnings)
        if warnings
        else ""
    )
    return (
        f"SQL 分析完成。\n\n"
        f"涉及表：{tables}\n"
        f"是否 JOIN：{'是' if parsed.get('has_join') else '否'}\n"
        f"是否聚合：{'是' if parsed.get('has_aggregate') else '否'}\n\n"
        f"执行计划：\n"
        + ("\n".join(plan_lines) if plan_lines else "- 暂无执行计划")
        + f"\n\n预计扫描行数：{explain.get('estimated_scan_rows', 0):,}"
        + warning_text
        + f"\n\n上下文：已获取 {len(context.get('ddl', {}))} 张表的 DDL、"
        f"{len(context.get('indexes', {}))} 张表的索引和统计信息。"
    )


def format_optimization(analysis: dict[str, Any]) -> str:
    issues = analysis.get("issues", [])
    issue_lines = "\n".join(f"- {item}" for item in issues) or "- 未发现明显结构性问题"
    index_lines = "\n".join(
        f"- {item['table']}({', '.join(item['columns'])})：{item['reason']}\n  建议：{item['ddl']}"
        for item in analysis.get("index_suggestions", [])
    ) or "- 暂无新增索引建议"
    join_lines = "\n".join(
        f"- {item['issue']} {item['suggestion']}"
        for item in analysis.get("join_optimization", [])
    ) or "- 暂无 JOIN 优化项"
    risk_lines = "\n".join(f"- {item}" for item in analysis.get("risk", []))
    return (
        f"SQL 问题诊断：\n{issue_lines}\n\n"
        f"索引建议：\n{index_lines}\n\n"
        f"JOIN 优化：\n{join_lines}\n\n"
        f"优化 SQL：\n```sql\n{analysis.get('rewritten_sql', analysis.get('sql', ''))}\n```\n\n"
        f"风险说明：\n{risk_lines}"
    )


def format_query_result(result: dict[str, Any]) -> str:
    if result.get("status") != "succeeded":
        return (
            "查询未执行："
            + "；".join(result.get("errors", [result.get("status", "未知错误")]))
        )
    rows = result.get("rows", [])
    preview = rows[:10]
    lines = [
        f"查询状态：{result['status']}",
        f"执行耗时：{result['elapsed_ms']} ms",
        f"扫描数据量：{result['scanned_rows']:,} 行",
        f"返回行数：{result['row_count']}",
        "",
        "结果预览：",
    ]
    if preview:
        headers = list(preview[0].keys())
        lines.append(" | ".join(headers))
        lines.append(" | ".join("---" for _ in headers))
        for row in preview:
            lines.append(" | ".join(str(row.get(header, "")) for header in headers))
    else:
        lines.append("无返回数据")
    return "\n".join(lines)


def format_query_explanation(result: dict[str, Any], question: str) -> str:
    rows = result.get("rows", [])
    if not rows:
        return "已获取查询结果，但没有可用于解释的数据行。"
    lines = ["基于当前真实查询结果，可以得到以下事实："]
    for row in rows[:5]:
        lines.append(
            "- " + "，".join(f"{key}={value}" for key, value in row.items())
        )
    if any(word in question for word in ["为什么", "原因", "下降"]):
        lines.append(
            "\n当前结果中不包含历史对比、贡献拆解或因果关系数据，"
            "不能据此编造下降原因。需要继续按时间、区域或用户分群查询后才能判断。"
        )
    else:
        lines.append("\n以上结论仅基于本次查询返回的数据。")
    return "\n".join(lines)


def format_approval_context(context: dict[str, Any]) -> str:
    if not context.get("found"):
        return f"未找到工单 {context.get('ticket_id', '')}。"
    ticket = context["ticket"]
    applicant = context["applicant"]
    role = context["roles"][0] if context.get("roles") else {}
    duplicate = context["duplicate_check"]
    risk = context["risk"]
    history = context.get("role_permission_history", [])
    history_text = (
        "\n".join(
            f"- {item['resource']} / {item['action'].upper()} / {item['status']} / "
            f"{item.get('expires_at', '长期有效')}"
            for item in history
        )
        if history
        else "- 无历史权限记录"
    )
    return (
        f"申请人：{applicant['name']}（{applicant['user_id']}）\n"
        f"部门：{applicant['department']}\n\n"
        f"本次申请：{ticket['resource']} / {ticket['action'].upper()} / "
        f"{ticket['env']} / {ticket['duration_days']} 天\n"
        f"申请理由：{ticket['reason']}\n\n"
        f"角色：{role.get('role_name', '未知')}\n"
        f"角色含义：{role.get('meaning', '未知')}\n"
        f"权限边界：{role.get('permission_boundary', '未知')}\n\n"
        f"历史权限：\n{history_text}\n\n"
        f"重复检查：{'存在有效相同权限' if duplicate['has_active_same_permission'] else '当前无有效相同权限'}\n"
        f"风险等级：{risk['level']}\n"
        f"风险原因：{'；'.join(risk['reasons'])}\n\n"
        f"Agent 建议：{context['agent_recommendation']}"
    )


def format_ticket_status(ticket: dict[str, Any]) -> str:
    if ticket.get("status") == "not_found":
        return f"未找到工单 {ticket.get('ticket_id', '')}。"
    return (
        f"工单：{ticket['ticket_id']}\n"
        f"状态：{ticket['status']}\n"
        f"资源：{ticket['resource']}\n"
        f"权限：{ticket['action'].upper()}\n"
        f"环境：{ticket['env']}\n"
        f"期限：{ticket['duration_days']} 天\n"
        f"创建时间：{ticket['created_at']}"
    )
