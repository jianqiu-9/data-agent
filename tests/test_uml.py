from pathlib import Path


def test_all_sequence_diagram_covers_permission_flow() -> None:
    content = Path("uml/all.puml").read_text(encoding="utf-8")

    assert "@startuml" in content
    assert "用户" in content
    assert "LangGraph" in content
    assert "是否同意一键提单" in content
    assert "申请期限" in content
    assert "选择角色" in content
    assert "X-User-Id" in content
    assert "@enduml" in content
