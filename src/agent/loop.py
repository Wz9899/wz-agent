"""ReAct 循环 —— Agent 的核心执行引擎。

完整的 ReAct 循环实现，支持工具调用和多步推理。
"""

from __future__ import annotations

import json
import os
from openai import OpenAI
from openai import APIError, APIConnectionError, RateLimitError

from agent import interactive
from agent.tools import make_tools

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
# LLM 配置（OpenAI 兼容协议，默认 DeepSeek，可用环境变量切换）
# ============================================================
# 走任意 OpenAI 兼容 API：
#   DeepSeek 默认：base_url=https://api.deepseek.com, model=deepseek-chat
#   GLM(智谱) 示例：LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
#                   LLM_MODEL=glm-4-flash（或 glm-4-plus 等）
#
# 统一读三个环境变量（都带 DeepSeek 默认值，切厂商只需在 .env 里改）：
#   LLM_API_KEY  —— 兼容旧 DEEPSEEK_API_KEY（未设时回退）
#   LLM_BASE_URL —— OpenAI 兼容服务地址
#   LLM_MODEL    —— 模型名
#
# client 不在 import 时创建：模块加载时 os.environ 可能还没有加载 .env
# （如 main.py 在 import agent 之后才调用 load_dotenv()）。若此时用占位符
# sk-xxx 构造 client，之后 load_dotenv() 也不会更新已创建的实例，导致
# .env 配置的 key 永远不生效。改为首次调用时再读取环境变量。
_client: OpenAI | None = None


# —— 配置读取函数（调用时读环境变量，确保 load_dotenv() 之后生效）——

def llm_api_key() -> str:
    """LLM API Key：优先 LLM_API_KEY，回退兼容旧 DEEPSEEK_API_KEY。"""
    return os.environ.get("LLM_API_KEY") or os.environ.get(
        "DEEPSEEK_API_KEY", "sk-xxx"
    )


def llm_base_url() -> str:
    """LLM 服务地址：默认 DeepSeek。"""
    return os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")


def llm_model() -> str:
    """LLM 模型名：默认 deepseek-chat。"""
    return os.environ.get("LLM_MODEL", "deepseek-chat")


def _get_client() -> OpenAI:
    """惰性获取 OpenAI 客户端（首次调用时构造，之后复用）。"""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=llm_api_key(),
            base_url=llm_base_url(),
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

    结构假设：[system, user, (assistant, tool*)*, user?, ...]。
    被丢弃的中间轮次是已完成的早期操作；任务定义在 system 与首条 user 中，
    最近 KEEP_HISTORY_ROUNDS 轮保留当前工作状态，因此压缩不丢失任务本身。
    压缩后插入一条 system 提示，避免 LLM 因记录减少而困惑。

    按"轮"为单位裁剪，assistant 与 user 都封轮——交互模式下用户回答/注入
    指令是独立的 user 轮次，必须成对保留，否则最新回答会被误裁。assistant
    与其 tool 结果始终成对，不产生 openai API 拒绝的孤立 tool 消息。
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
        if m.get("role") in ("assistant", "user"):
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

# ============================================================
# 流式输出
# ============================================================


