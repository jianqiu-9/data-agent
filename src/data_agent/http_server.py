"""HTTP entry point for platforms calling the agent."""

from __future__ import annotations

import argparse
import json
import os
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from data_agent.graph import DataAgentRuntime


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    session_id: str | None = Field(default=None, min_length=1)
    env: Literal["dev", "staging", "prod"] = "prod"

    @field_validator("user_id", "message", "session_id")
    @classmethod
    def non_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("must not be blank")
        return value


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    decision: dict[str, Any]

    @field_validator("user_id", "session_id")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


def _public_turn(turn: dict[str, Any], session_id: str) -> dict[str, Any]:
    result = {"session_id": session_id, "status": turn["status"]}
    if turn["status"] == "interrupted":
        result["interrupt"] = turn.get("interrupt", {})
    else:
        result["response"] = turn.get("response", {})
        result["intent"] = turn.get("intent")
    return result


def create_server(
    runtime: DataAgentRuntime,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    token: str | None = None,
    user_tokens: dict[str, str] | None = None,
) -> ThreadingHTTPServer:
    """创建共享 Runtime 的 HTTP 服务；远程绑定须有可信用户令牌映射。"""
    if token and user_tokens:
        raise ValueError("共享令牌与用户令牌映射不能同时启用")
    if user_tokens is not None and (not user_tokens or any(not secret or not user for secret, user in user_tokens.items())):
        raise ValueError("用户令牌映射不能为空或包含空值")
    if host not in {"127.0.0.1", "localhost"} and not user_tokens:
        raise ValueError("非本地监听需要用户令牌映射或可信身份提供者")

    lock = RLock()
    session_users: dict[str, str] = {}
    interrupted_sessions: set[str] = set()

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            self._authenticated_user: str | None = None
            if user_tokens is not None:
                actual = self.headers.get("Authorization", "")
                for secret, user in user_tokens.items():
                    if compare_digest(actual, f"Bearer {secret}"):
                        self._authenticated_user = user
                        return True
                self._send_json(401, {"error": "unauthorized"})
                return False
            if token is None:
                return True
            actual = self.headers.get("Authorization", "")
            if not compare_digest(actual, f"Bearer {token}"):
                self._send_json(401, {"error": "unauthorized"})
                return False
            return True

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send_json(404, {"error": "not found"})
            elif self._authorized():
                self._send_json(200, {"status": "ok"})

        def do_POST(self) -> None:
            if self.path not in {"/v1/chat", "/v1/resume"}:
                self._send_json(404, {"error": "not found"})
                return
            if not self._authorized():
                return
            if self.headers.get_content_type() != "application/json":
                self._send_json(415, {"error": "Content-Type must be application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send_json(400, {"error": "Content-Length is required"})
                return
            if length < 1 or length > 1024 * 1024:
                self._send_json(413, {"error": "request body must be between 1 byte and 1 MiB"})
                return
            body = self.rfile.read(length)
            try:
                if self.path == "/v1/chat":
                    request = ChatRequest.model_validate_json(body)
                    if self._authenticated_user is not None and request.user_id != self._authenticated_user:
                        self._send_json(403, {"error": "user does not match authenticated principal"})
                        return
                    session_id = request.session_id or f"s-{uuid4().hex[:12]}"
                    with lock:
                        owner = session_users.get(session_id)
                        if owner is not None and owner != request.user_id:
                            self._send_json(409, {"error": "session belongs to another user"})
                            return
                        if session_id in interrupted_sessions:
                            self._send_json(409, {"error": "resume the interrupted session first"})
                            return
                        turn = runtime.chat(
                            user_id=request.user_id,
                            session_id=session_id,
                            message=request.message,
                            context={"env": request.env},
                        )
                        session_users[session_id] = request.user_id
                        if turn["status"] == "interrupted":
                            interrupted_sessions.add(session_id)
                else:
                    request = ResumeRequest.model_validate_json(body)
                    if self._authenticated_user is not None and request.user_id != self._authenticated_user:
                        self._send_json(403, {"error": "user does not match authenticated principal"})
                        return
                    session_id = request.session_id
                    with lock:
                        if session_users.get(session_id) != request.user_id:
                            self._send_json(409, {"error": "unknown session or user"})
                            return
                        if session_id not in interrupted_sessions:
                            self._send_json(409, {"error": "session is not interrupted"})
                            return
                        turn = runtime.resume(session_id=session_id, decision=request.decision)
                        if turn["status"] != "interrupted":
                            interrupted_sessions.remove(session_id)
                self._send_json(200, _public_turn(turn, session_id))
            except ValidationError as exc:
                self._send_json(422, {"error": "invalid request", "details": exc.errors(include_url=False, include_context=False)})
            except Exception:
                self._send_json(500, {"error": "agent request failed"})

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve Data Agent over HTTP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    from data_agent.cli import _runtime, build_parser

    runtime = _runtime(build_parser().parse_args(["chat"]))
    user_tokens_json = os.environ.get("DATA_AGENT_HTTP_USER_TOKENS_JSON")
    user_tokens = json.loads(user_tokens_json) if user_tokens_json else None
    if user_tokens is not None and (not isinstance(user_tokens, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in user_tokens.items())):
        raise ValueError("DATA_AGENT_HTTP_USER_TOKENS_JSON 必须是令牌到用户 ID 的对象")
    server = create_server(
        runtime,
        host=args.host,
        port=args.port,
        token=os.environ.get("DATA_AGENT_HTTP_TOKEN"),
        user_tokens=user_tokens,
    )
    try:
        print(f"Data Agent HTTP listening on http://{args.host}:{server.server_port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
