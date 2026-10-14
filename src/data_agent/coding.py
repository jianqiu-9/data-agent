"""数据处理代码生成与隔离测试；绝不在主进程执行模型代码。"""

from __future__ import annotations

import re
import os
import subprocess
import tempfile
from uuid import uuid4
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CodeTask(BaseModel):
    """独立测试由调用方提供，不能使用模型同时生成的自证测试。"""

    model_config = ConfigDict(extra="forbid", strict=True)
    goal: str = Field(min_length=1, max_length=2000)
    test_source: str = Field(min_length=1, max_length=20000)


@dataclass(frozen=True)
class SandboxResult:
    status: str
    exit_code: int | None
    stdout: str
    stderr: str


class CodeGenerator(Protocol):
    def generate(self, task: CodeTask) -> str:
        """根据任务目标生成代码，不读取独立验收测试。"""
        ...


class CodeSandbox(Protocol):
    def run(self, code: str, tests: str) -> SandboxResult:
        """在隔离环境运行代码与测试，返回退出状态和有限输出。"""
        ...


class LLMCodeGenerator:
    """从模型读取 Python 源码；执行与正确性均由沙箱及独立测试决定。"""

    def __init__(self, model: Any) -> None:
        """保存已由启动者配置的模型实例。"""
        self.model = model

    def generate(self, task: CodeTask) -> str:
        """只将任务目标发送给模型，不泄露用于验收的独立测试。"""
        response = self.model.invoke("生成 Python 数据处理代码，只输出源码，不要 Markdown。需求：" + task.goal)
        return self._content(response)

    def repair(self, task: CodeTask, code: str, error: str) -> str:
        """最多两轮修复时提供失败摘要，仍须重新执行同一独立测试。"""
        response = self.model.invoke("修复下面的 Python 数据处理代码，只输出源码。需求：" + task.goal + "\n代码：\n" + code[:10000] + "\n测试错误：\n" + error[:2000])
        return self._content(response)

    @staticmethod
    def _content(response: Any) -> str:
        """提取模型文本并限制长度，拒绝非文本响应。"""
        content = getattr(response, "content", response)
        if not isinstance(content, str):
            raise ValueError("代码模型未返回文本")
        value = content.strip()
        if value.startswith("```python") and value.endswith("```"):
            value = value[len("```python") : -3].strip()
        if not value or len(value) > 100000:
            raise ValueError("生成代码为空或超过大小上限")
        return value


class DockerSandbox:
    """使用外部 Docker 守护进程运行代码；缺失或失败时安全关闭。"""

    def __init__(self, *, image: str, timeout_seconds: int = 60) -> None:
        """校验固定镜像和时间上限，避免模型决定运行环境。"""
        if not re.fullmatch(r"[a-zA-Z0-9._/-]+@sha256:[a-f0-9]{64}", image):
            raise ValueError("沙箱镜像必须固定到 sha256 摘要")
        if not 1 <= timeout_seconds <= 120:
            raise ValueError("沙箱超时必须在 1 到 120 秒之间")
        self.image = image
        self.timeout_seconds = timeout_seconds

    def command(self, workdir: str, *, name: str | None = None) -> list[str]:
        """生成固定隔离选项；workdir 只挂载临时任务目录的只读副本。"""
        command = [
            "docker", "run", "--rm", "--network=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--user=65534:65534", "--pids-limit=64", "--memory=2g", "--cpus=2",
            "--tmpfs=/tmp:rw,nosuid,noexec,size=64m",
            f"--mount=type=bind,src={workdir},dst=/workspace,readonly",
        ]
        if name is not None:
            command.append(f"--name={name}")
        return command + ["--workdir=/workspace", self.image, "python", "-B", "tests.py"]

    def run(self, code: str, tests: str) -> SandboxResult:
        """把代码与独立测试放进临时目录，在容器中执行并收集有限输出。"""
        if len(code) > 100_000 or len(tests) > 20_000:
            raise ValueError("代码或测试超过沙箱输入上限")
        with tempfile.TemporaryDirectory(prefix="data-agent-code-") as workdir:
            # 仅这两个生成文件进入容器，宿主项目和密钥不挂载。
            Path(workdir, "solution.py").write_text(code, encoding="utf-8")
            Path(workdir, "tests.py").write_text(tests, encoding="utf-8")
            os.chmod(workdir, 0o755)
            os.chmod(Path(workdir, "solution.py"), 0o644)
            os.chmod(Path(workdir, "tests.py"), 0o644)
            container_name = "data-agent-code-" + uuid4().hex
            try:
                completed = subprocess.run(
                    self.command(workdir, name=container_name), capture_output=True, text=True,
                    timeout=self.timeout_seconds, check=False,
                )
            except FileNotFoundError as exc:
                raise RuntimeError("Docker 沙箱不可用") from exc
            except subprocess.TimeoutExpired:
                # CLI 超时后主动终止仍可能运行的容器，避免任务悬挂。
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10, check=False)
                return SandboxResult("timeout", None, "", "沙箱执行超时")
            return SandboxResult(
                "passed" if completed.returncode == 0 else "failed",
                completed.returncode,
                completed.stdout[:8000],
                completed.stderr[:8000],
            )


class CodingAgent:
    def __init__(self, generator: CodeGenerator, sandbox: CodeSandbox) -> None:
        """组合代码生成器和隔离执行器；两者由服务端注入。"""
        self.generator = generator
        self.sandbox = sandbox

    def run(self, task: CodeTask) -> dict[str, str | int | None]:
        """生成代码并运行独立测试；测试失败最多修复两次。"""
        last: SandboxResult | None = None
        code = ""
        attempts = 0
        for attempt in range(3):
            # 首次生成；仅在生成器提供 repair 方法时把失败摘要用于有限修复。
            if attempt == 0:
                code = self.generator.generate(task)
            else:
                repair = getattr(self.generator, "repair", None)
                if not callable(repair):
                    break
                code = repair(task, code, (last.stderr if last else "")[:2000])
            if not isinstance(code, str) or not code.strip():
                raise ValueError("模型未生成有效代码")
            last = self.sandbox.run(code, task.test_source)
            attempts += 1
            if last.status == "passed":
                break
            if last.status == "timeout":
                break
        assert last is not None
        return {"status": last.status, "code": code, "exit_code": last.exit_code, "stdout": last.stdout, "stderr": last.stderr, "attempts": attempts}
