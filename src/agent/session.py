"""交互式命令行会话 —— 用户与 agent 持续对话，不退出。

启动 `python src/main.py`（无参数）进入本会话：
  - 输入需求 → 澄清（agent 逐轮问清）→ 写 spec.md
  - 输入"编码" → 自主编码执行（按模块，可 Ctrl-C 中断）
  - /help /spec /exit 等斜杠命令
会话持续直到用户退出（/exit、exit、q、Ctrl-C 或输入流结束）。
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from agent import interactive
from agent.context import ensure_spec, spec_exists
from agent.loop import run_interactive
from agent.paths import PROJECT_ROOT
from agent.prompts import CLARIFY_SYSTEM_PROMPT, CODE_SYSTEM_PROMPT

console = Console()

# 编码意图触发词（精确匹配，避免长需求描述被误判为编码意图）
CODE_TRIGGERS: frozenset[str] = frozenset({
    "编码", "开始编码", "实现", "开始实现", "开工", "开始", "写代码", "code", "build",
})

# 退出词
EXIT_WORDS: frozenset[str] = frozenset({"exit", "quit", "q", "退出"})

# 会话内单轮最大工具调用步数。
# 澄清阶段"多问问清楚"：每个 ask_user 消耗一步，问 5-8 个问题 + 写 spec 需要余量；
# 编码阶段分模块实现同样需要较多步数。
SESSION_MAX_STEPS: int = 30


def is_code_intent(line: str) -> bool:
    """用户输入是否为"开始编码"意图。

    去掉首尾空白与句尾标点后，与触发词做精确匹配——避免"帮我实现一个游戏"
    这类长描述被误判为编码意图。
    """
    text = line.strip().rstrip("。！! ")
    return text.lower() in CODE_TRIGGERS


def _print_help() -> None:
    console.print("[cyan]可用命令:[/]")
    console.print("  [bold]/help[/]    显示本帮助")
    console.print("  [bold]/spec[/]    查看当前 spec.md 内容")
    console.print("  [bold]/clear[/]   清空 output/ 和 spec.md（重新开始）")
    console.print("  [bold]/exit[/]    退出会话（或输入 exit / q / Ctrl-C）")
    console.print("")
    console.print("直接输入:")
    console.print("  [bold]<需求描述>[/]  需求澄清：agent 逐轮问清后写 spec.md")
    console.print("  [bold]编码[/]        进入编码执行（需先有 spec.md，按模块自主实现）")
    console.print("  [bold]<修改意见>[/]  已有代码后直接说修改意见（如\"把范围改成 1-1000\"），agent 会改代码")


def _handle_command(line: str) -> str:
    """处理斜杠命令，返回 "exit" 或 "continue"。"""
    cmd = line.lower()
    if cmd in ("/exit", "/quit", "/bye"):
        return "exit"
    if cmd == "/help":
        _print_help()
    elif cmd == "/clear":
        _clear_outputs()
    elif cmd == "/spec":
        if spec_exists():
            console.print(Panel(ensure_spec(), title="spec.md"))
        else:
            console.print("[yellow]还没有 spec.md —— 先输入需求澄清。[/]")
    else:
        console.print(f"[yellow]未知命令: {line}（/help 查看帮助）[/]")
    return "continue"


def run_clarify(requirement: str, safety_mode: str, stream: bool) -> None:
    """需求澄清：agent 逐轮问清后写 spec.md。"""
    console.print("[bold green]需求澄清...[/]")
    result = run_interactive(
        CLARIFY_SYSTEM_PROMPT,
        requirement,
        retry=False,
        max_steps=SESSION_MAX_STEPS,
        bash_safety_mode=safety_mode,
        stream=stream,
    )
    if not interactive.is_terminal(result):
        console.print(result, markup=False)
    if spec_exists():
        console.print("\n[bold green]spec.md 已写入。输入 [cyan]编码[/] 开始实现，或继续描述需求。[/]")
    else:
        console.print(f"\n[yellow]未生成 spec.md：{result}[/]", markup=False)


def run_code(instruction: str, safety_mode: str, stream: bool) -> None:
    """编码执行：按 spec.md 自主实现，可 Ctrl-C 中断。"""
    if not spec_exists():
        console.print("[yellow]还没有 spec.md —— 先输入需求澄清。[/]")
        return
    spec = ensure_spec()
    task = f"{instruction}\n\n===== spec.md 项目级上下文 =====\n{spec}"
    console.print("[bold green]编码执行...[/]")
    result = run_interactive(
        CODE_SYSTEM_PROMPT,
        task,
        retry=True,
        max_steps=SESSION_MAX_STEPS,
        bash_safety_mode=safety_mode,
        stream=stream,
    )
    console.print("\n[bold green]本轮编码结束。输入修改意见/新需求继续，/exit 退出。[/]")


# ============================================================
# 修改反馈（已有代码后）
# ============================================================


def _generated_code_files() -> list[Path]:
    """output/ 目录下已生成的 .py 文件（按修改时间倒序）。"""
    out = PROJECT_ROOT / "output"
    if not out.is_dir():
        return []
    return sorted(out.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)


def has_generated_code() -> bool:
    """是否已有 agent 生成的代码（output/ 下存在 .py）。"""
    return bool(_generated_code_files())


def run_modify(instruction: str, safety_mode: str, stream: bool) -> None:
    """根据用户反馈修改现有代码：读 output/ 下代码，用 edit 修改，验证。"""
    files = _generated_code_files()
    if not files:
        console.print("[yellow]还没有已生成的代码 —— 先输入需求澄清 + 编码。[/]")
        return
    file_list = "\n".join(f"  - {f.name}" for f in files)
    spec_ctx = f"\n\n===== spec.md 项目级上下文 =====\n{ensure_spec()}" if spec_exists() else ""
    task = (
        f"用户输入：{instruction}\n\n"
        f"output/ 目录下已有的代码文件：\n{file_list}\n"
        f"请判断用户意图并处理：\n"
        f"  - 如果是【修改代码】的请求 → 先 read 读取相关文件，理解现状后用 edit 精准修改，"
        f"修改后运行验证，最后报告改了什么、如何验证。\n"
        f"  - 如果是【对现有代码的提问/解释请求】→ 直接 read 相关文件并回答，回复以 [DONE] 开头。\n"
        f"  - 不要创建新文件覆盖现有实现，除非确实需要。\n"
        f"{spec_ctx}"
    )
    console.print("[bold green]修改代码...[/]")
    result = run_interactive(
        CODE_SYSTEM_PROMPT,
        task,
        retry=True,
        max_steps=SESSION_MAX_STEPS,
        bash_safety_mode=safety_mode,
        stream=stream,
    )
    console.print("\n[bold green]修改完成。继续反馈/指令，/exit 退出。[/]")


def _clear_outputs() -> None:
    """清空 output/ 与 spec.md，重新开始（需确认）。"""
    try:
        confirm = interactive.prompt_human("确认清空 output/ 和 spec.md，重新开始？[y/N] > ")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]已取消。[/]")
        return
    if confirm.lower() != "y":
        console.print("[yellow]已取消。[/]")
        return
    import shutil
    out = PROJECT_ROOT / "output"
    if out.is_dir():
        shutil.rmtree(out)
    spec = PROJECT_ROOT / "spec.md"
    if spec.is_file():
        spec.unlink()
    console.print("[yellow]已清空 output/ 和 spec.md，可以开始新需求。[/]")


def run_interactive_session(safety_mode: str = "auto", stream: bool = True) -> None:
    """交互会话主循环：持续对话直到用户退出。"""
    interactive.ENABLED = True  # 会话模式始终允许 agent 追问
    console.print("[cyan]wz-agent 交互会话。输入需求开始；/help 查看命令；/exit 或 Ctrl-C 退出。[/]")
    _print_help()

    while True:
        try:
            prompt = "\n> " if spec_exists() else "\n需求 > "
            line = interactive.prompt_human(prompt)
        except (KeyboardInterrupt, EOFError):
            # 会话空闲（等输入）时 Ctrl-C 或输入流结束 → 退出
            console.print("\n[yellow]再见。[/]")
            break

        line = line.strip()
        if not line:
            continue
        if line.lower() in EXIT_WORDS:
            console.print("[cyan]再见。[/]")
            break

        if line.startswith("/"):
            if _handle_command(line) == "exit":
                console.print("[cyan]再见。[/]")
                break
            continue

        if is_code_intent(line) and spec_exists():
            run_code(line, safety_mode, stream)
        elif has_generated_code():
            run_modify(line, safety_mode, stream)
        else:
            run_clarify(line, safety_mode, stream)
