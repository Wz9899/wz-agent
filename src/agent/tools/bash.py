"""bash 工具 —— 执行 Shell 命令，支持 auto/plan 双模式。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
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

    # bash 可用性探测结果缓存（模块级，进程内只探一次）
    _BASH_PATH: str | None = None
    _BASH_CHECKED: bool = False

    @classmethod
    def _bash_available(cls) -> str | None:
        """返回 bash 可执行文件路径（Windows 上通常是 git-bash），不可用返回 None。"""
        if not cls._BASH_CHECKED:
            cls._BASH_PATH = shutil.which("bash")
            cls._BASH_CHECKED = True
        return cls._BASH_PATH

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

    # 自杀式清理：按映像名全杀 python 会连 wz-agent 自己的宿主进程一起杀
    # （实测事故：agent 为清理泄漏的 Flask 跑 taskkill /IM python.exe，
    # 窗口直接消失，连 pause 都没执行到）。要清后台进程必须用 PID。
    _SELF_KILL_IM_RE = re.compile(r"taskkill\s+/im\s+python", re.IGNORECASE)

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

        # 自杀式清理（按映像名全杀）：给可行动的替代方案（杀 PID 不杀映像名）
        if self._SELF_KILL_IM_RE.search(stripped):
            return (
                "拒绝执行 taskkill /IM python —— 这会连带杀掉 wz-agent 自己。"
                "清理后台进程请用 PID：先 netstat/tasklist 找到 PID，"
                "再 taskkill /PID <pid> /F。"
            )

        # 自杀守卫（跨形态）：任何以当前进程 PID 为目标的 kill/taskkill 都拦。
        # 形态各异（kill /PID n、taskkill /pid n、powershell Stop-Process -Id n），
        # 用当前 PID 是否作为独立数字出现来判定。
        me = str(os.getpid())
        if re.search(r"(?<![0-9])" + me + r"(?![0-9])", stripped) and re.search(
            r"taskkill|kill|stop-process", stripped, re.IGNORECASE
        ):
            return (
                f"拒绝执行 —— 目标 PID {me} 是 wz-agent 自己的进程。"
                "如需终止后台服务，请针对该服务的 PID 操作。"
            )
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

        执行路径:
          - Windows + bash 可用: 命令写入临时脚本，用 bash 执行。
            原因: shell=True 在 Windows 下走 cmd.exe，而 LLM 生成的是
            bash 语法（POSIX 路径 /c/...、/dev/null 重定向、&& 链、单引号），
            cmd 解析不了直接报“系统找不到指定的路径”，agent 只能反复换写法烧步数。
            临时脚本法避免引号转义问题，命令内容原样到达 bash。
          - 其他情况（POSIX 或无 bash 的 Windows）: 退回 shell=True 原路径。
        """
        bash_path = self._bash_available()
        if os.name == "nt" and bash_path:
            return self._execute_via_bash(bash_path, command)
        stdout, stderr, err = self._spawn(command, shell=True)
        if err:
            return err
        return self._assemble_output(stdout, stderr)

    def _execute_via_bash(self, bash_path: str, command: str) -> str:
        """用 bash 执行命令（Windows 路径）。"""
        # newline="\n": 防止 Windows 文本模式把 \n 写成 \r\n 破坏 heredoc/行延续
        with tempfile.NamedTemporaryFile(
            "w", suffix=".sh", delete=False, encoding="utf-8", newline="\n"
        ) as script:
            script.write(command)
            script_path = script.name
        try:
            # encoding="utf-8": git-bash 工具链输出 UTF-8；按 locale（GBK）解码会乱码。
            # 混入的原生 Windows 程序 GBK 输出会被 errors=replace 替换为 �，不致崩溃。
            stdout, stderr, err = self._spawn(
                [bash_path, script_path], shell=False, encoding="utf-8"
            )
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass
        if err:
            return err
        return self._assemble_output(stdout, stderr)

    def _spawn(
        self, args, *, shell: bool, encoding: str | None = None
    ) -> tuple[str, str, str | None]:
        """启动子进程并等待完成。返回 (stdout, stderr, 错误消息)。

        错误消息非 None 表示超时/启动失败/异常，调用方直接返回给 LLM；
        正常完成时前两项为文本输出。
        """
        # Windows 上 shell=True 的 cmd 会衍生子进程，超时需能终止整棵进程树
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        popen_kwargs: dict = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",   # 非法字节替换为 �，避免读取线程解码崩溃导致流为 None
            creationflags=creationflags,
        )
        if encoding:
            popen_kwargs["encoding"] = encoding
        try:
            proc = subprocess.Popen(args, shell=shell, **popen_kwargs)
            stdout, stderr = proc.communicate(timeout=self.TIMEOUT)
        except subprocess.TimeoutExpired:
            self._kill_process_tree(proc)
            try:
                proc.communicate(timeout=5)  # 收尾，清空残留管道，防僵尸
            except Exception:
                pass
            return "", "", (
                f"[ERR] 超时（>{self.TIMEOUT}s）：已连同子进程强制终止。"
                f"\n提示：如果命令需要更长时间，请考虑拆分或优化。"
            )
        except FileNotFoundError:
            # str（shell=True）报命令首词；list（shell=False）报可执行文件本身。
            # 不能统一 join 后 split()[0]：bash 路径含空格会被切碎（如 C:\Program Files\...）。
            if isinstance(args, str):
                first_word = args.strip().split()[0] if args.strip() else args
            else:
                first_word = args[0]
            return "", "", f"[ERR] 命令未找到：'{first_word}'"
        except Exception as e:
            return "", "", f"[ERR] 执行出错：{e}"
        return stdout or "", stderr or "", None

    @staticmethod
    def _assemble_output(stdout: str, stderr: str) -> str:
        """拼接 stdout/stderr 为返回文本（None 防御：极端情况下流可能为 None）。"""
        output_parts: list[str] = []

        stdout_text = (stdout or "").strip()
        stderr_text = (stderr or "").strip()

        if stdout_text:
            output_parts.append((stdout or "").rstrip())

        if stderr_text:
            output_parts.append(f"[stderr]\n{(stderr or '').rstrip()}")

        if not output_parts:
            return "（命令执行完毕，无输出）"

        return "\n".join(output_parts)

    def _kill_process_tree(self, proc) -> None:
        """超时后强制终止整棵进程树。

        Windows 用 taskkill /T /F 按 PID 杀 cmd 及其全部子进程（如 python）；
        POSIX 用 proc.kill()（shell 子进程一般同组）。
        """
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/pid", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                )
            except Exception:
                pass
        else:
            try:
                proc.kill()
            except Exception:
                pass
