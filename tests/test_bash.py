"""bash 工具单元测试：危险命令拦截 + auto/plan 双模式状态机。"""

import pytest

from agent.tools.bash import BashTool


@pytest.fixture
def tool() -> BashTool:
    return BashTool()


# ---------- auto 模式 ----------


def test_auto_executes_echo(tool):
    out = tool.run("echo hello")
    assert "hello" in out


def test_dangerous_commands_blocked(tool):
    for cmd in ("rm -rf /", "rm -rf ~", "dd if=/dev/zero of=/dev/sda", "mkfs.ext4 /dev/sda"):
        out = tool.run(cmd)
        assert "[ERR] 安全拦截" in out, f"命令未被拦截: {cmd}"


def test_plan_execution_checks_dangerous(tool, monkeypatch):
    """plan 模式执行阶段同样做安全检查，危险命令不落地执行。"""
    tool.mode = "plan"
    tool.run("echo hi")       # 安全命令
    tool.run("rm -rf /")      # 危险命令
    executed: list[str] = []

    def fake_execute(cmd: str) -> str:
        executed.append(cmd)
        return "ok"

    monkeypatch.setattr(tool, "_execute_one", fake_execute)
    out = tool.run("__execute_plan__")
    assert "[ERR] 安全拦截" in out
    assert executed == ["echo hi"]  # 只有安全命令被真实执行


# ---------- plan 模式 ----------


def test_plan_records_and_shows(tool):
    tool.mode = "plan"
    assert "[PLAN] 已记录" in tool.run("echo a", reason="测试")
    out = tool.run("__show_plan__")
    assert "echo a" in out
    assert "1" in out


def test_plan_show_empty(tool):
    tool.mode = "plan"
    out = tool.run("__show_plan__")
    assert "为空" in out


def test_plan_execute_clears_plan(tool, monkeypatch):
    tool.mode = "plan"
    tool.run("echo a")
    tool.run("echo b")
    monkeypatch.setattr(tool, "_execute_one", lambda cmd: f"ok:{cmd}")
    out = tool.run("__execute_plan__")
    assert "[DONE]" in out
    assert "2 条" in out
    assert tool.plan == []  # 执行后清空


def test_plan_clear(tool):
    tool.mode = "plan"
    tool.run("echo a")
    out = tool.run("__clear_plan__")
    assert "已清空" in out
    assert tool.plan == []


# ---------- mode 切换 ----------


def test_mode_validation():
    with pytest.raises(ValueError):
        BashTool().mode = "invalid"


def test_mode_switch_clears_plan(tool):
    tool.mode = "plan"
    tool.run("echo a")
    tool.mode = "auto"  # 切换模式清空计划
    assert tool.plan == []


def test_plan_description_mentions_special_commands(tool):
    tool.mode = "plan"
    assert "__execute_plan__" in tool.description
    tool.mode = "auto"
    assert "__execute_plan__" not in tool.description
