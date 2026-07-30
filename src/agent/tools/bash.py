"""bash 工具 —— 执行 Shell 命令。"""

import subprocess

from agent.tools.base import BaseTool


class BashTool(BaseTool):
    """执行 Shell 命令并返回输出。

    安全约束:
        - 所有命令有 30 秒超时限制。
        - 危险命令模式会被拒绝（如 rm -rf /）。
        - 超时后进程会被强制终止。
    """

    # 超时秒数（类常量，方便外部调整）
    TIMEOUT: int = 30

    # 危险命令黑名单（前缀匹配）
    _DANGEROUS_PREFIXES: tuple[str, ...] = (
        "rm -rf /",
        "rm -rf ~",
        "rm -rf /*",
        "dd if=",
        "mkfs.",
        ":(){ :|:& };:",
        "> /dev/sda",
        "chmod -R 777 /",
    )

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return (
            "执行一个 shell 命令，返回 stdout 和 stderr 输出。"
            "适用于：安装依赖 (pip install)、运行脚本、执行测试、"
            "查看目录结构 (ls / tree) 等。"
            "安全：危险系统命令会被拒绝，所有命令有 30 秒超时限制。"
        )

    def run(self, command: str) -> str:
        """执行命令，返回标准输出和标准错误的合并结果。

        参数:
            command: 要执行的 shell 命令字符串。
        """
        # ---- 1. 安全检查：拒绝危险命令 ----
        for dangerous in self._DANGEROUS_PREFIXES:
            if command.strip().startswith(dangerous):
                return f"❌ 安全拦截：拒绝执行危险命令 —— '{dangerous}...'"

        # ---- 2. 执行命令（带超时、捕获输出） ----
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (
                f"❌ 错误：命令执行超时（超过 {self.TIMEOUT} 秒），已被强制终止。"
                f"\n提示：如果命令需要更长时间，请考虑拆分或优化。"
            )
        except FileNotFoundError:
            return f"❌ 错误：命令或可执行文件未找到 —— '{command.split()[0] if command.strip() else command}'"
        except Exception as e:
            return f"❌ 执行命令时出错：{e}"

        # ---- 3. 拼接 stdout 和 stderr ----
        output_parts: list[str] = []

        if result.stdout.strip():
            output_parts.append(result.stdout.rstrip())

        if result.stderr.strip():
            output_parts.append(f"[stderr]\n{result.stderr.rstrip()}")

        # 无输出时给出明确提示
        if not output_parts:
            return "（命令执行完毕，无输出）"

        return "\n".join(output_parts)
