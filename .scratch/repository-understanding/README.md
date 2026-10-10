# Data Agent 阅读地图

- [概览](00-executive-summary.md)：目的、架构与边界。
- [请求生命周期](01-request-lifecycle.md)：输入、路由、工具、记忆、终止、回写和失败场景。
- [已知未知](known-unknowns.md)：不能从仓库证实的运行行为。

建议顺序：先看 `graph.py` 的边，再看 `routing.py`，最后沿 `nodes.py` 的查询及权限申请路径读 `tooling.py` 和适配器。
