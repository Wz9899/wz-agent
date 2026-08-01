"""wz-agent 入口脚本。

用法:
    # 阶段一：需求澄清（默认）
    python src/main.py "帮我写一个猜人游戏"
    python src/main.py "帮我写一个猜人游戏" --safety-mode plan

    # 阶段二：编码执行（需要先有 spec.md）
    python src/main.py --phase code "请根据 spec.md 实现项目"

    # 阶段三：issue 分诊（triage 状态机）
    python src/main.py triage <feature-slug 或 issue 文件路径>

    # 阶段四：任务拆解（spec → 垂直切片 tickets）
    python src/main.py to-tickets <feature-slug 或 spec 文件路径>
"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# 把 src 加入路径（支持从项目根目录运行）
# 同时把工作目录锚定到项目根 —— 所有相对路径（工具 write/read、spec.md、
# .scratch/）都以项目根为基准，从任何目录启动行为一致。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
os.chdir(PROJECT_ROOT)

from agent import issues
from agent.context import ensure_spec, spec_exists
from agent.loop import run, run_with_retry
from agent.prompts import (
    CLARIFY_SYSTEM_PROMPT,
    CODE_SYSTEM_PROMPT,
    TRIAGE_SYSTEM_PROMPT,
    TO_TICKETS_SYSTEM_PROMPT,
)

load_dotenv()
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
# v2.0 子命令：triage
# ============================================================


def _run_triage(target: str, safety_mode: str) -> None:
    """分诊一个 feature（全部 issues）或单个 issue 文件。"""
    feature, issue_ref = issues.resolve_issue_target(target)

    # spec 校验之后才需要 LLM —— 目标解析错误优先于缺 key 提示
    if not _check_api_key():
        raise SystemExit(1)

    if issue_ref:
        # 定位到具体 issue：读取当前状态注入任务描述
        path = issues.issue_path(feature, issue_ref)
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

    with console.status(f"[bold green]Agent 分诊中... ({feature})"):
        result = run_with_retry(
            TRIAGE_SYSTEM_PROMPT,
            task,
            bash_safety_mode=safety_mode,
        )
    console.print(Panel(result, title="wz-agent triage 结果"))


# ============================================================
# v2.0 子命令：to-tickets
# ============================================================


def _run_to_tickets(target: str, safety_mode: str) -> None:
    """把 spec 拆成垂直切片 tickets。"""
    try:
        feature, spec_file = issues.resolve_spec_target(target)
    except FileNotFoundError as e:
        console.print(Panel.fit(f"[bold red]{e}[/]", title="wz-agent to-tickets"))
        raise SystemExit(1)

    # spec 校验之后才需要 LLM —— 目标解析错误优先于缺 key 提示
    if not _check_api_key():
        raise SystemExit(1)

    spec_content = spec_file.read_text(encoding="utf-8")
    task = (
        f"请把以下 spec 拆解成垂直切片 tickets，写入 "
        f".scratch/{feature}/issues/ 目录。\n"
        "先 list_issues 确认该目录现状，再逐个 allocate_issue + write。\n\n"
        f"===== spec（{spec_file}） =====\n{spec_content}"
    )

    with console.status(f"[bold green]Agent 拆解任务中... ({feature})"):
        result = run_with_retry(
            TO_TICKETS_SYSTEM_PROMPT,
            task,
            bash_safety_mode=safety_mode,
        )
    console.print(Panel(result, title="wz-agent to-tickets 结果"))


# ============================================================
# 入口
# ============================================================


@click.command()
@click.argument("args", nargs=-1, required=False)
@click.option(
    "-s", "--safety-mode",
    type=click.Choice(["auto", "plan"]),
    default="auto",
    show_default=True,
    help="Bash 安全模式: auto=直接执行, plan=先收集命令后批量执行",
)
@click.option(
    "-p", "--phase",
    type=click.Choice(["clarify", "code"]),
    default="clarify",
    show_default=True,
    help="执行阶段: clarify=需求澄清, code=编码执行",
)
def main(args: tuple[str, ...], safety_mode: str, phase: str) -> None:
    """wz-agent — 通用编码助手：主动追问需求，自动生成代码。"""

    args = list(args)

    # ---- 0. v2.0 子命令分发（triage / to-tickets）----
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
            _run_triage(target, safety_mode)
        else:
            _run_to_tickets(target, safety_mode)
        return

    # ---- 1. 参数校验：缺少任务描述时打印用法 ----
    task = " ".join(args).strip() if args else None
    if not task:
        console.print(
            Panel.fit(
                "[bold red]用法:[/] python src/main.py [cyan]\"任务描述\"[/]"
                " [--phase code] [--safety-mode plan]\n"
                "v2.0: python src/main.py [cyan]triage|to-tickets[/]"
                " [cyan]<feature-slug 或文件路径>[/]",
                title="wz-agent v2.0",
            )
        )
        raise SystemExit(1)

    # ---- 2. 校验编码阶段的前置条件（spec.md 必须存在）----
    # 不依赖 API Key，优先检查 —— spec 缺失是比缺 key 更根本的问题
    if phase == "code" and not spec_exists():
        console.print(
            Panel.fit(
                "[bold red]缺少 spec.md[/]\n\n"
                "编码执行阶段需要 spec.md 作为唯一输入。\n"
                "请先运行需求澄清阶段：\n"
                '[cyan]python src/main.py "你的需求"[/]\n\n'
                "确认 spec.md 内容无误后，再运行：\n"
                '[cyan]python src/main.py --phase code "请根据 spec.md 实现项目"[/]',
                title="wz-agent v2.0",
            )
        )
        raise SystemExit(1)

    # ---- 3. 校验 API Key ----
    if not _check_api_key():
        raise SystemExit(1)

    # ---- 4. 选择阶段对应的系统 prompt ----
    if phase == "clarify":
        system_prompt = CLARIFY_SYSTEM_PROMPT
        phase_label = "需求澄清"
    else:
        system_prompt = CODE_SYSTEM_PROMPT
        phase_label = "编码执行"

    # ---- 5. 运行 ReAct 循环（带 rich 状态指示）----
    # 编码阶段：启用自动修复重试 + 自动注入 spec.md 项目级上下文
    mode_label = "[auto]" if safety_mode == "auto" else "[plan]"
    with console.status(
        f"[bold green]Agent 思考中... ({phase_label}, bash: {mode_label})"
    ):
        if phase == "code":
            spec = ensure_spec()
            task_with_context = (
                f"{task}\n\n===== spec.md 项目级上下文 =====\n{spec}"
            )
            result = run_with_retry(
                system_prompt,
                task_with_context,
                bash_safety_mode=safety_mode,
            )
        else:
            result = run(system_prompt, task, bash_safety_mode=safety_mode)

    # ---- 6. 输出最终结果 ----
    console.print(Panel(result, title="wz-agent 回复"))


if __name__ == "__main__":
    main()
