"""Prompt 模板包。

交互会话（单循环）:  base.py 的 BASE_SYSTEM_PROMPT / build_system_prompt()
                     —— 澄清、编码、修改、问答在同一对话里模型自路由。
全自动 headless:    triage.py（issue 分诊）、to_tickets.py（任务拆解）
                     —— 不进交互循环，保留独立提示。

v2.2：clarify / code / modify 三套阶段提示已合并进 base.py（[DONE]
阶段边界协议随之退役——单循环下模型返回纯文本即本轮自然结束）。
"""

from agent.prompts.base import BASE_SYSTEM_PROMPT, build_system_prompt
from agent.prompts.to_tickets import TO_TICKETS_SYSTEM_PROMPT
from agent.prompts.triage import TRIAGE_SYSTEM_PROMPT

__all__ = [
    "BASE_SYSTEM_PROMPT",
    "build_system_prompt",
    "TRIAGE_SYSTEM_PROMPT",
    "TO_TICKETS_SYSTEM_PROMPT",
]
