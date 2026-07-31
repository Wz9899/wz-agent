"""Prompt 模板包 —— 两阶段 Prompt 切换。

阶段一 (clarify): 需求澄清，Agent 主动追问用户需求。
阶段二 (code):    编码执行，Agent 按 spec.md 编写代码。
"""

from agent.prompts.clarify import CLARIFY_SYSTEM_PROMPT
from agent.prompts.code import CODE_SYSTEM_PROMPT

__all__ = ["CLARIFY_SYSTEM_PROMPT", "CODE_SYSTEM_PROMPT"]
