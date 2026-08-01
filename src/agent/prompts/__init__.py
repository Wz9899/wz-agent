"""Prompt 模板包 —— 多阶段 Prompt 切换。

阶段一 (clarify):     需求澄清，Agent 主动追问用户需求。
阶段二 (code):        编码执行，Agent 按 spec.md 编写代码。
阶段三 (triage):      分诊状态机，把 issue 移到五档标签之一。
阶段四 (to-tickets):  任务拆解，把 spec 拆成垂直切片 ticket。
"""

from agent.prompts.clarify import CLARIFY_SYSTEM_PROMPT
from agent.prompts.code import CODE_SYSTEM_PROMPT
from agent.prompts.triage import TRIAGE_SYSTEM_PROMPT
from agent.prompts.to_tickets import TO_TICKETS_SYSTEM_PROMPT

__all__ = [
    "CLARIFY_SYSTEM_PROMPT",
    "CODE_SYSTEM_PROMPT",
    "TRIAGE_SYSTEM_PROMPT",
    "TO_TICKETS_SYSTEM_PROMPT",
]
