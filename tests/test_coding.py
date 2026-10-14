from data_agent.coding import CodeTask, CodingAgent, DockerSandbox, SandboxResult


def test_coding_agent_returns_code_and_independent_test_result() -> None:
    class Generator:
        def generate(self, task):
            return "def transform(rows):\n    return [row['x'] * 2 for row in rows]\n"

    class Sandbox:
        def run(self, code, tests):
            assert "transform" in code
            assert "assert" in tests
            return SandboxResult(status="passed", exit_code=0, stdout="1 passed", stderr="")

    task = CodeTask(goal="数值乘二", test_source="from solution import transform\nassert transform([{'x': 2}]) == [4]")
    result = CodingAgent(Generator(), Sandbox()).run(task)
    assert result["status"] == "passed"
    assert result["code"].startswith("def transform")


def test_docker_sandbox_command_is_isolated() -> None:
    image = "python@sha256:" + "a" * 64
    sandbox = DockerSandbox(image=image)
    command = sandbox.command("/tmp/work")
    assert "--network=none" in command
    assert "--read-only" in command
    assert "--cap-drop=ALL" in command
    assert "--pids-limit=64" in command
    assert "--privileged" not in command
