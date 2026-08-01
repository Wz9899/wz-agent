"""agent.loop 客户端惰性初始化测试。

验证 client 在首次调用时才从环境变量构造（修复 .env 在 import 之后
加载导致的占位符问题），且之后复用同一实例。
"""

from agent import interactive

import agent.loop as loop


def test_get_client_reads_current_env(monkeypatch):
    """client 应从当前环境变量构造，而非 import 时的值。"""
    monkeypatch.setattr(loop, "_client", None)          # 重置惰性缓存
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-test-key")
    client = loop._get_client()
    assert client.api_key == "env-test-key"


def test_get_client_is_cached(monkeypatch):
    """第二次调用应返回同一实例（不重复构造）。"""
    monkeypatch.setattr(loop, "_client", None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-test-key")
    first = loop._get_client()
    second = loop._get_client()
    assert first is second


def test_get_client_falls_back_to_placeholder(monkeypatch):
    """环境变量缺失时保持原占位符行为（由调用方前置校验兜底）。"""
    monkeypatch.setattr(loop, "_client", None)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    assert loop._get_client().api_key == "sk-xxx"


# ---------- 历史压缩 _maybe_compact ----------


def _rounds(n: int) -> list[dict]:
    """构造 system + user + n 轮（assistant 工具调用 + tool 结果）消息。"""
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    for i in range(n):
        msgs.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": f"t{i}", "function": {"name": "read", "arguments": "{}"}}],
        })
        msgs.append({"role": "tool", "tool_call_id": f"t{i}", "content": "R" * 1000})
    return msgs


def test_compact_noop_within_budget(monkeypatch):
    """预算充足时消息保持不变。"""
    monkeypatch.setattr(loop, "MAX_CONTEXT_CHARS", 10 ** 9)
    msgs = _rounds(4)
    before = len(msgs)
    loop._maybe_compact(msgs)
    assert len(msgs) == before


def test_compact_keeps_head_and_recent_rounds(monkeypatch):
    """超预算时保留 system + user + 提示 + 最近 KEEP_HISTORY_ROUNDS 轮。"""
    monkeypatch.setattr(loop, "MAX_CONTEXT_CHARS", 0)
    monkeypatch.setattr(loop, "KEEP_HISTORY_ROUNDS", 2)
    msgs = _rounds(4)
    loop._maybe_compact(msgs)

    assert len(msgs) == 2 + 1 + 2 * 2  # head + 提示 + 2 轮 × 2 条
    assert msgs[0]["role"] == "system"     # 任务定义不丢
    assert msgs[1]["role"] == "user"
    assert "较早的工具调用记录已移除" in msgs[2]["content"]
    # 保留的是最新两轮（i=2, i=3）
    tool_ids = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
    assert tool_ids == ["t2", "t3"]


def test_compact_keeps_assistant_tool_pairs(monkeypatch):
    """裁剪后 assistant 与其 tool 结果必须成对保留，不产生孤立 tool 消息。"""
    monkeypatch.setattr(loop, "MAX_CONTEXT_CHARS", 0)
    monkeypatch.setattr(loop, "KEEP_HISTORY_ROUNDS", 3)
    msgs = _rounds(5)
    loop._maybe_compact(msgs)

    roles = [m["role"] for m in msgs[3:]]  # 跳过 system / user / 提示
    for i in range(0, len(roles), 2):
        assert roles[i] == "assistant"
        assert roles[i + 1] == "tool"


# ---------- 流式累积 _accumulate_stream ----------


class _D:
    """极简属性容器，模拟 openai 流式 chunk 对象。"""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _chunk(delta):
    """构造一个含单个 choice 的流式 chunk。"""
    return _D(choices=[_D(delta=delta)])


def _tcall(index, id=None, name=None, arguments=None):
    """构造一个工具调用增量。"""
    return _D(
        index=index,
        id=id,
        function=_D(name=name, arguments=arguments),
    )


def test_accumulate_plain_text():
    content, calls = loop._accumulate_stream([
        _chunk(_D(content="你", tool_calls=None)),
        _chunk(_D(content="好", tool_calls=None)),
    ])
    assert content == "你好"
    assert calls == []


def test_accumulate_tool_call_split_across_chunks():
    """工具调用 name/arguments 分片传输时能正确拼接。"""
    chunks = [
        _chunk(_D(content=None, tool_calls=[_tcall(0, id="call_1", name="read", arguments='{"path": "')])),
        _chunk(_D(content=None, tool_calls=[_tcall(0, arguments='spec.md"}')])),
    ]
    content, calls = loop._accumulate_stream(chunks)
    assert content == ""
    assert calls == [{
        "id": "call_1",
        "type": "function",
        "function": {"name": "read", "arguments": '{"path": "spec.md"}'},
    }]


