"""工具注册表 —— 统一管理所有可用工具。"""

from agent.tools.base import BaseTool
from agent.tools.read import ReadTool
from agent.tools.write import WriteTool
from agent.tools.edit import EditTool
from agent.tools.bash import BashTool
from agent.tools.triage import ListIssuesTool, SetIssueStatusTool
from agent.tools.tickets import AllocateIssueTool
from agent.tools.interact import AskUserTool, CheckpointTool
from agent.tools.task import TaskTool

# 按名称索引的工具实例
ALL_TOOLS: dict[str, BaseTool] = {}

# 对 BashTool 的强引用（loop.py 需要它来切换安全模式）
_BASH_TOOL: BashTool | None = None


def _register(tool: BaseTool) -> None:
    """把工具实例注册到全局表中。

    如果同名工具已存在，说明注册了重复的工具，应立即暴露问题。
    """
    if tool.name in ALL_TOOLS:
        raise ValueError(
            f"工具名冲突：'{tool.name}' 已被 {ALL_TOOLS[tool.name].__class__.__name__} 注册，"
            f"无法再注册 {tool.__class__.__name__}"
        )
    ALL_TOOLS[tool.name] = tool


def get_bash_tool() -> BashTool:
    """返回 BashTool 的单例实例，用于运行时切换安全模式。"""
    global _BASH_TOOL
    if _BASH_TOOL is None:
        raise RuntimeError("BashTool 尚未初始化 —— 请先调用 _register(BashTool())")
    return _BASH_TOOL


_register(ReadTool())
_register(WriteTool())
_register(EditTool())

_bash = BashTool()
_BASH_TOOL = _bash
_register(_bash)

_register(ListIssuesTool())
_register(SetIssueStatusTool())
_register(AllocateIssueTool())

_register(AskUserTool())
_register(CheckpointTool())

# task 最后注册 —— 它延迟依赖 agent.loop，而 loop 依赖本注册表
_register(TaskTool())
