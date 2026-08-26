"""交互式命令行会话 —— 单循环 REPL。

v2.2 重构：旧版是"关键词意图分类器 → 5 个阶段函数 → 各自新建
messages[]"的三层会话结构（REPL、阶段函数、loop 对话循环层层嵌套，
两层在等用户输入且互相不知情）。新版只有一层 REPL：

    一份基座提示（prompts/base.py）
  + 一份跨轮持久的 messages[]
  + 每轮调 loop.continue_turn

澄清、编码、修改、问答在同一个对话里由模型自行路由；本模块只负责
读输入、斜杠命令（确定性出口）、转录、调循环。意图分类器（约 150 行
关键词匹配）已整体删除——那是替模型做的判断，软路由（prompt）错判
还能 ask_user 找回来，硬路由（if-else）错判直接丢功能。

所有产物（spec、代码）与 agent 流式输出转录集中在本次运行的独立目录
runs/<时间戳>/（见 agent.runtime）——运行结束后可打开 session.log 回看。
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from agent import interactive, paths, runtime
from agent.context import ensure_spec, spec_exists
from agent.loop import continue_turn
from agent.prompts.base import build_system_prompt

console = Console()

# 会话内单轮最大工具调用步数（澄清问答 + 编码分模块都需余量）
SESSION_MAX_STEPS: int = 30

# 退出词 —— REPL 层的确定性出口，不交给模型路由
_EXIT_WORDS = frozenset({"exit", "quit", "q", "退出"})

# /code 命令的提示词译文：把用户显式意图翻译成对话输入，而非路由分支
_CODE_COMMAND_INPUT = (
    "（用户命令 /code）请按 spec.md 开始编码实现。"
    "若 PROGRESS.md 已存在，先 read 它接上进度再继续；"
    "项目里已有代码时先 read 现状，增量开发。"
)


def _progress_path() -> Path:
    """进度文档路径 —— 目标项目根 PROGRESS.md（项目快照，随项目走）。"""
    return paths.target_root() / "PROGRESS.md"


def _print_help() -> None:
    console.print("[cyan]可用命令:[/]")
    console.print("  [bold]/help[/]   显示本帮助")
    console.print("  [bold]/spec[/]     查看当前 spec.md 内容")
    console.print("  [bold]/progress[/] 查看进度文档 PROGRESS.md")
    console.print("  [bold]/code[/]   开始编码执行（按 spec.md 实现）")
    console.print("  [bold]/clear[/]  删除 spec.md 并重置对话（项目文件不动；代码回滚自己用 git）")
    console.print("  [bold]/exit[/]   退出会话（或输入 exit / q / Ctrl-C）")
    console.print("")
    console.print("直接输入:")
    console.print("  [bold]<需求描述>[/]  需求澄清：agent 逐轮问清后写 spec.md")
    console.print("  [bold]<修改意见>[/]  已有代码后直接说，agent 会精准修改并同步 PROGRESS.md")
    console.print("  [bold]<提问>[/]      直接回答，不写文件")


def _clear_session() -> None:
    """删除 spec.md 并重置对话（需确认）。

    项目里的代码文件与 PROGRESS.md **绝不动**——那是用户用自己的 git
    管理的事；本命令只重置 wz-agent 自己的状态（spec + 对话历史）。
    """
    try:
        confirm = interactive.prompt_human(
            "删除 spec.md 并重置对话历史？项目文件不会动 [y/N] > "
        )
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]已取消。[/]")
        return
    if confirm.lower() != "y":
        console.print("[yellow]已取消。[/]")
        return
    spec = runtime.spec_path()
    if spec.is_file():
        spec.unlink()
    console.print(
        "[yellow]已删除 spec.md（如有）并重置对话。项目文件未动——"
        "代码回滚请用自己的 git。[/]"
    )


def _seed_message() -> str:
    """目标项目已有 spec.md / PROGRESS.md 时的现状播种消息（只告知，不跑模型）。"""
    notes: list[str] = []
    if spec_exists():
        notes.append(
            f"（会话恢复）目标项目根已存在 spec.md（{runtime.spec_path()}），"
            f"请先 read 它了解需求。"
        )
    progress = _progress_path()
    if progress.is_file():
        notes.append(
            "目标项目根已存在 PROGRESS.md"
            f"（{progress}）——请先 read 它接上上次的进度，"
            "不要重复已完成的工作。"
        )
    if not notes:
        return ""
    notes.append("项目现状自行用 read/ls 探索后再动手。")
    return "".join(notes)


def run_interactive_session(
    safety_mode: str = "auto",
    stream: bool = True,
    run_dir: Path | None = None,
    seed: str | None = None,
) -> None:
    """单循环 REPL：一份持久 messages[]，每轮调 loop.continue_turn。

    参数:
        safety_mode: Bash 安全模式 —— 'auto' 或 'plan'。
        stream:      是否流式输出（实时打印思考与工具调用）。
        run_dir:     可选，复用指定转录目录（调试时沿用之前的 session.log）。
        seed:        可选，初始用户输入（命令行任务参数播种进会话，
                     相当于 pi 的"带任务启动会话"）。
    """
    interactive.ENABLED = True  # 会话模式始终允许 agent 追问 / Ctrl-C 菜单
    run_dir_path = runtime.start_run(run_dir)
    console.print(f"[cyan]本次运行目录: {run_dir_path}（产物与 session.log 都在这里）[/]")
    console.print("[cyan]wz-agent 交互会话。输入需求开始；/help 查看命令；/exit 或 Ctrl-C 退出。[/]")
    _print_help()

    # 唯一的会话状态：system = 基座提示 + 运行环境路径；历史跨轮持久
    messages: list[dict] = [{"role": "system", "content": build_system_prompt()}]
    seed_note = _seed_message()
    if seed_note:
        messages.append({"role": "user", "content": seed_note})

    def _turn(line: str) -> None:
        """跑一轮：转录 → continue_turn → 哨兵收尾提示。"""
        runtime.write_transcript(f"用户输入: {line}\n")
        result = continue_turn(
            messages,
            line,
            bash_safety_mode=safety_mode,
            max_steps=SESSION_MAX_STEPS,
            stream=stream,
        )
        runtime.write_transcript(f"\n[本轮结束] {result[:200]}\n")
        if not stream:
            console.print(result, markup=False)
        elif result.startswith(("[ERR]", "[WARN]", "[API-ERR]", "[ABORT]")):
            # 流式下正常回复已实时显示；这里只给错误/中断一句收尾提示
            console.print(f"\n[yellow]{result.splitlines()[0]}[/]", markup=False)

    # 播种输入（命令行任务参数）：直接作为第一轮
    if seed:
        _turn(seed)

    while True:
        try:
            line = interactive.prompt_human("\n> ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]再见。[/]")
            break

        line = line.strip()
        if not line:
            continue

        # ---- 确定性出口：退出词与斜杠命令不进模型 ----
        if line.lower() in _EXIT_WORDS:
            console.print("[cyan]再见。[/]")
            break

        if line.startswith("/"):
            cmd = line.lower()
            if cmd in ("/exit", "/quit", "/bye"):
                console.print("[cyan]再见。[/]")
                break
            if cmd == "/help":
                _print_help()
            elif cmd == "/clear":
                _clear_session()
                # 清空后重置对话：spec 已不存在，历史里的旧讨论会误导模型。
                # PROGRESS.md 保留 —— 进度是项目工件，与代码同生死，不随对话重置
                messages[:] = [messages[0]]
                console.print("[yellow]已重置对话历史。[/]")
            elif cmd == "/spec":
                if spec_exists():
                    console.print(Panel(ensure_spec(), title="spec.md"))
                else:
                    console.print("[yellow]还没有 spec.md —— 先输入需求。[/]")
            elif cmd == "/progress":
                progress = _progress_path()
                if progress.is_file():
                    console.print(Panel(progress.read_text(encoding="utf-8"), title="PROGRESS.md"))
                else:
                    console.print("[yellow]还没有 PROGRESS.md —— 编码时 agent 会创建并维护它。[/]")
            elif cmd == "/code":
                _turn(_CODE_COMMAND_INPUT)
            else:
                console.print(f"[yellow]未知命令: {line}（/help 查看帮助）[/]")
            continue

        # ---- 其他一切输入：交给模型路由 ----
        _turn(line)
