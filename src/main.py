"""wz-agent 入口脚本。

用法:
    # 阶段一：需求澄清（默认）
    python src/main.py "帮我写一个猜人游戏"
    python src/main.py "帮我写一个猜人游戏" --safety-mode plan

    # 阶段二：编码执行（需要先有 spec.md）
    python src/main.py --phase code "请根据 spec.md 实现项目"
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# 把 src 加入路径（支持从项目根目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.loop import run
from agent.prompts import CLARIFY_SYSTEM_PROMPT, CODE_SYSTEM_PROMPT

load_dotenv()
console = Console()


def main():
    parser = argparse.ArgumentParser(
        description="wz-agent — 通用编码助手",
    )
    parser.add_argument(
        "task",
        nargs="?",
        help="任务描述",
    )
    parser.add_argument(
        "-s", "--safety-mode",
        choices=["auto", "plan"],
        default="auto",
        help="Bash 安全模式: auto=直接执行, plan=先收集命令后批量执行 (默认: auto)",
    )
    parser.add_argument(
        "-p", "--phase",
        choices=["clarify", "code"],
        default="clarify",
        help="执行阶段: clarify=需求澄清, code=编码执行 (默认: clarify)",
    )
    args = parser.parse_args()

    if not args.task:
        console.print(
            Panel.fit(
                "[bold red]用法:[/] python src/main.py [cyan]\"任务描述\"[/] [--phase code] [--safety-mode plan]",
                title="wz-agent v0.4"
            )
        )
        sys.exit(1)

    if not os.environ.get("DEEPSEEK_API_KEY"):
        console.print("[red]错误：未设置 DEEPSEEK_API_KEY[/]")
        console.print("PowerShell: [cyan]$env:DEEPSEEK_API_KEY=\"sk-你的key\"[/]")
        console.print("Bash:       [cyan]export DEEPSEEK_API_KEY=\"sk-你的key\"[/]")
        sys.exit(1)

    # ---- 选择阶段对应的系统 prompt ----
    if args.phase == "clarify":
        system_prompt = CLARIFY_SYSTEM_PROMPT
        phase_label = "需求澄清"
    else:
        system_prompt = CODE_SYSTEM_PROMPT
        phase_label = "编码执行"

    mode_label = "[auto]" if args.safety_mode == "auto" else "[plan]"
    with console.status(f"[bold green]Agent 思考中... ({phase_label}, bash: {mode_label})"):
        result = run(system_prompt, args.task, bash_safety_mode=args.safety_mode)

    console.print(Panel(result, title="wz-agent 回复"))


if __name__ == "__main__":
    main()
