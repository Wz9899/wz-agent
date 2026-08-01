"""ask_user / checkpoint 交互工具单元测试（含非交互退化）。"""

import pytest

from agent import interactive
from agent.tools.interact import AskUserTool, CheckpointTool


def _reset_flags(monkeypatch):
    monkeypatch.setattr(interactive, "abort_requested", False)
    monkeypatch.setattr(interactive, "pending_instruction", None)


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


# ---------- CheckpointTool ----------


def test_checkpoint_non_interactive_skips(monkeypatch):
    monkeypatch.setattr(interactive, "ENABLED", False)
    _reset_flags(monkeypatch)

    out = CheckpointTool().run("模块1完成")
    assert out == "(非交互模式) checkpoint 跳过，继续执行。"
    assert interactive.abort_requested is False
    assert interactive.pending_instruction is None


def test_checkpoint_enter_continues(monkeypatch):
    monkeypatch.setattr(interactive, "ENABLED", True)
    _reset_flags(monkeypatch)
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "")

    out = CheckpointTool().run("模块1完成")
    assert "继续执行" in out
    assert interactive.abort_requested is False
    assert interactive.pending_instruction is None


def test_checkpoint_stop_aborts(monkeypatch):
    monkeypatch.setattr(interactive, "ENABLED", True)
    _reset_flags(monkeypatch)
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "stop")

    out = CheckpointTool().run("模块1完成")
    assert out.startswith("[ABORT]")
    assert interactive.abort_requested is True


def test_checkpoint_injects_instruction(monkeypatch):
    monkeypatch.setattr(interactive, "ENABLED", True)
    _reset_flags(monkeypatch)
    monkeypatch.setattr(interactive, "prompt_human", lambda prompt: "改用 golang")

    out = CheckpointTool().run("模块1完成")
    assert "新的指令" in out
    assert interactive.pending_instruction == "改用 golang"
