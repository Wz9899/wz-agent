"""wz-agent 入口脚本。

用法:
    # 阶段一：需求澄清（默认）
    python src/main.py "帮我写一个猜人游戏"
    python src/main.py "帮我写一个猜人游戏" --safety-mode plan

    # 阶段二：编码执行（需要先有 spec.md）
    python src/main.py --phase code "请根据 spec.md 实现项目"
"""

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# 把 src 加入路径（支持从项目根目录运行）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.context import ensure_spec, spec_exists
from agent.loop import run, run_with_retry
from agent.prompts import CLARIFY_SYSTEM_PROMPT, CODE_SYSTEM_PROMPT

load_dotenv()
console = Console()


@click.command()
@click.argument("task", required=False)
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
def main(task: str, safety_mode: str, phase: str) -> None:
    """wz-agent — 通用编码助手：主动追问需求，自动生成代码。"""

    # ---- 1. 参数校验：缺少任务描述时打印用法 ----
    if not task:
        console.print(
            Panel.fit(
                "[bold red]用法:[/] python src/main.py [cyan]\"任务描述\"[/]"
                " [--phase code] [--safety-mode plan]",
                title="wz-agent v0.4",
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
                title="wz-agent v0.4",
            )
        )
        raise SystemExit(1)

    # ---- 3. 校验 API Key ----
    if not os.environ.get("DEEPSEEK_API_KEY"):
        console.print("[red]错误：未设置 DEEPSEEK_API_KEY[/]")
        console.print('PowerShell: [cyan]$env:DEEPSEEK_API_KEY="sk-你的key"[/]')
        console.print('Bash:       [cyan]export DEEPSEEK_API_KEY="sk-你的key"[/]')
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
