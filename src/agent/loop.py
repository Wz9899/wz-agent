"""ReAct 循环 —— Agent 的核心执行引擎。

完整的 ReAct 循环实现，支持工具调用和多步推理。
"""

from __future__ import annotations

import json
import os
from openai import OpenAI
from openai import APIError, APIConnectionError, RateLimitError

from agent.tools import ALL_TOOLS, get_bash_tool

# ============================================================
# 常量
# ============================================================

# 工具执行结果的截断上限（字符数），防止 messages 膨胀
MAX_TOOL_RESULT_CHARS: int = 2000

# ============================================================
# 初始化 DeepSeek 客户端
# ============================================================
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-xxx"),
    base_url="https://api.deepseek.com",
)

# 注意：工具 schema 不再设为模块级常量 ——
# bash 工具的 description 会随 mode 变化而改变，
# 每次 run() 时重新生成以反映当前安全模式。
# 性能影响可忽略（4 个工具的反射远快于一次 API 调用）。

# ============================================================
# ReAct 循环
# ============================================================


def run(
    system_prompt: str,
    user_message: str,
    max_steps: int = 10,
    bash_safety_mode: str = "auto",
) -> str:
    """
    执行 ReAct 循环：思考 → 行动 → 观察 → 再思考，直到任务完成。

    参数:
        system_prompt:    系统提示词，定义 agent 的行为规则。
        user_message:     用户输入的任务描述。
        max_steps:        最大工具调用次数（硬上限，防止死循环），默认 10。
        bash_safety_mode: Bash 安全模式 —— 'auto'（直接执行）或 'plan'（先收集后确认执行）。

    返回:
        模型的最终文本回复；如因异常提前终止则返回错误描述。
    """
    # ---- 0. 设置 bash 安全模式并生成工具 schema ----
    bash_tool = get_bash_tool()
    bash_tool.mode = bash_safety_mode
    tool_schemas = [tool.to_openai_function() for tool in ALL_TOOLS.values()]

    # ---- 1. 初始化对话历史 ----
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    step = 0

    while step < max_steps:
        # ---- 2. 调用 LLM（带工具 schema）----
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=tool_schemas,
            )
        except RateLimitError:
            return "[ERR] API 调用失败：请求频率超过限制（429），请稍后重试。"
        except APIConnectionError:
            return "[ERR] API 调用失败：网络连接错误，请检查网络后重试。"
        except APIError as e:
            return f"[ERR] API 调用失败：{e}"
        except Exception as e:
            return f"[ERR] 调用 LLM 时发生未预期错误：{e}"

        msg = response.choices[0].message

        # ---- 3. 分支：工具调用 vs 纯文本回复 ----
        if msg.tool_calls:
            # 3a. 记录 assistant 消息（含 tool_calls）到对话历史
            #     exclude_none=True 避免把 null 字段（如 content=None）写入消息
            messages.append(msg.model_dump(exclude_none=True))

            for tool_call in msg.tool_calls:
                # 硬上限：即使在同一个 API 回复中也不可突破
                if step >= max_steps:
                    break

                step += 1
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # 3b. 查找工具
                tool = ALL_TOOLS.get(tool_name)
                if tool is None:
                    tool_result = f"错误：未知工具 —— {tool_name}"
                else:
                    # 3c. 执行工具（包裹 try-catch 防止工具异常导致 Agent 崩溃）
                    try:
                        tool_result = tool.run(**tool_args)
                    except Exception as e:
                        tool_result = f"错误：工具 '{tool_name}' 执行异常 —— {e}"

                # 3d. 截断过长的结果，保留原始长度信息
                total_len = len(tool_result)
                if total_len > MAX_TOOL_RESULT_CHARS:
                    tool_result = (
                        tool_result[:MAX_TOOL_RESULT_CHARS]
                        + f"\n\n...（工具输出共 {total_len} 字符，已截断至前 {MAX_TOOL_RESULT_CHARS} 字符）"
                    )

                # 3e. 把工具执行结果加入对话历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })
        else:
            # 3f. 纯文本回复 —— 任务完成
            return msg.content or ""

    # ---- 4. 达到步数上限 ----
    return f"[WARN] 已达到最大步数限制（{max_steps} 步），Agent 未完成任务。"
