from __future__ import annotations

import argparse
import json
import os
import select
import sys
from time import monotonic
from typing import Any
from uuid import uuid4

from data_agent.adapters.http import HttpPlatformAdapter
from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.graph import DataAgentRuntime
from data_agent.llm import LLMSettings, build_intent_router


class ChatIdleTimeout(RuntimeError):
    """Raised when an interactive prompt exceeds its idle timeout."""


def _read_chat_input(
    prompt: str,
    *,
    idle_timeout_seconds: float,
    warning_seconds: float,
) -> str:
    """Read one line with a POSIX TTY idle timeout."""
    if (
        idle_timeout_seconds <= 0
        or not sys.stdin.isatty()
        or os.name != "posix"
    ):
        return input(prompt)

    print(prompt, end="", flush=True)
    deadline = monotonic() + idle_timeout_seconds
    warned = warning_seconds <= 0

    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ChatIdleTimeout

        wait_seconds = remaining
        if not warned and remaining > warning_seconds:
            wait_seconds = remaining - warning_seconds

        ready, _, _ = select.select([sys.stdin], [], [], wait_seconds)
        if ready:
            line = sys.stdin.readline()
            if line == "":
                raise EOFError
            return line.rstrip("\r\n")

        remaining = deadline - monotonic()
        if not warned and remaining <= warning_seconds:
            print(
                f"\n会话将在 {max(int(warning_seconds), 1)} 秒后自动结束，"
                "可按 Enter 继续。"
            )
            warned = True


