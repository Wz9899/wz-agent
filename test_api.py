"""临时测试：验证 DeepSeek API 调用是否正常。"""

import os
import sys

# 把 src 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# 加载 .env 文件（如果有的话）
from dotenv import load_dotenv
load_dotenv()

from agent.loop import run

if not os.environ.get("DEEPSEEK_API_KEY"):
    print("错误：请设置环境变量 DEEPSEEK_API_KEY")
    print("  export DEEPSEEK_API_KEY=sk-xxxx   (Linux/Mac)")
    print("  set DEEPSEEK_API_KEY=sk-xxxx      (Windows)")
    sys.exit(1)

result = run(
    system_prompt="你是一个简洁的助手，用中文回答。",
    user_message="用一句话介绍什么是 ReAct 循环。",
)
print("模型回复：")
print(result)
