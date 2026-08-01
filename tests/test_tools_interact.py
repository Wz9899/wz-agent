"""ask_user / checkpoint 交互工具单元测试（含非交互退化）。"""

from agent import interactive
from agent.tools.interact import AskUserTool, CheckpointTool


# ---------- AskUserTool ----------


def test_ask_user_non_interactive_degrades(monkeypatch):
    """非交互模式返回提示，绝不调用 prompt_human（不阻塞）。"""
    monkeypatch.setattr(interactive, "ENABLED", False)

    def _should_not_call(prompt):
        raise AssertionError("非交互模式不应等待输入")
    monkeypatch.setattr(interactive, "prompt_human", _should_not_call)

    out = AskUserTool().run("用什么语言？")
    assert "非交互模式" in out


def test_ask_user_returns_answer(monkeypatch):
    monkeypatch.setattr(interactive, "ENABLED", True)
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "Python")
    assert AskUserTool().run("用什么语言？") == "Python"


def test_ask_user_empty_answer(monkeypatch):
    # prompt_human 内部已 strip，空输入返回 ""（模拟真实行为）
    monkeypatch.setattr(interactive, "ENABLED", True)
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "")
    out = AskUserTool().run("用什么语言？")
    assert out == "(用户未提供回答)"


# ---------- CheckpointTool（非阻塞汇报）----------


def test_checkpoint_non_interactive_skips(monkeypatch):
    monkeypatch.setattr(interactive, "ENABLED", False)
    out = CheckpointTool().run("模块1完成")
    assert out == "(非交互模式) checkpoint 跳过，继续执行。"


def test_checkpoint_non_blocking_reports(monkeypatch):
    """checkpoint 非阻塞：汇报进度，不等待用户输入。"""
    monkeypatch.setattr(interactive, "ENABLED", True)

    def _should_not_call(prompt):
        raise AssertionError("checkpoint 不应等待输入")
    monkeypatch.setattr(interactive, "prompt_human", _should_not_call)

    out = CheckpointTool().run("模块1完成")
    assert "进度已汇报" in out
