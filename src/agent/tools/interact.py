"""ask_user / checkpoint —— 人机交互工具。

这两个工具让 agent 在 ReAct 循环中：
  - ask_user(question)：中途向用户提问，阻塞等回答，回答作为工具结果返回。
  - checkpoint(summary)：完成一个模块/阶段后停下汇报，用户确认后才继续。

非交互模式（interactive.ENABLED=False）下两者都退化：返回提示文本，让 LLM
自行做合理假设或继续，绝不阻塞。工具由 make_tools() 工厂构造进每个循环，
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
        try:
            answer = interactive.prompt_human("  你的回答 > ")
        except EOFError:
            return "(用户未提供回答)"
        return answer if answer else "(用户未提供回答)"


class CheckpointTool(BaseTool):
    """阶段汇报：每完成一个模块调用，把进度打印到终端供用户观察，不停下。"""

    @property
    def name(self) -> str:
        return "checkpoint"

    @property
    def description(self) -> str:
        return (
            "完成一个模块/阶段后调用它，把当前进度打印到终端供用户观察，"
            "然后继续执行——不会暂停等待。适合分模块实现时每完成一个模块汇报一次。"
        )

    def run(self, summary: str) -> str:
        """汇报当前进度（非阻塞，不等待用户）。

        参数:
            summary: 当前进度摘要（做了什么、下一步计划）。
        """
        if not interactive.ENABLED:
            return "(非交互模式) checkpoint 跳过，继续执行。"
        interactive.print_human(f"\n── 进度汇报 ──\n{summary}\n────────────")
        return "[CHECKPOINT] 进度已汇报，继续执行。"
