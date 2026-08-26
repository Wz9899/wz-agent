"""wz-agent 入口脚本。

用法:
    # 目标项目 = 启动时所在目录（或 -C 显式指定）
    python src/main.py                     # 交互会话（单循环 REPL）
    python src/main.py -C ../my-project    # 锚定目标项目后进会话
    python src/main.py "帮我写一个猜人游戏"    # 带任务播种进会话

    # issue 分诊 / 任务拆解（同样是目标项目上的 headless 流程）
    python src/main.py triage <feature-slug 或 issue 文件路径>
    python src/main.py to-tickets <feature-slug 或 spec 文件路径>

    # headless 一次性执行（不进 REPL）
    python src/main.py "帮我写一个猜人游戏" --no-interactive
"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# 启动时的工作目录 —— 未指定 -C 时作为默认目标项目（必须在任何 chdir 之前捕获）
LAUNCH_CWD: Path = Path.cwd()

# wz-agent 自身根：sys.path 与 .env 的定位基准。
# 注意：v2.3 起不再 chdir 到这里 —— 目标项目在 main() 里通过 paths.set_target 锚定，
# 工具（read/write/edit/bash）的相对路径全部随目标项目走。
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from agent import interactive, issues, paths, runtime
from agent.loop import run_with_retry
from agent.session import run_interactive_session
from agent.prompts import (
    TRIAGE_SYSTEM_PROMPT,
    TO_TICKETS_SYSTEM_PROMPT,
    build_system_prompt,
)

load_dotenv(PROJECT_ROOT / ".env")  # .env 固定在 wz-agent 根（与 cwd 无关）
console = Console()

# v2.0 子命令保留字（出现在第一个位置参数时走对应流程）
SUBCOMMANDS: tuple[str, ...] = ("triage", "to-tickets")


def _check_api_key() -> bool:
    """校验 DEEPSEEK_API_KEY，缺失时打印提示并返回 False。"""
    if os.environ.get("DEEPSEEK_API_KEY"):
        return True
    console.print("[red]错误：未设置 DEEPSEEK_API_KEY[/]")
    console.print('PowerShell: [cyan]$env:DEEPSEEK_API_KEY="sk-你的key"[/]')
    console.print('Bash:       [cyan]export DEEPSEEK_API_KEY="sk-你的key"[/]')
    return False


# ============================================================
# v2.0 子命令
# ============================================================


def _run_agent(
    title: str,
    system_prompt: str,
    task: str,
    safety_mode: str,
    stream: bool,
) -> None:
    """校验 API key、跑带重试的 ReAct 循环、输出结果。

    _run_triage / _run_to_tickets 共享的控制流：目标解析各自做，解析成功
    后才到这里 —— 目标解析错误优先于缺 key 提示。

    stream=True 时：agent 的思考与工具调用过程实时打印到控制台，结束只给
    简短提示（结果已逐字显示，不再重复输出 Panel）。
    stream=False 时：保留 status spinner + 结果 Panel 的旧行为。
    """
    # triage / to-tickets 是自动化流程：强制非交互，避免 LLM 误调 ask_user 阻塞
    interactive.ENABLED = False
    run_dir = runtime.start_run()
    console.print(f"[cyan]本次运行目录: {run_dir}[/]")

    if not _check_api_key():
        raise SystemExit(1)

    if stream:
        console.print(f"[bold green]{title}[/]")
        result = run_with_retry(
            system_prompt,
            task,
            bash_safety_mode=safety_mode,
            stream=True,
        )
        console.print("\n[bold green]完成[/]")
    else:
        with console.status(f"[bold green]{title}"):
            result = run_with_retry(
                system_prompt,
                task,
                bash_safety_mode=safety_mode,
            )
        console.print(Panel(result, title="wz-agent 结果"))


def _run_triage(target: str, safety_mode: str, stream: bool) -> None:
    """分诊一个 feature（全部 issues）或单个 issue 文件。"""
    feature, issue_ref = issues.resolve_issue_target(target)

    if issue_ref:
        # 定位到具体 issue：读取当前状态注入任务描述
        try:
            path = issues.issue_path(feature, issue_ref)
        except ValueError as e:
            # issue 引用存在歧义（命中多个文件）—— 拒绝静默选一个
            console.print(Panel.fit(f"[bold red]{e}[/]", title="wz-agent triage"))
            raise SystemExit(1)
        status = issues.get_status(path) if path else None
        task = (
            f"请分诊 feature '{feature}' 下的 issue '{issue_ref}'。\n"
            f"当前状态: {status or '（无 Status 行）'}\n"
            f"文件: .scratch/{feature}/issues/{path.name if path else issue_ref}.md\n"
            f"用 read 读取内容后分析并更新状态。"
        )
    else:
        task = (
            f"请分诊 feature '{feature}' 下的所有 issue。\n"
            "先用 list_issues 查看全貌，再逐个处理。"
        )

    _run_agent(f"Agent 分诊中... ({feature})", TRIAGE_SYSTEM_PROMPT, task, safety_mode, stream)


def _run_to_tickets(target: str, safety_mode: str, stream: bool) -> None:
    """把 spec 拆成垂直切片 tickets。"""
    try:
        feature, spec_file = issues.resolve_spec_target(target)
    except FileNotFoundError as e:
        console.print(Panel.fit(f"[bold red]{e}[/]", title="wz-agent to-tickets"))
        raise SystemExit(1)

    spec_content = spec_file.read_text(encoding="utf-8")
    task = (
        f"请把以下 spec 拆解成垂直切片 tickets，写入 "
        f".scratch/{feature}/issues/ 目录。\n"
        "先 list_issues 确认该目录现状，再逐个 allocate_issue + write。\n\n"
        f"===== spec（{spec_file}） =====\n{spec_content}"
    )

    _run_agent(f"Agent 拆解任务中... ({feature})", TO_TICKETS_SYSTEM_PROMPT, task, safety_mode, stream)


# ============================================================
# 入口
# ============================================================


def is_self_harness(path: Path) -> bool:
    """目标是否落在 wz-agent 自身仓库内（含根、src/ 等任意子目录）。

    防自噬护栏：agent 没有自我模型，锚到自己源码时会把 harness 代码当
    "用户项目"探索、提议集成、甚至直接修改（实测事故：从 src/ 里裸启
    python main.py，agent 建议把新项目"接入你现有的 main.py"）。
    """
    resolved = path.resolve()
    return resolved == PROJECT_ROOT or PROJECT_ROOT in resolved.parents


@click.command()
@click.argument("args", nargs=-1, required=False)
@click.option(
    "-C", "--cd", "target",
    type=click.Path(path_type=Path, exists=True, file_okay=False),
    default=None,
    help="目标项目目录（agent 直接在其中工作；默认：启动时所在目录）",
)
@click.option(
    "-s", "--safety-mode",
    type=click.Choice(["auto", "plan"]),
    default="auto",
    show_default=True,
    help="Bash 安全模式: auto=直接执行, plan=先收集命令后批量执行",
)
@click.option(
    "--no-stream",
    is_flag=True,
    default=False,
    help="关闭流式输出（等待完整结果后一次性返回）",
)
@click.option(
    "--no-interactive",
    is_flag=True,
    default=False,
    help="关闭交互会话：带任务参数时一次性跑完（headless），不进 REPL",
)
@click.option(
    "--run",
    "run_opt",
    type=click.Path(path_type=Path),
    default=None,
    help="复用指定运行目录调试（如 runs/20260802_113114），不新建；沿用其中 spec 与代码",
)
@click.option(
    "--allow-self",
    is_flag=True,
    default=False,
    help="允许目标为 wz-agent 自身仓库（自举开发；默认拒绝防 agent 改自己源码）",
)
def main(
    args: tuple[str, ...],
    target: Path | None,
    safety_mode: str,
    no_stream: bool,
    no_interactive: bool,
    run_opt: Path | None,
    allow_self: bool,
) -> None:
    """wz-agent — 通用编码助手：主动追问需求，自动生成代码。"""

    # ---- 0. 锚定目标项目（相对路径基于启动时目录解析）----
    try:
        anchored = paths.set_target(target if target is not None else LAUNCH_CWD)
    except FileNotFoundError as e:
        console.print(Panel.fit(f"[bold red]{e}[/]", title="wz-agent"))
        raise SystemExit(1)

    # 防自噬：目标落在 wz-agent 自身仓库内 → 拒绝（自举开发用 --allow-self 显式放行）
    if is_self_harness(anchored) and not allow_self:
        console.print(Panel.fit(
            f"[bold red]目标项目是 wz-agent 自身仓库：[/]\n{anchored}\n\n"
            "agent 没有自我模型，锚在这里它会把 harness 代码当成你的项目，"
            "甚至修改自己的源码。\n\n"
            "请用 -C 指向你自己的项目目录；\n"
            "确实要用 wz-agent 开发 wz-agent（自举）时加 --allow-self。",
            title="wz-agent",
        ))
        raise SystemExit(1)

    args = list(args)
    stream = not no_stream

    # ---- 1. v2.0 子命令分发（triage / to-tickets，全自动 headless）----
    if args and args[0] in SUBCOMMANDS:
        sub = args.pop(0)
        if not args:
            console.print(
                Panel.fit(
                    f"[bold red]用法:[/] python src/main.py [cyan]{sub}[/]"
                    " [cyan]<feature-slug 或文件路径>[/]",
                    title="wz-agent v2.0",
                )
            )
            raise SystemExit(1)
        target = args[0]
        if sub == "triage":
            _run_triage(target, safety_mode, stream)
        else:
            _run_to_tickets(target, safety_mode, stream)
        return

    if not _check_api_key():
        raise SystemExit(1)

    # ---- 2. 任务参数：播种进交互会话（单循环 REPL，模型自路由）----
    task = " ".join(args).strip() if args else None
    if not no_interactive:
        console.print(f"[cyan]目标项目: {anchored}[/]")
        run_interactive_session(
            safety_mode=safety_mode, stream=stream, run_dir=run_opt, seed=task,
        )
        return

    # ---- 3. headless 一次性模式（--no-interactive + 任务参数）----
    # 脚本化场景：不进 REPL，用基座提示跑一轮带自动修复的循环到完成
    if not task:
        console.print(
            Panel.fit(
                "[bold red]--no-interactive 需要附带任务参数[/]\n\n"
                "例: python src/main.py \"帮我写一个猜人游戏\" --no-interactive",
                title="wz-agent",
            )
        )
        raise SystemExit(1)

    run_dir = runtime.start_run(run_opt)
    console.print(f"[cyan]本次运行目录: {run_dir}[/]")
    mode_label = "[auto]" if safety_mode == "auto" else "[plan]"
    mode_label_markup = mode_label.replace("[", "[[").replace("]", "]]")
    try:
        if stream:
            console.print(
                f"[bold green]Agent 思考中... (bash: {mode_label_markup})[/]"
            )
            result = run_with_retry(
                build_system_prompt(),
                task,
                bash_safety_mode=safety_mode,
                stream=True,
            )
            console.print("\n[bold green]完成[/]")
        else:
            with console.status("[bold green]Agent 思考中..."):
                result = run_with_retry(
                    build_system_prompt(),
                    task,
                    bash_safety_mode=safety_mode,
                )
            console.print(Panel(result, title="wz-agent 结果"))
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断。[/]")
        raise SystemExit(130)


if __name__ == "__main__":
    main()
