import httpx
import pytest

from data_agent.adapters.http import (
    TOOL_ENDPOINTS,
    HttpPlatformAdapter,
    PlatformAPIError,
)
from data_agent.tooling import TOOL_NAMES


def make_adapter(handler) -> tuple[HttpPlatformAdapter, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = httpx.Client(
        base_url="https://platform.example.com",
        transport=httpx.MockTransport(record),
    )
    return HttpPlatformAdapter(
        base_url="https://platform.example.com",
        client=client,
    ), requests


def test_http_adapter_implements_all_agent_tools() -> None:
    adapter, _ = make_adapter(lambda request: httpx.Response(200, json={}))

    assert all(callable(getattr(adapter, name, None)) for name in TOOL_NAMES)
    assert set(TOOL_ENDPOINTS) == set(TOOL_NAMES)


def test_search_assets_calls_declared_endpoint() -> None:
    adapter, requests = make_adapter(
        lambda request: httpx.Response(200, json={"assets": [], "total": 0})
    )

    result = adapter.search_data_assets("销售订单", limit=3)

    assert result == {"assets": [], "total": 0}
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/v1/data-assets/search"
    assert requests[0].url.params["query"] == "销售订单"
    assert requests[0].url.params["limit"] == "3"


def test_permission_check_posts_expected_payload() -> None:
    adapter, requests = make_adapter(
        lambda request: httpx.Response(200, json={"has_permission": False})
    )

    adapter.check_permission(
        user_id="u123",
        resource={"type": "table", "database": "dw", "name": "dwd_order"},
        action="select",
        env="prod",
    )

    request = requests[0]
    assert request.method == "POST"
    assert request.url.path == "/api/v1/tools/permission/check"
    assert request.content
    assert b'"user_id":"u123"' in request.content
    assert b'"name":"dwd_order"' in request.content


def test_create_ticket_uses_prd_flat_payload() -> None:
    adapter, requests = make_adapter(
        lambda request: httpx.Response(
            200,
            json={"ticket_id": "T202609120001", "status": "pending"},
        )
    )

    adapter.create_permission_ticket(
        "u123",
        {
            "role_id": "r_sales_analyst",
            "resource": {
                "type": "table",
                "database": "dw",
                "name": "dwd_order",
            },
            "action": "select",
            "env": "prod",
            "duration_days": 7,
            "reason": "订单分析",
            "approver": "销售数据 Owner",
        },
    )

    request = requests[0]
    assert request.url.path == "/api/v1/tools/permission/tickets"
    body = request.content.decode()
    assert '"applicant_id":"u123"' in body
    assert '"duration_days":7' in body
    assert '"approver_id":"销售数据 Owner"' in body
    assert '"application"' not in body


def test_platform_error_exposes_status_and_body() -> None:
    adapter, _ = make_adapter(
        lambda request: httpx.Response(503, json={"message": "platform unavailable"})
    )

    with pytest.raises(PlatformAPIError) as error:
        adapter.get_table_metadata("dw.dwd_order")

    assert error.value.status_code == 503
    assert "platform unavailable" in error.value.body
