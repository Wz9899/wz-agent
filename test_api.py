"""快速测试 DeepSeek API 连通性"""
from openai import OpenAI
import os
from dotenv import load_dotenv

# 加载 .env
load_dotenv()
api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    print("[ERROR] DEEPSEEK_API_KEY not set")
    exit(1)

print(f"[OK] Key loaded: {api_key[:10]}...")

# 测试连通性
client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

try:
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "Reply 'API TEST SUCCESS'"}],
        max_tokens=20
    )
    print(f"[OK] API test succeeded! Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"[ERROR] API test failed: {e}")
