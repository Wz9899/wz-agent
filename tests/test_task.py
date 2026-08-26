"""task 工具（子 agent 派发）测试。

不打真实 API —— loop.run 用桩替换，验证的是派发协议：
注册表完整性、递归防线、参数透传、bash 模式继承、深度复位。
"""

import pytest

from agent.tools import ALL_TOOLS, get_bash_tool
from agent.tools.task import SUBAGENTS, TaskTool, _DEPTH


# ============================================================
# 注册表结构
# ============================================================


def test_registry_has_both_subagents():
    """两个预定义角色存在。"""
    assert set(SUBAGENTS) == {"investigator", "coder"}


def test_subagent_toolsets_are_registered_and_task_free():
    """子 agent 工具名均已在全局注册表；且都不含 task —— 递归的结构性防线。"""
    for spec in SUBAGENTS.values():
        for name in spec.tool_names:
            assert name in ALL_TOOLS, f"{spec.name} 引用未注册工具 {name}"
        assert "task" not in spec.tool_names, f"{spec.name} 不得含 task（递归）"


def test_investigator_is_read_only():
    """investigator 的工具集不含 write/edit —— 只读边界。"""
    assert set(SUBAGENTS["investigator"].tool_names) == {"read", "bash"}


def test_task_tool_registered():
    """task 工具已注册进全局注册表（主 agent 可见）。"""
    assert "task" in ALL_TOOLS


# ============================================================
# schema 自动生成
# ============================================================


def test_schema_params():
    """schema: 必填 task/subagent，描述中列出可选角色。"""
    schema = TaskTool().to_openai_function()
    fn = schema["function"]
    assert fn["name"] == "task"
    assert set(fn["parameters"]["required"]) == {"task", "subagent"}
    for role in SUBAGENTS:  # 描述动态拼接，必须让 LLM 看到全部角色
        assert role in fn["description"]


# ============================================================
# 参数校验
# ============================================================


def test_unknown_subagent_returns_error_with_options():
    result = TaskTool().run(task="调查X", subagent="nope")
    assert result.startswith("[ERR]")
    for role in SUBAGENTS:
        assert role in result  # 错误信息列出可选项，供 LLM 自修正


def test_empty_task_rejected():
    result = TaskTool().run(task="   ", subagent="investigator")
    assert result.startswith("[ERR]")


# ============================================================
# 深度守卫
# ============================================================


def test_depth_guard_blocks_nested_dispatch():
    """深度 >= 1 时拒绝派发（注册表隔离之外的第二道防线）。"""
    import agent.tools.task as task_mod

    task_mod._DEPTH = 1
    try:
        result = TaskTool().run(task="子任务", subagent="coder")
        assert result.startswith("[ERR]")
        assert "递归" in result
    finally:
        task_mod._DEPTH = 0


def test_depth_reset_after_loop_crash(monkeypatch):
    """子循环抛异常时深度也必须复位（finally），否则后续派发全被拒。"""
    import agent.loop as loop_mod

    def _boom(**kwargs):
        raise RuntimeError("子循环崩溃")

    monkeypatch.setattr(loop_mod, "run", _boom)
    tool = TaskTool()
    with pytest.raises(RuntimeError):
        tool.run(task="t", subagent="investigator")
    assert _DEPTH == 0


# ============================================================
# 派发协议（loop.run 桩）
# ============================================================


def test_dispatch_protocol(monkeypatch):
    """验证传给子循环的参数: 注册表定义透传 + 受限工具集 + 独立 bash 实例 + 强制 auto。"""
    import agent.loop as loop_mod

    captured: dict = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return "调查结论: 问题在 loop.py"

    monkeypatch.setattr(loop_mod, "run", _fake_run)

    spec = SUBAGENTS["investigator"]
    get_bash_tool().mode = "plan"  # 父循环处于 plan 模式 —— 子循环不得继承/污染

    result = TaskTool().run(task="调查编辑工具的实现", subagent="investigator")

    assert result == "调查结论: 问题在 loop.py"        # 返回值透传
    assert captured["system_prompt"] == spec.system_prompt
    assert captured["user_message"] == "调查编辑工具的实现"
    assert captured["max_steps"] == spec.max_steps
    assert captured["bash_safety_mode"] == "auto"       # 强制 auto，不继承 plan
    assert captured["stream"] is False
    assert set(captured["tools"]) == set(spec.tool_names)
    assert "task" not in captured["tools"]              # 受隔离
    assert _DEPTH == 0                                  # 执行完深度复位

    get_bash_tool().mode = "auto"  # 还原全局单例状态


def test_subagent_gets_isolated_bash_instance(monkeypatch):
    """子 agent 的 bash 是独立实例，且不改变父循环（全局单例）的 plan 状态。"""
    import agent.loop as loop_mod

    captured: dict = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(loop_mod, "run", _fake_run)

    parent_bash = get_bash_tool()
    parent_bash.mode = "plan"
    parent_bash.run("echo parent-cmd")  # 父循环已收集一条执行计划

    TaskTool().run(task="t", subagent="investigator")

    sub_bash = captured["tools"]["bash"]
    assert sub_bash is not parent_bash      # 独立实例，不共享 _plan/_mode
    assert sub_bash.mode == "auto"          # 新实例默认 auto
    assert parent_bash.mode == "plan"       # 父循环模式未被翻转
    assert len(parent_bash.plan) == 1       # 父循环计划未被清空/污染

    parent_bash.mode = "auto"  # 还原全局单例状态