def _print_turn(result: dict[str, Any], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result["status"] == "interrupted":
        interrupt = result.get("interrupt", {})
        interrupt_type = interrupt.get("type")
        if interrupt_type == "permission_duration":
            print("\n请选择申请期限：7 / 15 / 30 天")
            return
        if interrupt_type == "permission_role":
            print("\n请选择申请角色：")
            for index, role in enumerate(interrupt.get("roles", []), start=1):
                print(
                    f"{index}. {role['role_name']}（{role['role_id']}）"
                    f"：{role.get('meaning', '')}"
                )
            return
        preview = interrupt.get("preview", {})
        resource = preview.get("resource", {})
        resource_name = (
            resource.get("qualified_name")
            or resource.get("name")
            or str(resource)
        )
        print("\n当前无权限，是否同意一键提单？")
        print(f"资源：{resource_name}")
        print(f"权限：{str(preview.get('action', 'select')).upper()}")
        print(f"环境：{str(preview.get('env', 'prod')).upper()}")
        print(f"建议期限：{preview.get('duration_days', 7)} 天")
        print(f"理由：{preview.get('reason', '')}")
        print(f"预计审批人：{preview.get('approver', '数据 Owner')}")
        return
    response = result.get("response", {})
    print("\n" + response.get("answer", "任务未产生结果。"))
    actions = response.get("actions", [])
    if actions:
        print("\n可执行操作：" + "、".join(item["label"] for item in actions))

# `*` 语法：关键字参数分隔符。`*`后面的参数调用时必须写参数名字，不能只按顺序传值。
def _handle_turn(
    runtime: DataAgentRuntime,
    turn: dict[str, Any],
    *,
    session_id: str,
    auto_confirm: bool,
    as_json: bool,
    interactive: bool,
    idle_timeout_seconds: float = 600,
    warning_seconds: float = 120,
) -> dict[str, Any]:
    while turn["status"] == "interrupted":
        if not as_json or not auto_confirm:
            _print_turn(turn, as_json=as_json)
        if auto_confirm:
            decision = _automatic_decision(turn["interrupt"])
        elif interactive:
            decision = _interactive_decision(
                turn["interrupt"],
                idle_timeout_seconds=idle_timeout_seconds,
                warning_seconds=warning_seconds,
            )
        else:
            return turn
        turn = runtime.resume(
            session_id=session_id,
            decision=decision,
        )
    return turn


def _automatic_decision(interrupt: dict[str, Any]) -> dict[str, Any]:
    interrupt_type = interrupt.get("type")
    if interrupt_type == "permission_duration":
        return {"duration_days": interrupt.get("recommended", 7)}
    if interrupt_type == "permission_role":
        roles = interrupt.get("roles", [])
        return {"role_id": roles[0]["role_id"] if roles else None}
    return {"approved": True}


def _interactive_decision(
    interrupt: dict[str, Any],
    *,
    idle_timeout_seconds: float = 600,
    warning_seconds: float = 120,
) -> dict[str, Any]:
    interrupt_type = interrupt.get("type")
    if interrupt_type == "permission_duration":
        while True:
            value = _read_chat_input(
                "申请期限 [7/15/30]：",
                idle_timeout_seconds=idle_timeout_seconds,
                warning_seconds=warning_seconds,
            ).strip()
            if value in {"7", "15", "30"}:
                return {"duration_days": int(value)}
            print("请输入 7、15 或 30。")
    if interrupt_type == "permission_role":
        roles = interrupt.get("roles", [])
        while True:
            value = _read_chat_input(
                "请输入角色序号或 role_id：",
                idle_timeout_seconds=idle_timeout_seconds,
                warning_seconds=warning_seconds,
            ).strip()
            if value.isdigit():
                index = int(value) - 1
                if 0 <= index < len(roles):
                    return {"role_id": roles[index]["role_id"]}
            if value in {str(role["role_id"]) for role in roles}:
                return {"role_id": value}
            print("角色无效，请重新选择。")
    answer = _read_chat_input(
        "是否同意一键提单？[y/N] ",
        idle_timeout_seconds=idle_timeout_seconds,
        warning_seconds=warning_seconds,
    ).strip().lower()
    return {"approved": answer in {"y", "yes", "是", "确认", "同意"}}


def _runtime(args: argparse.Namespace) -> DataAgentRuntime:
    llm_settings = LLMSettings(
        enabled=args.llm_enabled,
        provider=args.llm_provider,
        model=args.llm_model,
        api_key=args.llm_api_key or os.environ.get("DATA_AGENT_LLM_API_KEY"),
        base_url=args.llm_base_url or os.environ.get("DATA_AGENT_LLM_BASE_URL"),
        temperature=args.llm_temperature,
        timeout_seconds=args.llm_timeout_seconds,
        minimum_confidence=args.llm_min_confidence,
    )
    router = build_intent_router(llm_settings)
    if args.adapter == "http":
        base_url = args.platform_base_url or os.environ.get(
            "DATA_PLATFORM_BASE_URL"
        )
        if not base_url:
            raise ValueError(
                "--platform-base-url or DATA_PLATFORM_BASE_URL is required"
            )
        token = args.platform_token or os.environ.get("DATA_PLATFORM_TOKEN")
        return DataAgentRuntime(
            HttpPlatformAdapter(
                base_url=base_url,
                token=token,
            ),
            router=router,
        )
    return DataAgentRuntime(InMemoryPlatformAdapter(), router=router)


def _chat(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    session_id = args.session_id or f"s-{uuid4().hex[:12]}"
    print(f"Data Agent 会话：{session_id}")
    print("输入 /quit 退出。")
    idle_minutes = args.chat_idle_timeout_seconds / 60
    print(f"空闲 {idle_minutes:g} 分钟将自动结束会话。")
    while True:
        try:
            message = _read_chat_input(
                "\n你：",
                idle_timeout_seconds=args.chat_idle_timeout_seconds,
                warning_seconds=args.chat_timeout_warning_seconds,
            ).strip()
        except EOFError:
            break
        except ChatIdleTimeout:
            print(
                f"\n会话空闲超过 {idle_minutes:g} 分钟，已自动结束。"
            )
            print(
                "已提交到平台的权限工单不会因本次会话超时而取消；"
                "如配置了持久化 Checkpointer，可使用同一 session_id 恢复。"
            )
            break
        if message.lower() in {"/quit", "quit", "exit"}:
            break
        if not message:
            continue
        try:
            turn = runtime.chat(
                user_id=args.user_id,
                session_id=session_id,
                message=message,
                context={"env": args.env},
            )
            turn = _handle_turn(
                runtime,
                turn,
                session_id=session_id,
                auto_confirm=False,
                as_json=args.json,
                interactive=True,
                idle_timeout_seconds=args.chat_idle_timeout_seconds,
                warning_seconds=args.chat_timeout_warning_seconds,
            )
        except EOFError:
            break
        except ChatIdleTimeout:
            print(
                f"\n会话空闲超过 {idle_minutes:g} 分钟，已自动结束。"
            )
            print(
                "已提交到平台的权限工单不会因本次会话超时而取消；"
                "如配置了持久化 Checkpointer，可使用同一 session_id 恢复。"
            )
            break
        _print_turn(turn, as_json=args.json)
    return 0


def _ask(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    session_id = args.session_id or f"s-{uuid4().hex[:12]}"
    turn = runtime.chat(
        user_id=args.user_id,
        session_id=session_id,
        message=args.message,
        context={"env": args.env},
    )
    turn = _handle_turn(
        runtime,
        turn,
        session_id=session_id,
        auto_confirm=args.yes,
        as_json=args.json,
        interactive=False,
    )
    if turn["status"] == "completed" and not args.json:
        _print_turn(turn)
    elif args.json:
        _print_turn(turn, as_json=True)
    return 0 if turn["status"] == "completed" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Data platform LangGraph agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat_parser = subparsers.add_parser("chat", help="进入交互式对话")
    _add_common_args(chat_parser)

    ask_parser = subparsers.add_parser("ask", help="执行单轮请求")
    _add_common_args(ask_parser)
    ask_parser.add_argument("message", help="用户问题")
    ask_parser.add_argument(
        "--yes",
        action="store_true",
        help="遇到权限申请确认时自动确认提交",
    )
    return parser


def _normalize_argv(argv: list[str] | None) -> list[str]:
    raw = list(sys.argv[1:] if argv is None else argv)
    if not raw:
        return ["chat"]
    if raw[0] in {"ask", "chat", "-h", "--help"}:
        return raw
    if raw[0].startswith("-"):
        return ["chat", *raw]
    return ["ask", *raw]


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    llm_defaults = LLMSettings.from_environment()
    parser.add_argument("--user-id", default="u123", help="当前用户 ID")
    parser.add_argument("--session-id", help="对话会话 ID")
    parser.add_argument(
        "--adapter",
        default=os.environ.get("DATA_AGENT_ADAPTER", "memory"),
        choices=["memory", "http"],
        help="平台适配器：memory 为本地演示，http 为真实 REST 接口",
    )
    parser.add_argument(
        "--platform-base-url",
        help="真实平台 REST API 根地址",
    )
    parser.add_argument(
        "--platform-token",
        help="真实平台 Bearer Token",
    )
    parser.add_argument(
        "--llm-enabled",
        action=argparse.BooleanOptionalAction,
        default=llm_defaults.enabled,
        help="启用 LLM 意图路由",
    )
    parser.add_argument(
        "--llm-provider",
        default=llm_defaults.provider,
        choices=["openai", "openai_compatible"],
    )
    parser.add_argument(
        "--llm-model",
        default=llm_defaults.model,
    )
    parser.add_argument("--llm-api-key", help="LLM API Key")
    parser.add_argument("--llm-base-url", help="OpenAI-compatible API 根地址")
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=llm_defaults.temperature,
    )
    parser.add_argument(
        "--llm-timeout-seconds",
        type=float,
        default=llm_defaults.timeout_seconds,
    )
    parser.add_argument(
        "--llm-min-confidence",
        type=float,
        default=llm_defaults.minimum_confidence,
    )
    parser.add_argument(
        "--chat-idle-timeout-seconds",
        type=float,
        default=float(
            os.environ.get("DATA_AGENT_CHAT_IDLE_TIMEOUT_SECONDS", "600")
        ),
        help="交互式对话空闲超时，默认 600 秒",
    )
    parser.add_argument(
        "--chat-timeout-warning-seconds",
        type=float,
        default=float(
            os.environ.get("DATA_AGENT_CHAT_TIMEOUT_WARNING_SECONDS", "120")
        ),
        help="空闲超时前的提醒时间，默认 120 秒",
    )
    parser.add_argument(
        "--env", default="prod", choices=["dev", "staging", "prod"], help="平台环境"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(_normalize_argv(argv))
    if args.command == "chat":
        return _chat(args)
    if args.command == "ask":
        return _ask(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
