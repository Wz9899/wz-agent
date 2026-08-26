"""task 工具（子 agent 派发）测试。

不打真实 API —— loop.run 用桩替换，验证的是派发协议：
注册表完整性、递归防线、参数透传、bash 模式继承、深度复位。
"""

import pytest

from agent.tools import ALL_TOOL_NAMES, TOOL_CLASSES, make_tools
from agent.tools.task import MAX_FAN_OUT, SUBAGENTS, TaskTool, _DEPTH


# ============================================================
# 注册表结构
# ============================================================


def test_registry_has_both_subagents():
    """两个预定义角色存在。"""
    assert set(SUBAGENTS) == {"investigator", "coder"}


def test_subagent_toolsets_are_registered_and_task_free():
    """子 agent 工具名均在目录中；且都不含 task —— 递归的结构性防线。"""
    for spec in SUBAGENTS.values():
        for name in spec.tool_names:
            assert name in TOOL_CLASSES, f"{spec.name} 引用未注册工具 {name}"
        assert "task" not in spec.tool_names, f"{spec.name} 不得含 task（递归）"


def test_investigator_is_read_only():
    """investigator 的工具集不含 write/edit —— 只读边界。"""
    assert set(SUBAGENTS["investigator"].tool_names) == {"read", "bash"}


def test_task_tool_in_catalog():
    """task 在工具目录中（主 agent 可见）。"""
    assert "task" in TOOL_CLASSES


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
    """验证传给子循环的参数: 注册表定义透传 + 受限工具集 + 全新工具实例 + 强制 auto。"""
    import agent.loop as loop_mod

    captured: dict = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return "调查结论: 问题在 loop.py"

    monkeypatch.setattr(loop_mod, "run", _fake_run)

    spec = SUBAGENTS["investigator"]

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


def test_subagent_gets_isolated_bash_instance(monkeypatch):
    """子 agent 的工具实例由工厂全新构造：bash 独立、默认 auto，不碰调用方的状态。"""
    import agent.loop as loop_mod

    captured: dict = {}

    def _fake_run(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(loop_mod, "run", _fake_run)

    # 模拟父循环：自己的 bash 实例处于 plan 模式且已收集一条计划
    parent_bash = make_tools()["bash"]
    parent_bash.mode = "plan"
    parent_bash.run("echo parent-cmd")

    TaskTool().run(task="t", subagent="investigator")

    sub_bash = captured["tools"]["bash"]
    assert sub_bash is not parent_bash      # 全新实例，不共享 _plan/_mode
    assert sub_bash.mode == "auto"          # 工厂新实例默认 auto
    assert parent_bash.mode == "plan"       # 父循环模式未被翻转
    assert len(parent_bash.plan) == 1       # 父循环计划未被清空/污染


# ---------- 工厂（v2.4）----------


def test_make_tools_returns_fresh_instances():
    """每次 make_tools() 返回全新实例 —— 并行循环互不共享可变状态。"""
    a = make_tools()
    b = make_tools()
    assert set(a) == set(ALL_TOOL_NAMES)
    for name, tool in a.items():
        assert tool is not b[name]


def test_make_tools_restricted_subset():
    """受限名单：只含指定工具，未知名报配置错误。"""
    tools = make_tools(["read", "bash"])
    assert set(tools) == {"read", "bash"}
    with pytest.raises(ValueError):
        make_tools(["read", "no-such-tool"])


def test_make_tools_instances_are_stateless_fresh():
    """两个循环各自 make_tools 后，一个改 bash mode 不影响另一个（竞态修复的核心）。"""
    tools_a = make_tools()
    tools_b = make_tools()
    tools_a["bash"].mode = "plan"
    tools_a["bash"].run("echo collected")
    assert tools_b["bash"].mode == "auto"     # b 不受 a 影响
    assert len(tools_b["bash"].plan) == 0


# ============================================================
# 并行扇出（v2.4）
# ============================================================


def test_schema_fan_out_is_optional_array():
    """fan_out 是可选参数且类型为 array（base.py 的 list/Optional 推断）。"""
    schema = TaskTool().to_openai_function()
    props = schema["function"]["parameters"]["properties"]
    assert props["fan_out"]["type"] == "array"
    assert "fan_out" not in schema["function"]["parameters"]["required"]
    assert "fan_out" in schema["function"]["description"]  # LLM 能看到并行用法


def test_fan_out_happy_path_aggregates_in_order(monkeypatch):
    """扇出：每个子问题一个子 agent，结果按子问题原序（非完成序）聚合。"""
    import agent.loop as loop_mod
    import agent.tools as tools_mod

    calls: list[str] = []
    tool_sets: list[dict] = []

    def _fake_run(**kwargs):
        calls.append(kwargs["user_message"])
        tool_sets.append(kwargs["tools"])
        # 从任务描述里提取子问题编号，模拟乱序完成（3 先返回）
        for q in ("问题3", "问题1", "问题2"):
            if q in kwargs["user_message"]:
                return f"结论[{q}]"
        return "?"

    monkeypatch.setattr(loop_mod, "run", _fake_run)

    result = TaskTool().run(
        task="调查项目结构",
        subagent="investigator",
        fan_out=["问题1：入口在哪", "问题2：数据流", "问题3：测试覆盖"],
    )

    assert len(calls) == 3                       # 三个子 agent
    assert "调查项目结构" in calls[0]              # 共享背景在每个任务里
    assert "问题3" not in calls[0].split("=====")[0]  # 子问题不串台
    # 按原序聚合：无论完成顺序，段落顺序 == fan_out 顺序
    i1, i2, i3 = result.index("问题1"), result.index("问题2"), result.index("问题3")
    assert i1 < i2 < i3
    assert "结论[问题1]" in result and "结论[问题3]" in result
    assert _DEPTH == 0                            # 深度复位
    for ts in tool_sets:
        assert set(ts) == {"read", "bash"}        # 每线程受限工具集
    # 每线程全新实例（线程安全前提）
    assert tool_sets[0]["bash"] is not tool_sets[1]["bash"]


def test_fan_out_rejects_write_agent(monkeypatch):
    """只读护栏：coder（有 write/edit）不允许扇出。"""
    import agent.loop as loop_mod
    called = []
    monkeypatch.setattr(loop_mod, "run", lambda **kw: called.append(kw))

    result = TaskTool().run(task="t", subagent="coder", fan_out=["a", "b"])
    assert result.startswith("[ERR]")
    assert "不允许并行" in result
    assert called == []                           # 未起任何子 agent


def test_fan_out_rejects_too_many(monkeypatch):
    """成本护栏：超过 MAX_FAN_OUT 拒绝。"""
    import agent.loop as loop_mod
    called = []
    monkeypatch.setattr(loop_mod, "run", lambda **kw: called.append(kw))

    result = TaskTool().run(
        task="t", subagent="investigator",
        fan_out=[f"q{i}" for i in range(MAX_FAN_OUT + 1)],
    )
    assert result.startswith("[ERR]")
    assert called == []


def test_fan_out_single_question_works(monkeypatch):
    """fan_out 只有一个子问题也能跑（退化为单线程并行路径）。"""
    import agent.loop as loop_mod
    monkeypatch.setattr(loop_mod, "run", lambda **kw: "只问一个的结论")

    result = TaskTool().run(task="背景", subagent="investigator", fan_out=["唯一问题"])
    assert "只问一个的结论" in result
    assert "1/1" in result
