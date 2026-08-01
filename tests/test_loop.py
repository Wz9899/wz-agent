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
