"""临时测试：验证 LLM API 调用是否正常（当前 .env 配置的模型）。"""

import os
import sys

# 把 src 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# 加载项目根的 .env（与 cwd 无关）
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from agent.loop import run, llm_api_key

if llm_api_key() in ("", "sk-xxx"):
    print("错误：请在 .env 或环境变量里设置 LLM_API_KEY（或 DEEPSEEK_API_KEY）")
    print("  参考 .env.example 的配置说明")
    sys.exit(1)

result = run(
    system_prompt="你是一个简洁的助手，用中文回答。",
    user_message="用一句话介绍什么是 ReAct 循环。",
)
print("模型回复：")
print(result)
