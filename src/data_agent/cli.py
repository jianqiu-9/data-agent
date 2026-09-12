from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from uuid import uuid4

from data_agent.adapters.http import HttpPlatformAdapter
from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.graph import DataAgentRuntime


def _print_turn(result: dict[str, Any], *, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if result["status"] == "interrupted":
        interrupt = result.get("interrupt", {})
        preview = interrupt.get("preview", {})
        resource = preview.get("resource", {})
        resource_name = (
            resource.get("qualified_name")
            or resource.get("name")
            or str(resource)
        )
        print("\n权限申请预览")
        print(f"资源：{resource_name}")
        print(f"权限：{str(preview.get('action', 'select')).upper()}")
        print(f"环境：{str(preview.get('env', 'prod')).upper()}")
        print(f"期限：{preview.get('duration_days', 30)} 天")
        print(f"理由：{preview.get('reason', '')}")
        print(f"预计审批人：{preview.get('approver', '数据 Owner')}")
        return
    response = result.get("response", {})
    print("\n" + response.get("answer", "任务未产生结果。"))
    actions = response.get("actions", [])
    if actions:
        print("\n可执行操作：" + "、".join(item["label"] for item in actions))


def _handle_turn(
    runtime: DataAgentRuntime,
    turn: dict[str, Any],
    *,
    session_id: str,
    auto_confirm: bool,
    as_json: bool,
    interactive: bool,
) -> dict[str, Any]:
    if turn["status"] != "interrupted":
        return turn
    if not as_json or not auto_confirm:
        _print_turn(turn, as_json=as_json)
    approved = auto_confirm
    if interactive and not auto_confirm:
        answer = input("确认提交？[y/N] ").strip().lower()
        approved = answer in {"y", "yes", "是", "确认", "提交"}
    if not approved and not interactive:
        return turn
    return runtime.resume(session_id=session_id, approved=approved)


def _runtime(args: argparse.Namespace) -> DataAgentRuntime:
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
            )
        )
    return DataAgentRuntime(InMemoryPlatformAdapter())


def _chat(args: argparse.Namespace) -> int:
    runtime = _runtime(args)
    session_id = args.session_id or f"s-{uuid4().hex[:12]}"
    print(f"Data Agent 会话：{session_id}")
    print("输入 /quit 退出。")
    while True:
        try:
            message = input("\n你：").strip()
        except EOFError:
            break
        if message.lower() in {"/quit", "quit", "exit"}:
            break
        if not message:
            continue
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
        )
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


def _add_common_args(parser: argparse.ArgumentParser) -> None:
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
        "--env", default="prod", choices=["dev", "staging", "prod"], help="平台环境"
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "chat":
        return _chat(args)
    if args.command == "ask":
        return _ask(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    sys.exit(main())
