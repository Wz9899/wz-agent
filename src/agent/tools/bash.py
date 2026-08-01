"""bash 工具 —— 执行 Shell 命令，支持 auto/plan 双模式。"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from agent.tools.base import BaseTool

# ============================================================
# 计划模式数据结构
# ============================================================


@dataclass
class PlannedCommand:
    """一条已记录但尚未执行的命令。"""

    index: int          # 序号（从 1 开始）
    command: str        # 命令文本
    reason: str = ""    # 可选的理由说明（agent 调用时可传入）


class BashTool(BaseTool):
    """执行 Shell 命令并返回输出。

    两种安全模式：
        - auto: 直接执行命令（默认，适合低风险操作）。
        - plan: 收集命令到执行计划，调用 execute_plan 时批量执行。

    安全约束:
        - 所有命令有 30 秒超时限制。
        - 危险命令模式会被拒绝（如 rm -rf /）。
        - 超时后进程会被强制终止。
    """

    # --------------------------------------------------------
    # 类常量
    # --------------------------------------------------------

    TIMEOUT: int = 30

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

    # --------------------------------------------------------
    # 实例状态
    # --------------------------------------------------------

    def __init__(self) -> None:
        self._mode: str = "auto"
        self._plan: list[PlannedCommand] = []

    @property
    def mode(self) -> str:
        """当前安全模式：'auto' 或 'plan'。"""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        if value not in ("auto", "plan"):
            raise ValueError(f"无效的安全模式 '{value}'，必须是 'auto' 或 'plan'")
        # 切换模式时清空当前计划
        if value != self._mode:
            self._plan.clear()
        self._mode = value

    @property
    def plan(self) -> list[PlannedCommand]:
        """当前计划中的命令列表（只读副本）。"""
        return list(self._plan)

    # --------------------------------------------------------
    # 工具元信息
    # --------------------------------------------------------

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        base = (
            "执行 shell 命令，返回 stdout 和 stderr 输出。"
            "适用于：安装依赖 (pip install)、运行脚本、执行测试、"
            "查看目录结构 (ls / tree) 等。"
            "安全：危险系统命令会被拒绝，所有命令有 30 秒超时限制。"
        )
        if self._mode == "plan":
            return (
                base
                + "\n\n[WARN] 当前处于【计划模式】："
                "调用本工具时命令不会立即执行，而是收集到执行计划中。"
                "当所有命令收集完成后，应调用 command='__execute_plan__' 一次性批量执行。"
                "也可以调用 command='__show_plan__' 查看当前计划、"
                "command='__clear_plan__' 清空计划。"
            )
        return base

    # --------------------------------------------------------
    # 核心方法
    # --------------------------------------------------------

    def run(self, command: str, reason: str = "") -> str:
        """根据当前模式处理命令。

        参数:
            command: 要执行的 shell 命令字符串。
                     在 plan 模式下，可用特殊命令：
                       __show_plan__   — 查看计划
                       __execute_plan__ — 执行全部命令
                       __clear_plan__  — 清空计划
            reason: 命令用途说明（仅在 plan 模式下有意义）。
        """
        if self._mode == "plan":
            return self._handle_plan(command, reason)
        return self._execute(command)

    # --------------------------------------------------------
    # 内部：计划模式
    # --------------------------------------------------------

    def _handle_plan(self, command: str, reason: str) -> str:
        """处理计划模式下的命令（记录/查看/执行/清空）。"""
        cmd = command.strip()

        # ---- 特殊命令：查看计划 ----
        if cmd == "__show_plan__":
            return self._format_plan()

        # ---- 特殊命令：执行计划 ----
        if cmd == "__execute_plan__":
            return self._execute_plan()

        # ---- 特殊命令：清空计划 ----
        if cmd == "__clear_plan__":
            return self._clear_plan()

        # ---- 普通命令：记录到计划 ----
        idx = len(self._plan) + 1
        self._plan.append(PlannedCommand(index=idx, command=cmd, reason=reason))

        reason_str = f" —— {reason}" if reason else ""
        return f"[PLAN] 已记录到执行计划 [#{idx}]: `{cmd}`{reason_str}"

    def _format_plan(self) -> str:
        """格式化输出当前计划。"""
        if not self._plan:
            return "[PLAN] 当前执行计划为空。"

        lines = [f"[PLAN] 执行计划（共 {len(self._plan)} 条命令）:"]
        for item in self._plan:
            reason_str = f"  # {item.reason}" if item.reason else ""
            lines.append(f"  [{item.index}] `{item.command}`{reason_str}")
        return "\n".join(lines)

    def _execute_plan(self) -> str:
        """批量执行计划中的所有命令，返回每条命令的结果。"""
        if not self._plan:
            return "[PLAN] 执行计划为空，没有命令需要执行。"

        results: list[str] = [f"[EXEC] 开始执行计划（共 {len(self._plan)} 条命令）...\n"]
        success_count = 0
        fail_count = 0

        for item in self._plan:
            results.append(f"── [{item.index}/{len(self._plan)}] `{item.command}` ──")

            # 对计划中的每条命令做安全检查
            blocked_reason = self._check_dangerous(item.command)
            if blocked_reason:
                results.append(f"[ERR] 安全拦截：{blocked_reason}\n")
                fail_count += 1
                continue

            output = self._execute_one(item.command)
            results.append(output)
            results.append("")

            if output.startswith("[ERR]"):
                fail_count += 1
            else:
                success_count += 1

        # 汇总
        results.append(
            f"[DONE] 计划执行完毕：{success_count} 成功, {fail_count} 失败（共 {len(self._plan)} 条）"
        )

        # 执行后清空计划
        self._plan.clear()

        return "\n".join(results)

    def _clear_plan(self) -> str:
        """清空计划。"""
        count = len(self._plan)
        self._plan.clear()
        return f"[CLEAR] 已清空执行计划（原 {count} 条命令）。"

    # --------------------------------------------------------
    # 内部：命令执行
    # --------------------------------------------------------

    def _check_dangerous(self, command: str) -> str | None:
        """检查命令是否包含危险模式，返回拦截原因或 None。"""
        stripped = command.strip()
        for dangerous in self._DANGEROUS_PREFIXES:
            if dangerous in stripped:
                return f"拒绝执行危险命令 —— 命令包含 '{dangerous}'"
        return None

    def _execute(self, command: str) -> str:
        """直接执行一条命令（auto 模式入口）。"""
        # 安全检查
        blocked_reason = self._check_dangerous(command)
        if blocked_reason:
            return f"[ERR] 安全拦截：{blocked_reason}"

        return self._execute_one(command)

    def _execute_one(self, command: str) -> str:
        """执行单条命令（所有模式共用，不做安全检查）。

        因为 _execute 和 _execute_plan 各自在调用前做了安全检查，
        所以这里只负责执行和超时/错误处理。
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                errors="replace",   # 非法字节替换为 �，避免读取线程解码崩溃导致流为 None
                timeout=self.TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return (
                f"[ERR] 超时（>{self.TIMEOUT}s）：已被强制终止。"
                f"\n提示：如果命令需要更长时间，请考虑拆分或优化。"
            )
        except FileNotFoundError:
            first_word = command.strip().split()[0] if command.strip() else command
            return f"[ERR] 命令未找到：'{first_word}'"
        except Exception as e:
            return f"[ERR] 执行出错：{e}"

        # 拼接 stdout 和 stderr（None 防御：极端情况下子进程流可能为 None）
        output_parts: list[str] = []

        stdout_text = (result.stdout or "").strip()
        stderr_text = (result.stderr or "").strip()

        if stdout_text:
            output_parts.append((result.stdout or "").rstrip())

        if stderr_text:
            output_parts.append(f"[stderr]\n{(result.stderr or '').rstrip()}")

        if not output_parts:
            return "（命令执行完毕，无输出）"

        return "\n".join(output_parts)
