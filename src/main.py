"""wz-agent 入口脚本。

用法:
    python src/main.py "你的任务描述"
"""

import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

# 把 src 加入路径（支持从项目根目录运行）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.loop import run

load_dotenv()
console = Console()


def main():
    if len(sys.argv) < 2:
        console.print(
            Panel.fit("[bold red]用法:[/] python src/main.py [cyan]\"任务描述\"[/]",
                      title="wz-agent v0.1"))
        sys.exit(1)

    user_input = sys.argv[1]

    if not os.environ.get("DEEPSEEK_API_KEY"):
        console.print("[red]错误：未设置 DEEPSEEK_API_KEY[/]")
        console.print("PowerShell: [cyan]$env:DEEPSEEK_API_KEY=\"sk-你的key\"[/]")
        console.print("Bash:       [cyan]export DEEPSEEK_API_KEY=\"sk-你的key\"[/]")
        sys.exit(1)

    system_prompt = "你是一个简洁的编码助手，用中文回答。"

    with console.status("[bold green]Agent 思考中..."):
        result = run(system_prompt, user_input)

    console.print(Panel(result, title="wz-agent 回复"))


if __name__ == "__main__":
    main()
