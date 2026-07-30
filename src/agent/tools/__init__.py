"""工具注册表 —— 统一管理所有可用工具。"""

from agent.tools.base import BaseTool
from agent.tools.read import ReadTool
from agent.tools.write import WriteTool
from agent.tools.edit import EditTool
from agent.tools.bash import BashTool

# 按名称索引的工具实例
ALL_TOOLS: dict[str, BaseTool] = {}


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


_register(ReadTool())
_register(WriteTool())
_register(EditTool())
_register(BashTool())
