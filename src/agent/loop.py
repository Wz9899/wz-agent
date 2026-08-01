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

# 工具执行结果的截断上限（字符数），防止单条结果膨胀
MAX_TOOL_RESULT_CHARS: int = 2000

# 消息历史总量预算（字符数）：超过后压缩早期轮次，防止长任务上下文无限膨胀。
# 粗略估算：单轮 LLM 回复 + 工具结果约 1-4k 字符，40k 预算可容纳十余轮。
MAX_CONTEXT_CHARS: int = 40_000

# 压缩时至少保留的最近"轮"数（一轮 = 一次 assistant 工具调用 + 其结果）
KEEP_HISTORY_ROUNDS: int = 6

# ============================================================
# DeepSeek 客户端（惰性初始化）
# ============================================================

# client 不在 import 时创建：模块加载时 os.environ 可能还没有加载 .env
# （如 main.py 在 import agent 之后才调用 load_dotenv()）。若此时用占位符
# sk-xxx 构造 client，之后 load_dotenv() 也不会更新已创建的实例，导致
# .env 配置的 key 永远不生效。改为首次调用时再读取环境变量。
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """惰性获取 OpenAI 客户端（首次调用时构造，之后复用）。"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ.get("DEEPSEEK_API_KEY", "sk-xxx"),
            base_url="https://api.deepseek.com",
        )
    return _client


# 注意：工具 schema 不再设为模块级常量 ——
# bash 工具的 description 会随 mode 变化而改变，
# 每次 run() 时重新生成以反映当前安全模式。
# 性能影响可忽略（4 个工具的反射远快于一次 API 调用）。

# ============================================================
# 历史压缩（防 context 膨胀）
# ============================================================


def _estimate_chars(messages: list[dict]) -> int:
    """粗略估算消息列表总字符数（content + 序列化 tool_calls）。

    仅用于预算判断，不追求精确——固定消息开销忽略不计。
    """
    total = 0
    for m in messages:
        content = m.get("content") or ""
        total += len(content)
        calls = m.get("tool_calls")
        if calls:
            total += len(json.dumps(calls, ensure_ascii=False))
    return total


def _maybe_compact(messages: list[dict]) -> None:
    """消息总量超过预算时，就地压缩历史：保留 system + 首条 user + 最近 N 轮。

    结构假设：[system, user, (assistant, tool*)*, ...]。
    被丢弃的中间轮次是已完成的早期工具操作；任务定义在 system 与首条 user 中，
    最近 KEEP_HISTORY_ROUNDS 轮保留当前工作状态，因此压缩不丢失任务本身。
    压缩后插入一条 system 提示，避免 LLM 因记录减少而困惑。

    按"轮"为单位裁剪，保证保留的 assistant 与其 tool 结果始终成对，
    不会产生 openai API 拒绝的孤立 tool 消息。
    """
    if _estimate_chars(messages) <= MAX_CONTEXT_CHARS:
        return

    head = messages[:2]          # system + 首条 user（任务定义）
    tail = messages[2:]

    # 从尾部逆序收集最近 KEEP_HISTORY_ROUNDS 轮
    rounds: list[list[dict]] = []
    current: list[dict] = []
    for m in reversed(tail):
        current.insert(0, m)
        if m.get("role") == "assistant":
            rounds.insert(0, current)
            current = []
            if len(rounds) >= KEEP_HISTORY_ROUNDS:
                break

    messages[:] = head + [m for r in rounds for m in r]
    messages.insert(
        len(head),
        {
            "role": "system",
            "content": (
                "（为控制上下文长度，较早的工具调用记录已移除。"
                "请基于当前对话中的最新状态继续原任务。）"
            ),
        },
    )


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
    执行单轮 ReAct 循环：思考 → 行动 → 观察 → 再思考，直到任务完成。

    参数:
        system_prompt:    系统提示词，定义 agent 的行为规则。
        user_message:     用户输入的任务描述。
        max_steps:        最大工具调用次数（硬上限，防止死循环），默认 10。
        bash_safety_mode: Bash 安全模式 —— 'auto'（直接执行）或 'plan'（先收集后确认执行）。

    返回:
        模型的最终文本回复；如因异常提前终止则返回错误描述。
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return _run_loop(messages, bash_safety_mode=bash_safety_mode, max_steps=max_steps)


def run_with_retry(
    system_prompt: str,
    user_message: str,
    max_steps: int = 10,
    bash_safety_mode: str = "auto",
    max_retries: int = 3,
) -> str:
    """
    带自动修复的 ReAct 循环：失败时把错误详情回喂给 LLM 继续修复。

    触发重试的条件：一轮执行返回的结果以 '[ERR]' 或 '[WARN]' 开头
    （工具执行异常、达到步数上限）。此时把失败详情作为新的用户消息
    让 LLM 分析原因并修复，最多重试 max_retries 次（默认 3）。

    不重试的条件：结果以 '[API-ERR]' 开头 —— 429 限流、网络断开、
    API 服务端错误等属于基础设施故障，LLM 无法通过修改代码修复，
    重试只会浪费轮次，直接原样返回。

    参数:
        system_prompt:    系统提示词。
        user_message:     用户输入的任务描述。
        max_steps:        每轮 ReAct 循环的最大工具调用次数。
        bash_safety_mode: Bash 安全模式。
        max_retries:      失败后的最大自动修复次数，默认 3。

    返回:
        成功的最终回复；不可修复的 API 错误或重试用尽时返回错误描述。
    """
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    for attempt in range(max_retries + 1):
        # 第一轮用原始任务，后续轮次把失败详情回喂给 LLM
        if attempt == 0:
            messages.append({"role": "user", "content": user_message})
        else:
            messages.append({
                "role": "user",
                "content": (
                    "上一轮执行未成功。请分析失败原因，"
                    "修复问题后继续完成原本的任务。\n\n失败详情:\n"
                    + result
                ),
            })

        result = _run_loop(
            messages,
            bash_safety_mode=bash_safety_mode,
            max_steps=max_steps,
        )

        # API 层错误（限流/断网/服务端）—— LLM 修不了，直接返回不重试
        if result.startswith("[API-ERR]"):
            return result

        # 成功（非 [ERR]/[WARN] 开头）—— 立即返回
        if not result.startswith("[ERR]") and not result.startswith("[WARN]"):
            return result

    # 重试用尽
    return (
        f"[ERR] 自动修复 {max_retries} 次后仍未成功，需要人工介入。\n\n"
        f"最后一次失败详情:\n{result}"
    )


def _run_loop(
    messages: list[dict],
    bash_safety_mode: str = "auto",
    max_steps: int = 10,
) -> str:
    """
    单轮 ReAct 循环核心：在给定的消息列表上持续调用 LLM，直到任务完成。

    参数:
        messages:         当前对话历史（system + user + 之前的工具结果）。
                          由调用方负责构建，调用后可继续复用（用于重试）。
        bash_safety_mode: Bash 安全模式 —— 'auto'（直接执行）或 'plan'（先收集后确认执行）。
        max_steps:        最大工具调用次数（硬上限，防止死循环）。

    返回:
        模型的最终文本回复；如因异常提前终止则返回错误描述。
    """
    # ---- 0. 设置 bash 安全模式并生成工具 schema ----
    bash_tool = get_bash_tool()
    bash_tool.mode = bash_safety_mode
    tool_schemas = [tool.to_openai_function() for tool in ALL_TOOLS.values()]

    step = 0

    while step < max_steps:
        # ---- 2. 调用 LLM（带工具 schema）----
        try:
            response = _get_client().chat.completions.create(
                model="deepseek-chat",
                messages=messages,
                tools=tool_schemas,
            )
        except RateLimitError:
            return "[API-ERR] API 调用失败：请求频率超过限制（429），请稍后重试。"
        except APIConnectionError:
            return "[API-ERR] API 调用失败：网络连接错误，请检查网络后重试。"
        except APIError as e:
            return f"[API-ERR] API 调用失败：{e}"
        except Exception as e:
            return f"[API-ERR] 调用 LLM 时发生未预期错误：{e}"

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

                # 3f. 历史超预算时压缩早期轮次，防止长任务上下文无限膨胀
                _maybe_compact(messages)
        else:
            # 3f. 纯文本回复 —— 任务完成
            return msg.content or ""

    # ---- 4. 达到步数上限 ----
    return f"[WARN] 已达到最大步数限制（{max_steps} 步），Agent 未完成任务。"
