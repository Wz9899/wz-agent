"""agent.loop 客户端惰性初始化测试。

验证 client 在首次调用时才从环境变量构造（修复 .env 在 import 之后
加载导致的占位符问题），且之后复用同一实例。
"""

from agent import interactive

import agent.loop as loop


def test_get_client_reads_current_env(monkeypatch):
    """client 应从当前环境变量构造，且 LLM_API_KEY 优先于 DEEPSEEK_API_KEY。"""
    # 先删掉两个 key：main.py 在 import 时 load_dotenv(.env)，
    # 同进程先跑的测试会把 .env 里的 LLM_API_KEY 泄漏进 os.environ
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(loop, "_client", None)          # 重置惰性缓存
    monkeypatch.setenv("DEEPSEEK_API_KEY", "old-key")
    monkeypatch.setenv("LLM_API_KEY", "env-test-key")
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
    """两个 key 都缺失时保持占位符行为（由调用方前置校验兜底）。"""
    monkeypatch.setattr(loop, "_client", None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
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


# ---------- continue_turn（单循环会话轮次）----------


def test_continue_turn_appends_user_and_delegates(monkeypatch):
    """continue_turn 追加用户消息后交给 _run_with_retry_on_messages，不重建历史。"""
    captured = {}

    def fake_retry(messages, **kwargs):
        captured["users"] = [m["content"] for m in messages if m["role"] == "user"]
        captured["stream"] = kwargs.get("stream")
        return "ok"

    monkeypatch.setattr(loop, "_run_with_retry_on_messages", fake_retry)
    messages = [{"role": "system", "content": "sp"}]
    out = loop.continue_turn(messages, "帮我写游戏", stream=True)

    assert out == "ok"
    assert captured["users"] == ["帮我写游戏"]  # 消息已 append 进同一份历史
    assert captured["stream"] is True            # 流式开关透传


def test_continue_turn_keeps_history(monkeypatch):
    """多轮 continue_turn 共用同一份 messages（跨轮持久的单循环不变量）。"""
    seen = []

    def fake_retry(messages, **kwargs):
        seen.append([m["content"] for m in messages if m["role"] == "user"])
        # 模拟 LLM 回复入史（真实路径在 _run_loop 内部）
        messages.append({"role": "assistant", "content": "ok"})
        return "ok"

    monkeypatch.setattr(loop, "_run_with_retry_on_messages", fake_retry)
    messages = [{"role": "system", "content": "sp"}]
    loop.continue_turn(messages, "第一轮")
    loop.continue_turn(messages, "第二轮")
    assert seen == [["第一轮"], ["第一轮", "第二轮"]]


def test_run_loop_handles_invalid_json_args(monkeypatch):
    """LLM 返回非法 JSON 工具参数（写大文件时被截断）→ 不崩溃，错误返回给 LLM 后继续。"""
    responses = [
        _D(choices=[_D(message=_D(role="assistant", content=None, tool_calls=[
            _D(id="c1", type="function", function=_D(name="read", arguments='{"path": "unclosed')),
        ]))]),
        _D(choices=[_D(message=_D(role="assistant", content="任务完成", tool_calls=None))]),
    ]

    class _FakeCompletions:
        def __init__(self, resp):
            self.resp = resp
            self.i = 0
        def create(self, **kw):
            r = self.resp[self.i]
            self.i += 1
            return r

    class _FakeClient:
        def __init__(self, resp):
            self._c = _FakeCompletions(resp)
        @property
        def chat(self):
            return _D(completions=self._c)

    client = _FakeClient(responses)  # 共享同一个 client，create 按序返回
    monkeypatch.setattr(loop, "_get_client", lambda: client)
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    result = loop._run_loop(msgs, stream=False)
    assert result == "任务完成"
    # 错误消息被作为 tool 结果返回给 LLM（agent 未崩溃，LLM 可据此重试）
    assert any("[ERR] 工具 'read' 的参数不是合法 JSON" in m.get("content", "") for m in msgs)


def test_run_loop_sets_mode_on_injected_tools_only(monkeypatch):
    """tools 注入时 mode 写到该实例；另一个循环的工厂实例不受影响（v2.4 工厂语义）。"""
    from agent.tools import make_tools

    other_loop_bash = make_tools()["bash"]  # 模拟另一个循环的工具实例
    other_loop_bash.mode = "plan"
    other_loop_bash.run("echo parent")     # 它已收集一条执行计划

    injected = make_tools(["bash"])        # 本循环注入的工具集（全新实例）

    resp = _D(choices=[_D(message=_D(role="assistant", content="done", tool_calls=None))])
    client = _D(chat=_D(completions=_D(create=lambda **kw: resp)))
    monkeypatch.setattr(loop, "_get_client", lambda: client)

    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}]
    result = loop._run_loop(msgs, stream=False, tools=injected, bash_safety_mode="auto")

    assert result == "done"
    assert injected["bash"].mode == "auto"       # 模式写到注入实例
    assert other_loop_bash.mode == "plan"         # 另一循环不受影响
    assert len(other_loop_bash.plan) == 1         # 其计划未被清空
