"""ask_user / checkpoint —— 人机交互工具。

这两个工具让 agent 在 ReAct 循环中：
  - ask_user(question)：中途向用户提问，阻塞等回答，回答作为工具结果返回。
  - checkpoint(summary)：完成一个模块/阶段后停下汇报，用户确认后才继续。

非交互模式（interactive.ENABLED=False）下两者都退化：返回提示文本，让 LLM
自行做合理假设或继续，绝不阻塞。工具仍注册在 ALL_TOOLS（schema 跨模式稳定），
triage/to-tickets 等非交互流程的 prompt 不提及它们，LLM 极少误调。
"""

from __future__ import annotations

from agent import interactive
from agent.tools.base import BaseTool


class AskUserTool(BaseTool):
    """向用户提出一个必须由用户回答才能继续的问题。"""

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return (
            "向用户提出一个问题，阻塞等待用户在终端回答，把回答作为工具结果返回。"
            "适用于需求不明确、存在多种取舍、或需要用户拍板时必须先确认的场景。"
        )

    def run(self, question: str) -> str:
        """提问并等待回答。

        参数:
            question: 要问用户的问题（一次一个，聚焦最关键的点）。
        """
        if not interactive.ENABLED:
            return (
                "(非交互模式) 无法询问用户。请基于已有信息做最合理假设，"
                "并在最终回复中明确标注该假设。"
            )
        interactive.print_human(f"\n[询问] {question}")
        answer = interactive.prompt_human("  你的回答 > ")
        return answer if answer else "(用户未提供回答)"


class CheckpointTool(BaseTool):
    """阶段汇报并暂停：每完成一个模块调用，等用户确认后再继续。"""

    @property
    def name(self) -> str:
        return "checkpoint"

    @property
    def description(self) -> str:
        return (
            "阶段汇报并暂停执行：完成一个模块/阶段后调用它，汇报当前进度，"
            "等待用户确认（回车继续 / 输入新指令 / 输 stop 终止）后才继续下一步。"
            "适合分模块实现时每完成一个模块同步一次进度。"
        )

    def run(self, summary: str) -> str:
        """汇报进度并等待确认。

        参数:
            summary: 当前进度摘要（做了什么、下一步计划）。
        """
        if not interactive.ENABLED:
            return "(非交互模式) checkpoint 跳过，继续执行。"
        interactive.print_human(f"\n── 进度汇报 ──\n{summary}\n────────────")
        ans = interactive.prompt_human("  [回车]=继续  [输入]=新指令  [stop]=终止 > ")
        if ans.lower() == "stop":
            interactive.abort_requested = True
            return "[ABORT] 用户要求停止执行。请停止所有操作并总结当前进度。"
        if ans:
            interactive.pending_instruction = ans
            return "[CHECKPOINT] 用户已确认，新的指令将作为独立消息注入对话。"
        return "[CHECKPOINT] 用户已确认，继续执行。"
