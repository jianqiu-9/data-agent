from data_agent.cli import build_parser


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
