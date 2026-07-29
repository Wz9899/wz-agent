"""ReAct 循环 —— Agent 的核心执行引擎。"""

import os
from openai import OpenAI

# ============================================================
# 初始化 DeepSeek 客户端
# DeepSeek 兼容 OpenAI SDK，只需改 base_url 和 api_key
# ============================================================
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-xxx"),
    base_url="https://api.deepseek.com",
)

# ============================================================
# 第 1 步：最简对话 —— 无工具、无循环，仅一次 API 调用
# ============================================================


def run(system_prompt: str, user_message: str) -> str:
    """
    发送 system prompt + 用户消息给 DeepSeek，返回模型回复。
    
    参数:
        system_prompt: 系统提示词，定义 agent 的行为规则
        user_message:  用户输入的任务描述
    
    返回:
        模型的文本回复
    """
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content
