import io

import pytest

import data_agent.cli as cli
from data_agent.cli import ChatIdleTimeout, _normalize_argv, build_parser


def test_cli_accepts_http_adapter_configuration() -> None:
    args = build_parser().parse_args(
        [
            "ask",
            "dwd_order 是干嘛的？",
            "--adapter",
            "http",
            "--platform-base-url",
            "https://platform.example.com",
            "--platform-token",
            "secret",
        ]
    )

    assert args.adapter == "http"
    assert args.platform_base_url == "https://platform.example.com"
    assert args.platform_token == "secret"


def test_cli_defaults_to_chat_without_arguments() -> None:
    assert _normalize_argv([]) == ["chat"]


def test_cli_treats_plain_text_as_single_turn_ask() -> None:
    assert _normalize_argv(["dwd_order 是干嘛的？"]) == [
        "ask",
        "dwd_order 是干嘛的？",
    ]


def test_cli_treats_leading_options_as_chat_options() -> None:
    assert _normalize_argv(["--user-id", "u123"]) == [
        "chat",
        "--user-id",
        "u123",
    ]


def test_cli_keeps_explicit_subcommands() -> None:
    assert _normalize_argv(["ask", "问题"]) == ["ask", "问题"]
    assert _normalize_argv(["chat", "--user-id", "u123"]) == [
        "chat",
        "--user-id",
        "u123",
    ]


def test_chat_idle_timeout_defaults_to_ten_minutes() -> None:
    args = build_parser().parse_args(["chat"])

    assert args.chat_idle_timeout_seconds == 600
    assert args.chat_timeout_warning_seconds == 120


def test_chat_input_uses_normal_input_when_not_tty(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO())
    monkeypatch.setattr("builtins.input", lambda prompt: "继续")

    value = cli._read_chat_input(
        "你：",
        idle_timeout_seconds=600,
        warning_seconds=120,
    )

    assert value == "继续"


def test_chat_input_warns_then_raises_idle_timeout(monkeypatch, capsys) -> None:
    class FakeTTY:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            raise AssertionError("readline must not be called on timeout")

    ticks = iter([0.0, 0.0, 8.0, 8.0, 10.1, 10.1])
    monkeypatch.setattr(cli.sys, "stdin", FakeTTY())
    monkeypatch.setattr(cli, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(
        cli.select,
        "select",
        lambda readable, writable, errors, timeout: ([], [], []),
    )

    with pytest.raises(ChatIdleTimeout):
        cli._read_chat_input(
            "你：",
            idle_timeout_seconds=10,
            warning_seconds=2,
        )

    assert "2 秒后自动结束" in capsys.readouterr().out
