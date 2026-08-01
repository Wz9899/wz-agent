"""agent.loop 客户端惰性初始化测试。

验证 client 在首次调用时才从环境变量构造（修复 .env 在 import 之后
加载导致的占位符问题），且之后复用同一实例。
"""

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
