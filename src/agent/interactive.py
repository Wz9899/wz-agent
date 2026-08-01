"""人机交互基础设施 —— 交互开关、编码安全的人机 I/O、Ctrl-C 中断菜单、完成判定。

交互状态（ENABLED / abort_requested / pending_instruction）是模块级全局，
与 loop.py 的 _client、tools 的 bash mode 采用的模式一致。交互工具
（ask_user / checkpoint）只读写这里的 flag；真正的消息注入与中断处理
由 loop.py 消费这些 flag 完成——工具不持有 messages，避免循环依赖。
"""

from __future__ import annotations

import sys
from typing import Literal

# ============================================================
# 交互状态
# ============================================================

# 交互开关：True 时 agent 可中途停下问用户；False 时 ask_user/checkpoint 退化
ENABLED: bool = True

# checkpoint 用户输入 stop 时置位，_run_loop 消费后终止当前执行
abort_requested: bool = False

# checkpoint 用户注入的新指令，_run_loop 消费后追加为真实 user 消息
pending_instruction: str | None = None

# 对话循环的终止前缀：命中这些开头的回复 → 本轮结束
TERMINAL_PREFIXES: tuple[str, ...] = ("[DONE]", "[ERR]", "[WARN]", "[API-ERR]", "[ABORT]")


# ============================================================
# 编码安全的人机 I/O
# ============================================================


def print_human(text: str, *, end: str = "\n") -> None:
    """编码安全打印：仅把当前输出编码无法表示的字符（如 emoji、⚠）替换为 '?'。

    Windows 控制台/重定向通常用 cp936（GBK），中文可编码但 emoji 不行——
    LLM 自由输出常带这类字符。流式文本与工具调用展示都走这里，避免
    UnicodeEncodeError 中断 agent；中文得以保留。
    """
    try:
        print(text, end=end, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = text.encode(enc, errors="replace").decode(enc)
        print(safe, end=end, flush=True)


def prompt_human(prompt: str) -> str:
    """编码安全阻塞输入，返回用户输入（去掉首尾空白）。

    - Ctrl-C：抛 KeyboardInterrupt（由上层统一处理中断菜单）
    - 非 TTY / 管道 EOF：返回空字符串（交互退化，不阻塞）
    """
    print_human(prompt, end="")
    try:
        return input().strip()
    except EOFError:
        return ""


# ============================================================
# Ctrl-C 中断菜单
# ============================================================


def handle_interrupt(messages: list[dict]) -> Literal["resume", "abort", "inject"]:
    """[Ctrl-C] 统一中断处理：询问用户接下来怎么办。

    - 回车            → resume：忽略中断，重新执行
    - stop            → abort：终止当前执行
    - 其他任意输入     → inject：作为新指令追加为 user 消息，继续执行
    - 再次 Ctrl-C      → abort：直接终止

    返回动作类型；inject 时已把指令 append 到 messages。
    """
    print_human("\n[Ctrl-C] 已中断。")
    while True:
        try:
            choice = prompt_human("  [回车]=继续  [输入]=注入指令  [stop]=停止 > ")
        except KeyboardInterrupt:
            return "abort"
        if not choice:
            return "resume"
        if choice.lower() == "stop":
            return "abort"
        messages.append({"role": "user", "content": choice})
        return "inject"


# ============================================================
# 完成判定
# ============================================================


def is_terminal(result: str) -> bool:
    """对话循环终止判定：空串或以 TERMINAL_PREFIXES 任一开头。

    clarify 的完成约定：agent 写全部 spec.md 后回复以 [DONE] 开头。
    普通问题文本（非这些前缀）返回 False —— 对话循环继续等用户回答。
    """
    if not result:
        return True
    return result.startswith(TERMINAL_PREFIXES)
