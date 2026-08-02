"""交互式命令行会话 —— 用户与 agent 持续对话，不退出。

启动 `python src/main.py`（无参数）进入本会话：
  - 输入需求 → 澄清（agent 逐轮问清）→ 写 spec.md
  - 输入"编码" → 自主编码执行（按模块，可 Ctrl-C 中断）
  - 已有代码后直接说修改意见 → agent 读代码改
  - /help /spec /clear /exit 等斜杠命令
会话持续直到用户退出。

所有产物（spec、代码）与 agent 流式输出转录集中在本次运行的独立目录
runs/<时间戳>/（见 agent.runtime）——运行结束后可打开 session.log 回看。
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from agent import interactive, runtime
from agent.context import ensure_spec, spec_exists
from agent.loop import run_interactive
from agent.prompts import CLARIFY_SYSTEM_PROMPT, CODE_SYSTEM_PROMPT, MODIFY_SYSTEM_PROMPT

console = Console()

# 编码意图触发词（精确匹配，避免长需求描述被误判为编码意图）
CODE_TRIGGERS: frozenset[str] = frozenset({
    "编码", "开始编码", "实现", "开始实现", "开工", "开始", "写代码", "code", "build",
})

# 退出词
EXIT_WORDS: frozenset[str] = frozenset({"exit", "quit", "q", "退出"})

# 表示"需求已完整、无需补充"的结束性表达（需求确认环节识别）
_DONE_PHRASES: tuple[str, ...] = (
    "没有补充", "不用补充", "不需要补充", "不用了", "不需要了", "没有了", "没了",
    "就这样", "够了", "可以了", "就这些", "暂时没有", "没有需求", "需求完整", "结束了",
)

# 会话内单轮最大工具调用步数（澄清多轮问答 + 写 spec / 编码分模块都需余量）
SESSION_MAX_STEPS: int = 30


def is_code_intent(line: str) -> bool:
    """用户输入是否为"开始编码"意图。

    两种形态都算：
    1. 精确匹配触发词（"编码"、"实现"、"code"）
    2. 短指令（≤8 字，如"开始编码吧"、"去实现"）且含触发词
    长需求描述（如"帮我实现一个游戏"）不会被误判为编码意图。
    """
    text = line.strip().rstrip("。！!吧 ")
    if text.lower() in CODE_TRIGGERS:
        return True
    if len(text) <= 8 and any(t in text for t in CODE_TRIGGERS):
        return True
    return False


def _is_done_requirements(text: str) -> bool:
    """识别"需求已完整、无需补充"的表达（需求确认环节）。

    用较长的结束性短语匹配，避免"没有做计分系统"这类补充内容被误判。
    """
    return any(p in text for p in _DONE_PHRASES)


# 疑问句特征（收紧：只有明确提问才识别，避免误把非提问当"回答"）
_QUESTION_WORDS: tuple[str, ...] = (
    "是啥", "是什么", "为啥", "为什么", "怎么", "如何", "在哪", "哪个", "哪些",
    "是否", "是不是",
)


def _is_question(text: str) -> bool:
    """识别用户输入是否为明确提问（直接回答，而非需求/指令）。

    以问号结尾、或短问句以"吗"结尾、或含强疑问词 → 视为提问。
    刻意收紧，避免"我不是每次输入都是要你回答"。
    """
    t = text.strip()
    if t.endswith(("？", "?")):
        return True
    if len(t) <= 12 and t.endswith("吗"):
        return True
    return any(w in t for w in _QUESTION_WORDS)


# 无实际内容的输入（语气词/确认词），不触发任何 agent 动作
_IGNORE_WORDS: frozenset[str] = frozenset({
    "嗯", "哦", "好", "好的", "ok", "okay", "对", "是的", "知道了", "行", "可以",
    "没问题", "收到", "继续", "嗯嗯", "好的吧", "行吧", "就这样", "嗯嗯嗯",
})


def _is_noop_input(text: str) -> bool:
    """无实际内容（语气词/确认词/过短）→ 不触发任何 agent 动作。"""
    return text.lower() in _IGNORE_WORDS or len(text) <= 1


# 明确的"项目需求"表达（含需求动作词），只有这些才触发需求澄清
_REQUIREMENT_MARKERS: tuple[str, ...] = (
    "帮我", "帮我写", "给我", "给我写", "我要", "我想要", "我想做", "要做",
    "写一个", "写个", "做一个", "做个", "开发", "创建", "设计一个", "实现一个", "来个",
)


def _is_requirement(text: str) -> bool:
    """识别明确的"项目需求"表达（含需求动作词）。"""
    return any(m in text for m in _REQUIREMENT_MARKERS)


def _print_help() -> None:
    console.print("[cyan]可用命令:[/]")
    console.print("  [bold]/help[/]    显示本帮助")
    console.print("  [bold]/spec[/]    查看当前 spec.md 内容")
    console.print("  [bold]/clear[/]   清空本次运行的代码和 spec（重新开始）")
    console.print("  [bold]/exit[/]    退出会话（或输入 exit / q / Ctrl-C）")
    console.print("")
    console.print("直接输入:")
    console.print("  [bold]<需求描述>[/]  需求澄清：agent 逐轮问清后写 spec.md")
    console.print("  [bold]编码[/]        进入编码执行（需先有 spec.md，按模块自主实现）")
    console.print("  [bold]<修改意见>[/]  已有代码后直接说修改意见，agent 会改代码")


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
    runtime.write_transcript(f"\n===== 需求澄清 =====\n{requirement}\n")
    spec_target = runtime.spec_path()
    task = (
        f"{requirement}\n\n"
        f"===== 输出位置 =====\n"
        f"请把最终需求写入 spec.md。spec.md 的完整路径是（用 write 工具写入该路径）：\n"
        f"{spec_target}\n"
    )
    result = run_interactive(
        CLARIFY_SYSTEM_PROMPT,
        task,
        retry=False,
        max_steps=SESSION_MAX_STEPS,
        bash_safety_mode=safety_mode,
        stream=stream,
    )
    if not interactive.is_terminal(result):
        console.print(result, markup=False)
    if spec_exists():
        console.print(f"\n[bold green]spec.md 已写入: {spec_target}[/]")
        _confirm_requirements(safety_mode, stream)
    else:
        console.print(f"\n[yellow]未生成 spec.md：{result}[/]", markup=False)


def run_qa(question: str, safety_mode: str, stream: bool) -> None:
    """直接回答用户的问题，不进入需求澄清/补充流程。

    让 agent 判断输入：若是提问（如"数据来源是啥"）则直接简洁回答并以
    [DONE] 结束本轮；若实际是需求则退回澄清流程（兜底，避免误判丢需求）。
    """
    console.print("[bold green]回答...[/]")
    runtime.write_transcript(f"\n===== 直接回答 =====\n{question}\n")
    context = ""
    if spec_exists():
        context += f"\n当前 spec.md 概要：{ensure_spec()[:400]}\n"
    files = _generated_code_files()
    if files:
        context += f"当前已生成代码：{', '.join(f.name for f in files)}\n"
    task = (
        f"用户输入：{question}\n\n"
        f"请判断并处理：\n"
        f"  - 如果是【对 agent 的提问/闲聊】（问数据来源、为什么、解释某概念等）→ "
        f"直接简洁回答，回复以 [DONE] 开头结束本轮，不要写 spec、不要改代码。\n"
        f"  - 如果是【项目需求】（要做个软件/功能）→ 走需求澄清流程，写 spec.md。\n"
        f"{context}"
    )
    result = run_interactive(
        CLARIFY_SYSTEM_PROMPT,
        task,
        retry=False,
        max_steps=SESSION_MAX_STEPS,
        bash_safety_mode=safety_mode,
        stream=stream,
    )
    if not interactive.is_terminal(result):
        console.print(result, markup=False)


def _confirm_requirements(safety_mode: str, stream: bool) -> None:
    """需求确认环节：澄清写完 spec 后，循环询问是否还有补充，直到确认完整。

    用户回车 → 确认无补充，提示输入"编码"开始实现；
    用户输入补充内容 → 让 agent 把补充整合进现有 spec.md，再继续询问。
    """
    while True:
        try:
            extra = interactive.prompt_human("\n还需要补充什么吗？[回车]=没有，直接输入补充内容 > ")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold green]需求确认完毕。输入 [cyan]编码[/] 开始实现。[/]")
            return
        if not extra.strip() or _is_noop_input(extra):
            console.print("[bold green]需求确认完毕。输入 [cyan]编码[/] 开始实现。[/]")
            return
        # 用户提问 → 直接回答，然后继续确认循环
        if _is_question(extra):
            run_qa(extra, safety_mode, stream)
            continue
        # 用户明确要开始编码 → 直接进入编码，不当作补充需求
        if is_code_intent(extra):
            console.print("[bold green]需求确认完毕，开始编码。[/]")
            run_code(extra, safety_mode, stream)
            return
        # 用户说"没有补充了/就这样" → 退出确认环节
        if _is_done_requirements(extra):
            console.print("[bold green]需求确认完毕。输入 [cyan]编码[/] 开始实现。[/]")
            return
        # 否则当作补充需求整合进 spec.md
        runtime.write_transcript(f"用户补充: {extra}\n")
        console.print("[bold green]正在把补充整合进 spec.md...[/]")
        task = (
            f"用户对已写入的 spec.md 补充了以下需求，请把它整合进现有 spec.md：\n"
            f"补充内容：{extra}\n\n"
            f"spec.md 路径：{runtime.spec_path()}\n"
            f"请先 read 现有 spec.md，用 edit 在对应章节更新/补充该需求，完成后回复 [DONE]。"
        )
        run_interactive(
            CLARIFY_SYSTEM_PROMPT,
            task,
            retry=False,
            max_steps=SESSION_MAX_STEPS,
            bash_safety_mode=safety_mode,
            stream=stream,
        )


def run_code(instruction: str, safety_mode: str, stream: bool) -> None:
    """编码执行：按 spec.md 自主实现，可 Ctrl-C 中断。"""
    if not spec_exists():
        console.print("[yellow]还没有 spec.md —— 先输入需求澄清。[/]")
        return
    spec = ensure_spec()
    out_dir = runtime.output_dir()
    runtime.write_transcript(f"\n===== 编码执行 =====\n{instruction}\n")

    # 注入 output/ 已有文件：让 agent 基于现状增量开发，而非从头重写
    existing_files = sorted(out_dir.glob("*")) if out_dir.is_dir() else []
    existing_note = ""
    if existing_files:
        names = ", ".join(p.name for p in existing_files)
        existing_note = (
            f"\noutput/ 下已有的文件：{names}\n"
            f"请先 read 了解已有代码，**基于它们增量开发/修改**，不要从头重写、"
            f"不要重复创建同名文件覆盖已有实现。\n"
        )

    task = (
        f"{instruction}\n\n"
        f"===== spec.md 项目级上下文 =====\n{spec}\n\n"
        f"===== 输出位置 =====\n"
        f"所有生成的代码写入目录（绝对路径，write 会自动创建）：\n{out_dir}\n"
        f"每个任务生成一个单独的主文件，不要写到别处。\n"
        f"{existing_note}"
    )
    console.print("[bold green]编码执行...[/]")
    result = run_interactive(
        CODE_SYSTEM_PROMPT,
        task,
        retry=True,
        max_steps=SESSION_MAX_STEPS,
        bash_safety_mode=safety_mode,
        stream=stream,
    )
    console.print(f"\n[bold green]本轮编码结束。产物在 {out_dir}。输入修改意见/新需求继续，/exit 退出。[/]")


# ============================================================
# 修改反馈（已有代码后）
# ============================================================


def _generated_code_files() -> list[Path]:
    """本次运行 output/ 目录下已生成的文件（代码/页面/资源），按修改时间倒序。

    不只认 .py——前端项目（index.html / style.css / script.js）也是已生成的代码，
    否则用户无法对这些项目发起修改反馈。
    """
    out = runtime.output_dir()
    if not out.is_dir():
        return []
    return sorted(
        (p for p in out.iterdir() if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def has_generated_code() -> bool:
    """是否已有 agent 生成的代码（output/ 下存在 .py）。"""
    return bool(_generated_code_files())


def run_modify(instruction: str, safety_mode: str, stream: bool) -> None:
    """根据用户反馈精准修改现有代码（用 edit，不重写整个文件）。"""
    files = _generated_code_files()
    if not files:
        console.print("[yellow]还没有已生成的代码 —— 先输入需求澄清 + 编码。[/]")
        return
    runtime.write_transcript(f"\n===== 修改反馈 =====\n{instruction}\n")
    file_list = "\n".join(f"  - {f.name}" for f in files)
    out_dir = runtime.output_dir()
    spec_ctx = f"\n\n===== spec.md 项目级上下文 =====\n{ensure_spec()}" if spec_exists() else ""
    task = (
        f"用户要求修改：{instruction}\n\n"
        f"output/ 目录下已有的代码文件：\n{file_list}\n"
        f"代码目录（绝对路径）：{out_dir}\n"
        f"请基于这些文件做**精准修改**（用 edit 只改需要改的部分，"
        f"不要用 write 重写整个文件），详见系统提示。\n"
        f"{spec_ctx}"
    )
    console.print("[bold green]修改代码...[/]")
    result = run_interactive(
        MODIFY_SYSTEM_PROMPT,
        task,
        retry=True,
        max_steps=SESSION_MAX_STEPS,
        bash_safety_mode=safety_mode,
        stream=stream,
    )
    console.print(f"\n[bold green]修改完成。代码在 {out_dir}。继续反馈/指令，/exit 退出。[/]")


def _clear_outputs() -> None:
    """清空本次运行的代码与 spec，重新开始（需确认）。"""
    try:
        confirm = interactive.prompt_human("确认清空本次运行的代码和 spec.md？[y/N] > ")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]已取消。[/]")
        return
    if confirm.lower() != "y":
        console.print("[yellow]已取消。[/]")
        return
    import shutil
    out = runtime.output_dir()
    if out.is_dir():
        shutil.rmtree(out)
    spec = runtime.spec_path()
    if spec.is_file():
        spec.unlink()
    console.print("[yellow]已清空本次运行的代码和 spec.md，可以开始新需求。[/]")


def run_interactive_session(safety_mode: str = "auto", stream: bool = True, run_dir: Path | None = None) -> None:
    """交互会话主循环：持续对话直到用户退出。

    参数:
        run_dir: 可选，复用指定运行目录（调试 agent 时沿用之前的 spec/代码），
                 不传则新建 runs/<时间戳>/。
    """
    interactive.ENABLED = True  # 会话模式始终允许 agent 追问
    run_dir_path = runtime.start_run(run_dir)
    console.print(f"[cyan]本次运行目录: {run_dir_path}（产物与 session.log 都在这里）[/]")
    console.print("[cyan]wz-agent 交互会话。输入需求开始；/help 查看命令；/exit 或 Ctrl-C 退出。[/]")
    _print_help()

    while True:
        try:
            prompt = "\n> " if spec_exists() else "\n需求 > "
            line = interactive.prompt_human(prompt)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]再见。[/]")
            break

        line = line.strip()
        if not line:
            continue
        runtime.write_transcript(f"用户输入: {line}\n")

        if line.lower() in EXIT_WORDS:
            console.print("[cyan]再见。[/]")
            break

        if line.startswith("/"):
            if _handle_command(line) == "exit":
                console.print("[cyan]再见。[/]")
                break
            continue

        # 无实际内容的输入（语气词/过短）→ 直接忽略，不触发任何动作
        if _is_noop_input(line):
            continue

        if is_code_intent(line) and spec_exists():
            run_code(line, safety_mode, stream)
        elif _is_question(line):
            run_qa(line, safety_mode, stream)
        elif has_generated_code():
            run_modify(line, safety_mode, stream)
        elif _is_requirement(line):
            run_clarify(line, safety_mode, stream)
        else:
            # 其他输入：不触发任何动作，提示用户
            console.print("[yellow]没理解你的意思。可以说需求（如\"帮我写一个游戏\"）、提问、或\"编码\"。/help 查看命令。[/]")
            runtime.write_transcript(f"[未识别输入] {line}\n")
