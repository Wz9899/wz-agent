"""工具工厂 —— 每个循环一份独立实例，互不共享可变状态。

v2.4 前是全局单例注册表（ALL_TOOLS）：bash 的 mode/_plan 是实例状态，
单例意味着所有循环共享——串行下靠"子 agent 注入独立 BashTool 实例"
的补丁活着，一旦并行派发（v2.4 扇出）就是竞态。工厂化后：

    主循环   每次调 _run_loop 时 make_tools() 一份全新实例
    子 agent make_tools(受限名单) 一份全新实例

plan 模式的生命周期天然对齐"一次 _run_loop 调用"：计划在实例内收集、
经 __execute_plan__ 执行，循环结束实例即弃——跨循环零泄漏。

TOOL_CLASSES 是名字 → 类的目录（schema 与测试的单一事实来源）；
运行时实例一律经 make_tools 构造，不走目录直接实例化。
"""

from __future__ import annotations

from agent.tools.base import BaseTool
from agent.tools.read import ReadTool
from agent.tools.write import WriteTool
from agent.tools.edit import EditTool
from agent.tools.bash import BashTool
from agent.tools.triage import ListIssuesTool, SetIssueStatusTool
from agent.tools.tickets import AllocateIssueTool
from agent.tools.interact import AskUserTool, CheckpointTool
from agent.tools.task import TaskTool

# 名字 → 工具类目录（工厂的原料表；键必须与工具的 .name 一致）
TOOL_CLASSES: dict[str, type[BaseTool]] = {
    "read": ReadTool,
    "write": WriteTool,
    "edit": EditTool,
    "bash": BashTool,
    "list_issues": ListIssuesTool,
    "set_issue_status": SetIssueStatusTool,
    "allocate_issue": AllocateIssueTool,
    "ask_user": AskUserTool,
    "checkpoint": CheckpointTool,
    # task 在目录里，但不在任何子 agent 的工具名单中 —— 递归的结构性防线
    "task": TaskTool,
}

# 全部工具名（make_tools() 不传 names 时的默认集）
ALL_TOOL_NAMES: tuple[str, ...] = tuple(TOOL_CLASSES)

# 导入期校验：键与 .name 错位、同一类挂多个键，都在这里当场暴露
for _name, _cls in TOOL_CLASSES.items():
    if _cls().name != _name:
        raise RuntimeError(f"工具目录错位：'{_name}' 键下的 {_cls.__name__}.name 是 '{_cls().name}'")


def make_tools(names: list[str] | tuple[str, ...] | None = None) -> dict[str, BaseTool]:
    """构造一组全新工具实例。

    参数:
        names: 工具名子集（子 agent 的受限工具集）；None = 全部。

    返回:
        name → 全新实例 的字典。每次调用独立构造——bash 的 mode/_plan
        等可变状态互不共享，并行调用安全。

    抛出:
        ValueError: names 含未注册的工具名（配置错误，应尽早暴露）。
    """
    selected = ALL_TOOL_NAMES if names is None else tuple(names)
    unknown = [n for n in selected if n not in TOOL_CLASSES]
    if unknown:
        raise ValueError(f"未注册的工具名：{unknown}。可选：{list(ALL_TOOL_NAMES)}")
    return {n: TOOL_CLASSES[n]() for n in selected}
