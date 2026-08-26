"""task 工具 —— 子 agent 派发（LLM 自主决定何时委派）。

核心机制：Agent 即工具。主 agent 的 LLM 发起一次普通的 tool_call，
harness 在工具的 run() 里递归调用 agent 循环本身（loop.run），
用全新的消息历史执行，只把最终回复作为工具结果返回主对话。

四个关键设计：
1. 上下文隔离 —— 子 agent 只看到自己的 system prompt + 任务描述，
   看不到主对话历史；主 agent 只看到子 agent 的最终回复（天然是摘要），
   中间几十 KB 的工具输出不会占用主对话的上下文预算。
2. 静态注册表 —— 子 agent 类型在此预定义（提示词/工具集/步数上限），
   LLM 只能按名选用，不能自创角色。能力边界是工程决定。
3. 禁止递归 —— 子 agent 的工具集不含 task 工具（注册表层面隔离），
   另加运行时深度守卫兜底（防未来配置失误）。
4. 并行扇出（v2.4）—— fan_out 传多个子问题时线程池并行调查，
   每线程独立 messages + 工厂全新工具实例（make_tools），互不共享
   可变状态。仅对只读 agent 开放（工具集无 write/edit）——并行写
   需要 worktree 隔离，那是更重的机制，暂不引入。
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from agent.tools.base import BaseTool
from agent.interactive import print_human

# ============================================================
# 子 agent 注册表（静态定义）
# ============================================================


class SubAgentDef:
    """一个子 agent 类型的定义：提示词 + 能力边界。

    tools 存工具名（str）而非实例 —— 实例在运行时从全局注册表解析，
    避免本模块 import 时与 agent.tools 循环依赖。
    """

    def __init__(self, name: str, summary: str, system_prompt: str, tool_names: list[str], max_steps: int):
        self.name = name
        self.summary = summary                # 一句话用途（拼进 task 工具描述，LLM 据此选择）
        self.system_prompt = system_prompt    # 子 agent 的人设与规则
        self.tool_names = tool_names          # 可用工具名列表（全局注册表的子集）
        self.max_steps = max_steps            # 工具调用次数硬上限


SUBAGENTS: dict[str, SubAgentDef] = {
    "investigator": SubAgentDef(
        name="investigator",
        summary="只读调查员：在代码库中搜索、阅读、回答问题，不改任何文件",
        system_prompt=(
            "你是代码调查员，在独立上下文中回答主 agent 交办的调查问题。\n"
            "规则:\n"
            "1. 只读不写 —— 不创建/修改/删除任何文件；bash 只用于查看"
            "（ls/cat/grep 等），禁止有副作用的命令（安装、git 写操作、删除等）\n"
            "2. 高效调查: 先定位相关文件，再读关键部分，不通读无关代码。"
            "工具调用预算约 15 次 —— 优先用一条命令覆盖多个文件"
            "（如 grep 同时传多个文件、ls -R 一次看全），避免逐文件串行\n"
            "3. 某命令失败时立即换等效命令重试，不要重复尝试同一失败命令\n"
            "4. 结论优先: 最终回复用简洁中文总结 —— 直接回答问题，"
            "附关键文件路径与证据；与问题无关的细节不要写"
        ),
        tool_names=["read", "bash"],
        max_steps=20,
    ),
    "coder": SubAgentDef(
        name="coder",
        summary="编码执行者：独立完成一个边界清晰的编码任务（写新文件/改现有文件）",
        system_prompt=(
            "你是编码执行者，在独立上下文中完成主 agent 交办的一个具体编码任务。\n"
            "规则:\n"
            "1. 动手前先读相关文件理解现状；改动最小化，严格不超出任务范围\n"
            "2. 不要重构/重写任务范围外的代码；发现范围外的问题，在最终回复中说明即可\n"
            "3. 完成后自检（语法检查/运行验证），最终回复说明: 改了哪些文件、"
            "关键实现思路、如何验证的"
        ),
        tool_names=["read", "write", "edit", "bash"],
        max_steps=15,
    ),
}


# ============================================================
# 深度守卫（防递归派发）
# ============================================================

# 当前子 agent 嵌套深度。注册表隔离（子 agent 工具集无 task）是第一道防线，
# 这里是第二道：万一未来某个子 agent 定义误含 task，运行时直接拒绝。
_DEPTH: int = 0

# 并行扇出的子问题上限（成本护栏：一次 tool_call 最多派几个并行子 agent）
MAX_FAN_OUT: int = 4

# 写工具名单（只读边界）：含写工具的 agent 并行会产生文件冲突
_WRITE_TOOLS: frozenset[str] = frozenset({"write", "edit"})


# ============================================================
# task 工具
# ============================================================


class TaskTool(BaseTool):
    """派出子 agent 在独立上下文中完成独立任务，返回其最终报告。"""

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        # 动态拼接注册表 —— LLM 选择子 agent 的唯一信息源
        roles = "；".join(f"{d.name}（{d.summary}）" for d in SUBAGENTS.values())
        return (
            "派一个子 agent 在独立上下文中完成一项独立任务，返回其最终报告。"
            "适合两类场景: ① 需要多轮探索才能回答的调查类问题；"
            "② 边界清晰、中间过程对当前对话无价值的编码子任务。"
            "用它可以避免大量工具输出占用主对话上下文。"
            f"可选角色: {roles}。"
            "并行调查：只读角色可传 fan_out（多个子问题），各子 agent "
            "线程池并行执行、上下文独立，结果按序聚合返回——一次摸清"
            "互不依赖的多个面向时用它，比逐个串行问快得多。"
            "注意: 子 agent 看不到当前对话，task 必须自包含全部背景"
            "（目标、相关文件路径、约束、验收标准）。"
        )

    def run(self, task: str, subagent: str, fan_out: list[str] | None = None) -> str:
        """执行子 agent 任务。

        task: 自包含的任务描述（目标、相关路径、约束、验收标准）；
              fan_out 模式下作为所有子问题的共享背景
        subagent: 子 agent 名（investigator / coder）
        fan_out: 并行子问题列表（仅只读 agent 可用），每个子问题一个独立
                 子 agent 线程，结果按序聚合返回；None = 单任务串行
        """
        global _DEPTH

        # ---- 1. 校验（错误以文本返回，主 LLM 可修正后重试）----
        spec = SUBAGENTS.get(subagent)
        if spec is None:
            available = "、".join(SUBAGENTS)
            return f"[ERR] 未知子 agent 类型 '{subagent}'。可选: {available}。请修正后重试。"
        if _DEPTH >= 1:
            return "[ERR] 子 agent 内不允许再派子 agent（防止递归失控）。请自己完成该任务。"
        if not task.strip():
            return "[ERR] task 不能为空 —— 请提供自包含的任务描述。"

        # ---- 2. 分发：并行扇出 or 单任务串行 ----
        if fan_out:
            return self._run_fan_out(task, spec, fan_out)
        return self._run_single(task, spec)

    def _run_fan_out(self, task: str, spec: "SubAgentDef", fan_out: list[str]) -> str:
        """并行扇出：每个子问题一个独立子 agent，线程池执行，按序聚合。

        线程安全前提（v2.4 工厂化）：每线程 make_tools() 全新实例，
        bash 的 mode/_plan 等可变状态零共享。只读护栏保证并行无文件冲突。
        """
        global _DEPTH

        # 只读护栏：含写工具的 agent 并行会互相踩文件，直接拒绝
        writes = _WRITE_TOOLS & set(spec.tool_names)
        if writes:
            return (
                f"[ERR] '{spec.name}' 有写权限（{sorted(writes)}），不允许并行 —— "
                f"并行写需要工作目录隔离。请逐个串行派发，或不传 fan_out。"
            )
        if len(fan_out) > MAX_FAN_OUT:
            return f"[ERR] fan_out 最多 {MAX_FAN_OUT} 个子问题（收到 {len(fan_out)} 个）。请拆分或精选。"

        items = [i.strip() for i in fan_out if i and i.strip()]
        n = len(items)
        if n == 0:
            return "[ERR] fan_out 为空（全是空白项）—— 请提供至少一个子问题。"

        # 延迟 import: loop.py 依赖 agent.tools（本模块），顶层 import 会循环依赖
        from agent.loop import run as loop_run
        from agent.tools import make_tools

        def _question(i: int) -> str:
            """第 i 个子问题的完整任务：共享背景 + 具体子问题。"""
            return (
                f"{task}\n\n===== 本次只调查这个子问题（{i + 1}/{n}）=====\n{items[i]}"
                f"\n（其余子问题由别的调查员并行负责，你不用管。）"
            )

        def _work(i: int) -> str:
            """线程体：全新工具实例 + 独立 messages 跑子循环。"""
            return loop_run(
                system_prompt=spec.system_prompt,
                user_message=_question(i),
                max_steps=spec.max_steps,
                bash_safety_mode="auto",      # 子循环实际执行命令，不进 plan 收集
                stream=False,
                tools=make_tools(spec.tool_names),  # 工厂：每线程全新实例
            )

        print_human(f"\n  [task·并行] 启动 {n} 个 {spec.name}：")
        for i, item in enumerate(items):
            print_human(f"    {i + 1}. {item[:60]}")

        results: list[str | None] = [None] * n
        start = time.time()
        _DEPTH += 1
        try:
            with ThreadPoolExecutor(max_workers=n) as pool:
                futures = {pool.submit(_work, i): i for i in range(n)}
                try:
                    for fut in as_completed(futures):
                        i = futures[fut]
                        results[i] = fut.result()
                        preview = (results[i] or "").strip().split("\n")[0][:80]
                        print_human(f"  [task·并行] {i + 1}/{n} 完成: {preview}")
                except KeyboardInterrupt:
                    # Ctrl-C 在主线程抛出：取消未启动的、不等在跑的（只读子
                    # agent 无副作用，让其自然收尾）。KI 继续上抛 → _run_loop
                    # 的中断菜单接管（继续/注入/停止）。
                    for f in futures:
                        f.cancel()
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise
        finally:
            _DEPTH -= 1

        # ---- 聚合（按子问题原序，不按完成序）----
        sections = []
        for i, item in enumerate(items):
            body = results[i] or "（无结果 —— 该子 agent 被中断或失败）"
            sections.append(f"== 子问题 {i + 1}/{n}: {item[:80]} ==\n{body}")
        print_human(f"  [task·并行] 全部完成（{time.time() - start:.0f}s），结果已聚合")
        return f"并行调查结果（{n} 个子问题，按序）:\n\n" + "\n\n".join(sections)

    def _run_single(self, task: str, spec: "SubAgentDef") -> str:
        """单任务串行派发（v2.1 行为不变）。"""
        global _DEPTH

        # ---- 构造受限工具集（工厂：全新实例，无 task —— 递归结构性防线）----
        # 延迟 import: loop.py 依赖 agent.tools（本模块），顶层 import 会循环依赖
        from agent.loop import run as loop_run
        from agent.tools import make_tools

        try:
            sub_tools = make_tools(spec.tool_names)
        except ValueError as e:
            return f"[ERR] 子 agent '{spec.name}' 的工具配置失效（{e}）。这是配置错误，请换其他方式完成。"

        # ---- 执行（子 agent 强制 auto 模式，用独立 bash 实例）----
        # 不继承父循环的 plan 模式：子 agent 处于独立上下文，其命令应实际执行
        # （investigator 需读 bash 输出、coder 需跑验证）；独立实例已隔离状态，
        # 不会污染父循环的执行计划。

        print_human(f"\n  [task] 启动子 agent {spec.name}: {task[:80]}")
        _DEPTH += 1
        start = time.time()
        try:
            result = loop_run(
                system_prompt=spec.system_prompt,
                user_message=task,
                max_steps=spec.max_steps,
                bash_safety_mode="auto",      # 子循环实际执行命令，不进 plan 收集
                stream=False,                 # 不转发子 agent 流式输出，避免污染主对话显示
                tools=sub_tools,              # 受限工具集（无 task —— 递归深度天然为 1）
            )
        finally:
            _DEPTH -= 1

        # ---- 4. 返回（[ERR]/[WARN] 前缀原样保留，主 LLM 可决定重派）----
        preview = result.strip().split("\n")[0][:120]
        print_human(f"  [task] 完成（{time.time() - start:.0f}s）: {preview}")
        return result
