import json
import threading
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.graph import DataAgentRuntime
from data_agent.http_server import create_server


class FakeRuntime:
    def __init__(self) -> None:
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(("chat", kwargs))
        return {"status": "interrupted", "interrupt": {"type": "permission_duration"}, "state": {"secret": "internal"}}

    def resume(self, **kwargs):
        self.calls.append(("resume", kwargs))
        return {"status": "completed", "response": {"answer": "已完成"}, "intent": "permission_apply", "state": {"secret": "internal"}}


@contextmanager
def running_server(runtime, token=None):
    server = create_server(runtime, host="127.0.0.1", port=0, token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def request(base, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None if payload is None else json.dumps(payload).encode()
    req = Request(base + path, data=data, headers=headers, method="GET" if payload is None else "POST")
    try:
        with urlopen(req) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def test_chat_and_resume_return_public_results_with_same_session():
    runtime = FakeRuntime()
    with running_server(runtime) as base:
        status, turn = request(base, "/v1/chat", {"user_id": "u123", "message": "申请权限", "env": "dev"})
        assert status == 200
        assert turn["status"] == "interrupted"
        assert turn["interrupt"] == {"type": "permission_duration"}
        assert turn["session_id"].startswith("s-")
        assert "state" not in turn

        status, resumed = request(base, "/v1/resume", {"user_id": "u123", "session_id": turn["session_id"], "decision": {"duration_days": 7}})
        assert status == 200
        assert resumed == {"session_id": turn["session_id"], "status": "completed", "response": {"answer": "已完成"}, "intent": "permission_apply"}

    assert runtime.calls[0][1]["context"] == {"env": "dev"}
    assert runtime.calls[1][1] == {"session_id": turn["session_id"], "decision": {"duration_days": 7}}


def test_invalid_request_does_not_call_runtime():
    runtime = FakeRuntime()
    with running_server(runtime) as base:
        status, body = request(base, "/v1/chat", {"user_id": "u123", "message": "  "})
    assert status == 422
    assert "error" in body
    assert runtime.calls == []


def test_token_rejects_unauthorized_requests():
    runtime = FakeRuntime()
    with running_server(runtime, token="secret") as base:
        status, _ = request(base, "/v1/chat", {"user_id": "u123", "message": "hello"})
        assert status == 401
        status, _ = request(base, "/v1/chat", {"user_id": "u123", "message": "hello"}, token="secret")
        assert status == 200
    assert len(runtime.calls) == 1


def test_session_cannot_be_used_by_another_user():
    runtime = FakeRuntime()
    with running_server(runtime) as base:
        _, turn = request(base, "/v1/chat", {"user_id": "u123", "session_id": "known", "message": "hello"})
        assert turn["status"] == "interrupted"
        status, _ = request(base, "/v1/resume", {"user_id": "another", "session_id": "known", "decision": {"duration_days": 7}})
        assert status == 409
        status, _ = request(base, "/v1/chat", {"user_id": "another", "session_id": "known", "message": "hello"})
        assert status == 409
    assert len(runtime.calls) == 1


def test_real_runtime_answers_over_http():
    runtime = DataAgentRuntime(InMemoryPlatformAdapter())
    with running_server(runtime) as base:
        status, result = request(base, "/v1/chat", {"user_id": "u123", "message": "dwd_order 是干嘛的？"})
    assert status == 200
    assert result["status"] == "completed"
    assert "dwd_order" in result["response"]["answer"]
    assert "state" not in result
