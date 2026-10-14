"""仅依据完整查询结果计算可复核的数据分析摘要。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


class DataAnalysisAgent:
    def summarize(self, result: dict[str, Any], *, measures: list[str]) -> dict[str, Any]:
        """对显式指定的度量求和；结果不完整时禁止报告总量。"""
        query_id = result.get("query_id")
        rows = result.get("rows")
        if result.get("status") != "succeeded" or not query_id or not isinstance(rows, list):
            return {"status": "insufficient_evidence", "query_id": query_id, "totals": {}, "limitations": ["没有成功且可读取的查询结果"]}
        if not rows:
            return {"status": "verified", "query_id": query_id, "row_count": 0, "totals": {}, "dimensions": [], "limitations": ["结果为空"]}
        # 平台可能返回非对象行；先校验首行，避免读取列集合时抛出未处理异常。
        if not isinstance(rows[0], dict):
            return {"status": "insufficient_evidence", "query_id": query_id, "totals": {}, "limitations": ["查询结果行不是对象"]}
        keys = set(rows[0])
        if any(not isinstance(row, dict) or set(row) != keys for row in rows):
            return {"status": "insufficient_evidence", "query_id": query_id, "totals": {}, "limitations": ["返回行的列结构不一致"]}
        if any(measure not in keys for measure in measures):
            return {"status": "insufficient_evidence", "query_id": query_id, "totals": {}, "limitations": ["指定度量列不存在"]}
        if result.get("row_count") != len(rows):
            return {"status": "partial", "query_id": query_id, "row_count": result.get("row_count"), "totals": {}, "limitations": ["只取得部分行，不能计算全量汇总"]}
        totals: dict[str, str] = {}
        for measure in measures:
            try:
                # Decimal 避免浮点误差；NULL 不参与加总，非法数值则停止。
                values = [Decimal(str(row[measure])) for row in rows if row[measure] is not None]
            except (InvalidOperation, TypeError, ValueError):
                return {"status": "insufficient_evidence", "query_id": query_id, "totals": {}, "limitations": [f"度量 {measure} 含非数值"]}
            if any(not value.is_finite() for value in values):
                return {"status": "insufficient_evidence", "query_id": query_id, "totals": {}, "limitations": [f"度量 {measure} 含非有限数值"]}
            totals[measure] = str(sum(values, Decimal(0)))
        return {
            "status": "verified",
            "query_id": query_id,
            "row_count": len(rows),
            "totals": totals,
            "dimensions": sorted(keys - set(measures)),
            "limitations": ["加总仅对返回行成立；跨粒度汇总需先核实业务口径"],
        }
