"""triage 工具 —— issue 列表查看与状态更新（分诊状态机）。"""

from agent import issues, paths
from agent.tools.base import BaseTool


class ListIssuesTool(BaseTool):
    """列出指定 feature 下的所有 issue 文件及当前分诊状态。"""

    @property
    def name(self) -> str:
        return "list_issues"

    @property
    def description(self) -> str:
        return (
            "列出指定 feature（.scratch/<feature>/issues/ 下）的所有 issue 文件。"
            "返回每个 issue 的完整相对路径和当前 Status，"
            "供分诊前了解全貌、以及 to-tickets 时确认已有 ticket。"
        )

    def run(self, feature: str) -> str:
        """列出 feature 下全部 issue 文件（含当前 Status）。

        参数:
            feature: feature-slug（对应 .scratch/<feature>/ 目录）。
        """
        files = issues.list_issue_files(feature)
        if not files:
            return (
                f"[INFO] feature '{feature}' 下没有 issue 文件"
                f"（{issues.issues_dir(feature)} 不存在或为空）"
            )

        lines = [f"feature '{feature}' 共 {len(files)} 个 issue:"]
        for p in files:
            status = issues.get_status(p) or "(无 Status 行)"
            rel = p.relative_to(paths.target_root())
            lines.append(f"  [{p.stem}] {rel} —— Status: {status}")
        return "\n".join(lines)


class SetIssueStatusTool(BaseTool):
    """更新 issue 的分诊状态（Status 行），可选追加判定评论。"""

    @property
    def name(self) -> str:
        return "set_issue_status"

    @property
    def description(self) -> str:
        return (
            "更新指定 issue 的分诊状态（Status 行），"
            f"合法标签: {', '.join(issues.VALID_LABELS)}。"
            "可选传入 comment 说明判定理由（追加到 ## Comments 区块）。"
            "分诊完成后用它把 issue 移到目标状态。"
        )

    def run(self, feature: str, issue: str, label: str, comment: str = "") -> str:
        """更新 issue 的状态。

        参数:
            feature: feature-slug。
            issue: issue 引用（"01"、"01-auth" 或 "01-auth.md"）。
            label: 目标分诊标签。
            comment: 判定理由（可选，追加到 ## Comments）。
        """
        try:
            path = issues.issue_path(feature, issue)
        except ValueError as e:
            # 引用命中多个文件，存在歧义 —— 让 LLM 换用完整文件名
            return f"[ERR] {e}"
        if path is None:
            return f"[ERR] 在 feature '{feature}' 中找不到 issue '{issue}'"
        return issues.set_status(path, label, comment)
