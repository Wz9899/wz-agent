"""to-tickets 工具 —— 为 ticket 分配唯一编号。"""

from agent import issues
from agent.tools.base import BaseTool


class AllocateIssueTool(BaseTool):
    """为 feature 分配下一个可用的 issue 编号（写 ticket 前调用）。"""

    @property
    def name(self) -> str:
        return "allocate_issue"

    @property
    def description(self) -> str:
        return (
            "为指定 feature 分配下一个可用的 issue 编号（从 01 开始，"
            "自动跳过已占用的编号）。每次写一个新 ticket 文件之前调用一次，"
            "用返回的编号拼入文件名：<编号>-<slug>.md。"
            "编号由代码保证唯一，不要自己猜测编号。"
        )

    def run(self, feature: str) -> str:
        """返回下一个可用编号。

        参数:
            feature: feature-slug（对应 .scratch/<feature>/ 目录）。
        """
        n = issues.next_issue_number(feature)
        return f"下一个可用编号: {n:02d} —— 请把 ticket 文件命名为 {n:02d}-<slug>.md"
