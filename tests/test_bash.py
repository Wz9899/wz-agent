"""bash 工具单元测试：危险命令拦截 + auto/plan 双模式状态机。"""

import os
import subprocess

import pytest

from agent.tools.bash import BashTool


@pytest.fixture
def tool() -> BashTool:
    return BashTool()


# ---------- auto 模式 ----------


def test_auto_executes_echo(tool):
    out = tool.run("echo hello")
    assert "hello" in out


def test_bash_syntax_works(tool):
    """bash 语法（POSIX 重定向/管道）可用 —— Windows 下应真用 bash 而非 cmd。

    回归背景: Windows 的 shell=True 走 cmd.exe，/dev/null 重定向直接报
    “系统找不到指定的路径”，LLM 生成的 bash 语法全部失败。
    """
    if os.name == "nt" and not BashTool._bash_available():
        pytest.skip("本机无 bash（非 git-bash 环境），退回 cmd 路径")
    out = tool.run("echo old > /dev/null && echo bash-syntax-ok | cat")
    assert "bash-syntax-ok" in out


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


# ---------- Windows 编码崩溃回归 ----------


def test_execute_handles_none_streams(monkeypatch):
    """子进程 stdout/stderr 为 None 时不崩溃（Windows 编码失败曾导致 NoneType.strip）。"""
    tool = BashTool()

    class _Fake:
        pid = 999
        def __init__(self, *a, **k):
            pass
        def communicate(self, timeout=None):
            return None, None

    monkeypatch.setattr("agent.tools.bash.subprocess.Popen", _Fake)
    out = tool._execute_one("some command")
    assert "无输出" in out


def test_execute_handles_stderr_content(monkeypatch):
    """stderr 有内容时正常拼接进结果（含 [stderr] 标记）。"""
    tool = BashTool()

    class _Fake:
        pid = 999
        def __init__(self, *a, **k):
            pass
        def communicate(self, timeout=None):
            return "ok", "some error"

    monkeypatch.setattr("agent.tools.bash.subprocess.Popen", _Fake)
    out = tool._execute_one("some command")
    assert "[stderr]" in out
    assert "some error" in out


def test_execute_timeout_kills_process_tree(monkeypatch):
    """超时返回 [ERR] 超时，并调用 _kill_process_tree 杀整棵进程树。"""
    tool = BashTool()

    class _Fake:
        pid = 777
        def __init__(self, *a, **k):
            pass
        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="x", timeout=timeout)

    monkeypatch.setattr("agent.tools.bash.subprocess.Popen", _Fake)
    killed = []
    monkeypatch.setattr(tool, "_kill_process_tree", lambda proc: killed.append(proc.pid))
    out = tool._execute_one("some long command")
    assert "超时" in out
    assert killed == [777]