def test_accumulate_multiple_tool_calls_ordered():
    """多个工具调用按 index 排序输出。"""
    chunks = [
        _chunk(_D(content=None, tool_calls=[_tcall(1, id="b", name="write", arguments="{}")])),
        _chunk(_D(content=None, tool_calls=[_tcall(0, id="a", name="read", arguments="{}")])),
    ]
    content, calls = loop._accumulate_stream(chunks)
    assert [c["function"]["name"] for c in calls] == ["read", "write"]


def test_accumulate_skips_empty_choices():
    content, calls = loop._accumulate_stream([_D(choices=[])])
    assert content == "" and calls == []


# ---------- _maybe_compact：user 封轮 ----------


def test_compact_keeps_trailing_user_round(monkeypatch):
    """交互注入的 user 消息作为独立轮保留，不被误裁。"""
    monkeypatch.setattr(loop, "MAX_CONTEXT_CHARS", 0)
    monkeypatch.setattr(loop, "KEEP_HISTORY_ROUNDS", 2)
    msgs = _rounds(3) + [{"role": "user", "content": "用户回答"}]
    loop._maybe_compact(msgs)
    assert msgs[-1] == {"role": "user", "content": "用户回答"}


# ---------- _run_with_retry_on_messages ----------


def test_retry_on_messages_abort_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake(messages, **kwargs):
        calls["n"] += 1
        return "[ABORT] 用户中断执行。"

    monkeypatch.setattr(loop, "_run_loop", fake)
    result = loop._run_with_retry_on_messages([{"role": "user", "content": "x"}], max_retries=3)
    assert result == "[ABORT] 用户中断执行。"
    assert calls["n"] == 1


def test_retry_on_messages_api_err_not_retried(monkeypatch):
    calls = {"n": 0}

    def fake(messages, **kwargs):
        calls["n"] += 1
        return "[API-ERR] 限流"

    monkeypatch.setattr(loop, "_run_loop", fake)
    loop._run_with_retry_on_messages([{"role": "user", "content": "x"}], max_retries=3)
    assert calls["n"] == 1


def test_retry_on_messages_retries_err_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake(messages, **kwargs):
        calls["n"] += 1
        return "[ERR] 失败" if calls["n"] <= 2 else "成功了"

    monkeypatch.setattr(loop, "_run_loop", fake)
    result = loop._run_with_retry_on_messages([{"role": "user", "content": "x"}], max_retries=3)
    assert result == "成功了"
    assert calls["n"] == 3


# ---------- run_interactive ----------


def test_run_interactive_non_interactive_degrades(monkeypatch):
    """ENABLED=False 时退化为单次 run / run_with_retry。"""
    monkeypatch.setattr(interactive, "ENABLED", False)
    captured = {}

    def fake_run(sp, um, **kwargs):
        captured["run"] = True
        return "run-result"

    monkeypatch.setattr(loop, "run", fake_run)
    assert loop.run_interactive("sp", "um", retry=False) == "run-result"
    assert captured.get("run")


def test_run_interactive_dialogue_flow(monkeypatch):
    """多轮对话：问题→回答→问题→回答→[DONE]，回答累积进历史。"""
    monkeypatch.setattr(interactive, "ENABLED", True)
    answers = iter(["Python", "网页"])
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: next(answers))
    results = iter(["用什么语言？", "命令行还是网页？", "[DONE] 已写入 spec.md"])
    seen: list[list[str]] = []

    def fake_run_loop(messages, **kwargs):
        seen.append([m["content"] for m in messages if m["role"] == "user"])
        return next(results)

    monkeypatch.setattr(loop, "_run_loop", fake_run_loop)
    out = loop.run_interactive("sp", "帮我写游戏", retry=False)
    assert out == "[DONE] 已写入 spec.md"
    # 第 1 轮只有初始任务；第 2 轮含第一个回答；第 3 轮含两个回答
    assert seen[0] == ["帮我写游戏"]
    assert seen[1] == ["帮我写游戏", "Python"]
    assert seen[2] == ["帮我写游戏", "Python", "网页"]


def test_run_interactive_exit_aborts(monkeypatch):
    monkeypatch.setattr(interactive, "ENABLED", True)
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "exit")
    monkeypatch.setattr(loop, "_run_loop", lambda messages, **kw: "一个问题")
    out = loop.run_interactive("sp", "um", retry=False)
    assert out == "[ABORT] 用户主动退出对话。"


def test_run_interactive_code_autonomous(monkeypatch):
    """code（retry=True）自主执行：跑完一轮即返回，不进入对话循环等回答。"""
    monkeypatch.setattr(interactive, "ENABLED", True)
    calls = {"n": 0}

    def fake_retry(messages, **kwargs):
        calls["n"] += 1
        return "[DONE] 全部模块完成"

    monkeypatch.setattr(loop, "_run_with_retry_on_messages", fake_retry)

    def _should_not_prompt(prompt):
        raise AssertionError("code 自主执行不应等用户回答")
    monkeypatch.setattr(interactive, "prompt_human", _should_not_prompt)

    out = loop.run_interactive("sp", "um", retry=True)
    assert out == "[DONE] 全部模块完成"
    assert calls["n"] == 1  # 只跑一轮
