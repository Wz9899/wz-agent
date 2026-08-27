"""人机交互基础设施 —— 交互开关、编码安全的人机 I/O、Ctrl-C 中断菜单、完成判定。

交互状态（ENABLED）是模块级全局，与 loop.py 的 _client、tools 的 bash mode
采用的模式一致。ask_user / checkpoint 只读 ENABLED 决定是否退化；消息注入
与中断处理由 loop.py 直接完成——工具不持有 messages，避免循环依赖。
"""

from __future__ import annotations

import sys
from typing import Literal

from agent import runtime

# ============================================================
# 交互状态
# ============================================================

# 交互开关：True 时 ask_user 可阻塞等回答、Ctrl-C 走中断菜单；
# False 时交互工具退化，Ctrl-C 直接抛出让调用方干净退出
ENABLED: bool = True

# 对话循环的终止前缀：命中这些开头的回复 → 本轮结束
# v2.2 起为四类哨兵协议（[ERR]/[WARN] 可重试、[API-ERR]/[ABORT] 不重试）；[DONE] 协议已退役
TERMINAL_PREFIXES: tuple[str, ...] = ("[ERR]", "[WARN]", "[API-ERR]", "[ABORT]")


# ============================================================
# 编码安全的人机 I/O
# ============================================================


def print_human(text: str, *, end: str = "\n") -> None:
    """编码安全打印 + 同步写入运行转录（session.log）。

    仅把当前输出编码无法表示的字符（如 emoji、⚠）替换为 '?'。流式文本与
    工具调用展示都走这里——因此 agent 在终端的输出会自动保存为运行回放，
    运行结束后可打开 runs/<时间戳>/session.log 回看。

    Windows 控制台/重定向通常用 cp936（GBK），中文可编码但 emoji 不行——
    LLM 自由输出常带这类字符。这里避免 UnicodeEncodeError 中断 agent。
    """
    try:
        print(text, end=end, flush=True)
        runtime.write_transcript(text + end)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = text.encode(enc, errors="replace").decode(enc)
        print(safe, end=end, flush=True)
        runtime.write_transcript(safe + end)


def strip_surrogates(text: str) -> str:
    """去掉字符串中的孤立 surrogate 字符（U+D800-U+DFFF）。

    Windows 管道/重定向输入可能因编码转换引入孤立 surrogate，导致 OpenAI
    json 序列化报 "'utf-8' codec can't encode character ... surrogates not allowed"。
    """
    return "".join(ch for ch in text if not 0xD800 <= ord(ch) <= 0xDFFF)


def prompt_human(prompt: str) -> str:
    """编码安全阻塞输入，返回用户输入（去掉首尾空白、清理 surrogate）。

    - Ctrl-C：抛 KeyboardInterrupt（由上层统一处理中断菜单）
    - 输入流结束 / 非 TTY EOF：抛 EOFError（由调用方决定：
      ask_user 退化、对话循环终止、交互会话退出）
    """
    print_human(prompt, end="")
    return strip_surrogates(input().strip())


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
        except (KeyboardInterrupt, EOFError):
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
    """对话循环终止判定：空串或以哨兵协议前缀（TERMINAL_PREFIXES）任一开头。

    命中哨兵说明本轮已结束（错误需修复、基础设施故障、或用户中止）；
    普通问题文本返回 False —— 对话循环继续等用户回答。
    """
    if not result:
        return True
    return result.startswith(TERMINAL_PREFIXES)