def _accumulate_stream(chunks) -> tuple[str, list[dict]]:
    """把流式 chunk 序列累积为 (文本内容, 工具调用列表)。

    chunk 约定：具有 .choices[0].delta，delta 有 .content 与 .tool_calls
    （tool_calls 元素有 .index / .id / .function.{name, arguments}）。
    用极简 stub 对象即可驱动本函数，不依赖 openai SDK 具体类型。

    工具调用的 name / arguments 可能跨多个 chunk 分片传输，按 index 累积
    后拼接；返回的列表按 index 排序，结构与 openai 非流式响应的
    tool_calls 一致，便于下游统一处理。
    """
    content_parts: list[str] = []
    tool_calls: dict[int, dict] = {}

    for chunk in chunks:
        if not getattr(chunk, "choices", None):
            continue
        delta = chunk.choices[0].delta
        content = getattr(delta, "content", None)
        if content:
            content_parts.append(content)
        for tc in (getattr(delta, "tool_calls", None) or []):
            entry = tool_calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
            if getattr(tc, "id", None):
                entry["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is not None:
                if getattr(fn, "name", None):
                    entry["name"] += fn.name
                if getattr(fn, "arguments", None):
                    entry["arguments"] += fn.arguments

    content = "".join(content_parts)
    calls: list[dict] = []
    for idx in sorted(tool_calls):
        tc = tool_calls[idx]
        calls.append({
            "id": tc["id"],
            "type": "function",
            "function": {"name": tc["name"], "arguments": tc["arguments"]},
        })
    return content, calls


def _call_stream(
    client,
    *,
    messages: list[dict],
    tool_schemas: list[dict],
) -> tuple[str, list[dict]]:
    """流式调用 LLM，返回 (文本内容, 工具调用列表)。

    副作用：把 LLM 返回的文本增量实时打印到控制台（end="" + flush），
    让用户能看到 agent 的思考过程。工具调用与执行结果由 _run_loop 打印。
    """
    response = client.chat.completions.create(
        model=llm_model(),
        messages=messages,
        tools=tool_schemas,
        stream=True,
    )

    chunks: list = []
    for chunk in response:
        chunks.append(chunk)
        # 文本增量实时打印（同时保存 chunk 用于累积）
        if chunk.choices and chunk.choices[0].delta.content:
            interactive.print_human(chunk.choices[0].delta.content, end="")

    return _accumulate_stream(chunks)


def run(
    system_prompt: str,
    user_message: str,
    max_steps: int = 10,
    bash_safety_mode: str = "auto",
    stream: bool = False,
    tools: dict | None = None,
) -> str:
    """
    执行单轮 ReAct 循环：思考 → 行动 → 观察 → 再思考，直到任务完成。

    参数:
        system_prompt:    系统提示词，定义 agent 的行为规则。
        user_message:     用户输入的任务描述。
        max_steps:        最大工具调用次数（硬上限，防止死循环），默认 10。
        bash_safety_mode: Bash 安全模式 —— 'auto'（直接执行）或 'plan'（先收集后确认执行）。
        stream:           是否流式输出 —— True 时 LLM 回复与工具调用过程
                          实时打印到控制台，便于观察与随时中断。
        tools:            本循环可用的工具注册表（name → BaseTool 实例）。
                          None = make_tools() 现场构造全新实例。子 agent 用它注入受限工具集，
                          隔离能力边界（如去掉 task 工具防递归派发）。

    返回:
        模型的最终文本回复；如因异常提前终止则返回错误描述。
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return _run_loop(
        messages,
        bash_safety_mode=bash_safety_mode,
        max_steps=max_steps,
        stream=stream,
        tools=tools,
    )


def run_with_retry(
    system_prompt: str,
    user_message: str,
    max_steps: int = 10,
    bash_safety_mode: str = "auto",
    max_retries: int = 3,
    stream: bool = False,
) -> str:
    """
    带自动修复的 ReAct 循环：失败时把错误详情回喂给 LLM 继续修复。

    触发重试的条件：一轮执行返回的结果以 '[ERR]' 或 '[WARN]' 开头
    （工具执行异常、达到步数上限）。此时把失败详情作为新的用户消息
    让 LLM 分析原因并修复，最多重试 max_retries 次（默认 3）。

    不重试的条件：结果以 '[API-ERR]' 或 '[ABORT]' 开头 —— 前者是基础
    设施故障（限流/断网/服务端），后者是用户主动中断，LLM 都修不了，
    直接返回不浪费轮次。

    参数:
        system_prompt:    系统提示词。
        user_message:     用户输入的任务描述。
        max_steps:        每轮 ReAct 循环的最大工具调用次数。
        bash_safety_mode: Bash 安全模式。
        max_retries:      失败后的最大自动修复次数，默认 3。
        stream:           是否流式输出 —— True 时实时打印过程，便于观察。

    返回:
        成功的最终回复；不可修复的错误或重试用尽时返回错误描述。
    """
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return _run_with_retry_on_messages(
        messages,
        bash_safety_mode=bash_safety_mode,
        max_steps=max_steps,
        max_retries=max_retries,
        stream=stream,
    )


def _run_with_retry_on_messages(
    messages: list[dict],
    *,
    bash_safety_mode: str = "auto",
    max_steps: int = 10,
    max_retries: int = 3,
    stream: bool = False,
) -> str:
    """在给定的消息列表上跑带自动修复的循环（共享同一份历史）。

    run_with_retry 与 continue_turn（单循环会话轮次）共用的底层逻辑。
    '[API-ERR]'（基础设施故障）与 '[ABORT]'（用户中止）开头不重试。
    """
    for attempt in range(max_retries + 1):
        if attempt > 0:
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
            stream=stream,
        )

        # 基础设施故障 / 用户中止 —— 不重试
        if result.startswith(("[API-ERR]", "[ABORT]")):
            return result

        # 成功（非 [ERR]/[WARN] 开头）—— 立即返回
        if not result.startswith(("[ERR]", "[WARN]")):
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
    stream: bool = False,
    tools: dict | None = None,
) -> str:
    """
    单轮 ReAct 循环核心：在给定的消息列表上持续调用 LLM，直到任务完成。

    参数:
        messages:         当前对话历史（system + user + 之前的工具结果）。
                          由调用方负责构建，调用后可继续复用（用于重试）。
        bash_safety_mode: Bash 安全模式 —— 'auto'（直接执行）或 'plan'（先收集后确认执行）。
        max_steps:        最大工具调用次数（硬上限，防止死循环）。
        stream:           是否流式输出 —— True 时实时打印 LLM 文本与工具调用过程。
        tools:            可用工具集，None = make_tools() 现场构造（见 run()）。

    返回:
        模型的最终文本回复；如因异常提前终止则返回错误描述。
    """
    # ---- 0. 构造本循环的工具集并设置 bash 安全模式 ----
    # 不传 tools 时现场工厂构造：每个循环一份全新实例，bash 的 mode/_plan
    # 生命周期 = 本次 _run_loop 调用（计划在实例内收集/执行，循环结束即弃）。
    # 重试循环每次重调 _run_loop 也各自全新——失败轮次残留的计划不会泄漏。
    registry = make_tools() if tools is None else tools
    bash_tool = registry.get("bash")
    if bash_tool is not None:
        bash_tool.mode = bash_safety_mode
    tool_schemas = [tool.to_openai_function() for tool in registry.values()]

    step = 0

    while step < max_steps:
        # 清理消息中的孤立 surrogate（Windows 管道输入可能引入），
        # 避免 OpenAI json 序列化失败；无 surrogate 时是零成本 no-op
        for m in messages:
            content = m.get("content")
            if isinstance(content, str) and content:
                m["content"] = interactive.strip_surrogates(content)

        # ---- 2. 调用 LLM（带工具 schema）----
        try:
            if stream:
                content, tool_calls = _call_stream(
                    _get_client(),
                    messages=messages,
                    tool_schemas=tool_schemas,
                )
            else:
                response = _get_client().chat.completions.create(
                    model=llm_model(),
                    messages=messages,
                    tools=tool_schemas,
                )
                msg = response.choices[0].message
                content = msg.content or ""
                tool_calls = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in (msg.tool_calls or [])
                ]
        except KeyboardInterrupt:
            # 用户在 LLM 生成中按 Ctrl-C：走统一中断菜单。
            # 生成尚未写入 messages（_call_stream 只打印不修改），resume/inject 可安全重来
            if not interactive.ENABLED:
                raise
            action = interactive.handle_interrupt(messages)
            if action == "abort":
                return "[ABORT] 用户中断执行。"
            continue  # resume / inject：messages 未变，重新调 LLM
        except RateLimitError:
            return "[API-ERR] API 调用失败：请求频率超过限制（429），请稍后重试。"
        except APIConnectionError:
            return "[API-ERR] API 调用失败：网络连接错误，请检查网络后重试。"
        except APIError as e:
            return f"[API-ERR] API 调用失败：{e}"
        except Exception as e:
            return f"[API-ERR] 调用 LLM 时发生未预期错误：{e}"

        # ---- 3. 分支：工具调用 vs 纯文本回复 ----
        if tool_calls:
            if stream:
                print()  # 结束上一段流式文本行

            # 3a. 记录 assistant 消息（含 tool_calls）到对话历史
            #     空字段（如 content=None）不写入消息
            assistant_msg = {
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls,
            }
            messages.append({k: v for k, v in assistant_msg.items() if v is not None})

            for call in tool_calls:
                # 硬上限：即使在同一个 API 回复中也不可突破
                if step >= max_steps:
                    break

                step += 1
                tool_name = call["function"]["name"]
                try:
                    tool_args = json.loads(call["function"]["arguments"])
                except (json.JSONDecodeError, ValueError) as e:
                    # LLM 参数非法/截断（写大文件时常见）：不执行工具，
                    # 把错误返回给 LLM 让它重新生成完整参数，而不是崩溃
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": (
                            f"[ERR] 工具 '{tool_name}' 的参数不是合法 JSON：{e}。"
                            f"请重新生成完整、闭合的工具参数。"
                        ),
                    })
                    _maybe_compact(messages)
                    continue

                # 3b. 流式模式：先展示本次工具调用
                #     注意用 ASCII 箭头 '->' —— Windows GBK 控制台无法编码 '→'/'↳'
                if stream:
                    interactive.print_human(
                        f"  -> 工具 {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:160]})"
                    )

                # 3c. 查找并执行工具
                tool = registry.get(tool_name)
                if tool is None:
                    tool_result = f"错误：未知工具 —— {tool_name}"
                else:
                    # 3d. 执行工具（包裹 try-catch 防止工具异常导致 Agent 崩溃）
                    try:
                        tool_result = tool.run(**tool_args)
                    except KeyboardInterrupt:
                        # 用户在工具执行中按 Ctrl-C：先补合成 tool 结果保持消息成对
                        # （resume 的前提，否则 openai API 会拒绝孤儿 assistant），
                        # 再走统一中断菜单；resume/inject 时 break 出 for 重进 while
                        if not interactive.ENABLED:
                            raise
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": "[WARN] 工具执行被用户中断（Ctrl-C）。请调整参数重试、换方式或跳过。",
                        })
                        action = interactive.handle_interrupt(messages)
                        if action == "abort":
                            return "[ABORT] 用户中断执行。"
                        break
                    except Exception as e:
                        tool_result = f"错误：工具 '{tool_name}' 执行异常 —— {e}"

                # 3e. 截断过长的结果，保留原始长度信息
                total_len = len(tool_result)
                if total_len > MAX_TOOL_RESULT_CHARS:
                    tool_result = (
                        tool_result[:MAX_TOOL_RESULT_CHARS]
                        + f"\n\n...（工具输出共 {total_len} 字符，已截断至前 {MAX_TOOL_RESULT_CHARS} 字符）"
                    )

                # 3f. 流式模式：展示结果摘要（首行 + 截断），让用户看到 agent 观察到什么
                if stream:
                    preview = tool_result.strip().split("\n")[0][:200]
                    interactive.print_human(f"  -> 结果 {preview}")

                # 3g. 把工具执行结果加入对话历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": tool_result,
                })

                # 3h. 历史超预算时压缩早期轮次，防止长任务上下文无限膨胀
                _maybe_compact(messages)
        else:
            # 3i. 纯文本回复 —— 任务完成（写回历史，供交互对话的下一轮引用）
            messages.append({"role": "assistant", "content": content})
            return content

    # ---- 4. 达到步数上限 ----
    return f"[WARN] 已达到最大步数限制（{max_steps} 步），Agent 未完成任务。"


# ============================================================
# 单循环会话轮次
# ============================================================


def continue_turn(
    messages: list[dict],
    user_input: str,
    *,
    bash_safety_mode: str = "auto",
    max_steps: int = 30,
    stream: bool = True,
) -> str:
    """单循环会话的一轮：追加用户输入 → 带自动修复地跑 ReAct 循环。

    messages 由调用方（session REPL）跨轮持有，本函数只追加、不重建——
    这是 v2.2 单循环架构的唯一会话入口：澄清、编码、修改、问答共用
    同一份历史，阶段切换由模型路由（见 prompts/base.py）。

    失败语义沿用哨兵协议：结果以 '[ERR]'/'[WARN]' 开头时自动把失败详情
    回喂给 LLM 修复（最多 3 次）；'[API-ERR]'/'[ABORT]' 直接返回不重试。
    Ctrl-C 中断菜单（继续/注入/停止）由 _run_loop 内部处理。

    参数:
        messages:         跨轮持久的对话历史（含 system 消息），就地追加。
        user_input:       本轮用户输入（需求/修改意见/提问/命令译文）。
        bash_safety_mode: Bash 安全模式 —— 'auto' 或 'plan'。
        max_steps:        本轮最大工具调用次数（硬上限，防死循环）。
        stream:           是否流式输出（实时打印思考与工具调用）。

    返回:
        模型的最终文本回复；异常/中断时为哨兵错误描述。
    """
    messages.append({"role": "user", "content": user_input})
    return _run_with_retry_on_messages(
        messages,
        bash_safety_mode=bash_safety_mode,
        max_steps=max_steps,
        stream=stream,
    )
