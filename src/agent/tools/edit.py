"""edit 工具 —— 精确文本匹配替换。"""

from agent.tools.base import BaseTool


class EditTool(BaseTool):
    """在文件中查找指定文本并替换为新文本，要求精确匹配。

    安全约束:
        1. oldText 必须在文件中恰好出现 1 次，否则拒绝操作。
        2. oldText 和 newText 不能相同 —— 无意义的替换会被拒绝。
        3. 替换后告知 LLM 修改发生在第几行。
    """

    @property
    def name(self) -> str:
        return "edit"

    @property
    def description(self) -> str:
        return (
            "在文件中精确查找一段文本并替换为新文本。"
            "oldText 必须在文件中唯一存在（精确匹配，包括空格和换行），"
            "否则操作会失败。适合局部修改已有文件，避免重写整个文件。"
        )

    def run(self, path: str, oldText: str, newText: str) -> str:
        """在 path 文件中查找 oldText 并替换为 newText。

        参数:
            path: 要编辑的文件路径。
            oldText: 要被替换的原始文本（必须精确匹配且唯一）。
            newText: 替换后的新文本。
        """
        # ---- 0. 无意义替换保护 ----
        if oldText == newText:
            return "错误：oldText 和 newText 完全相同，无需替换"

        # ---- 1. 读取原文件 ----
        try:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
        except FileNotFoundError:
            return f"错误：文件不存在 —— {path}"
        except UnicodeDecodeError:
            return f"错误：{path} 不是 UTF-8 文本文件，无法编辑"
        except PermissionError:
            return f"错误：没有权限读取 {path}"
        except OSError as e:
            return f"读取文件时出错：{e}"

        # ---- 2. 检查 oldText 出现次数 ----
        count = original.count(oldText)

        if count == 0:
            return (
                f"错误：未在 {path} 中找到指定的 oldText。"
                f"请确认文本内容与文件中完全一致（包括空格和换行）。"
            )
        if count > 1:
            return (
                f"错误：oldText 在 {path} 中出现了 {count} 次（必须唯一）。"
                f"请提供更长的上下文使其唯一。"
            )

        # ---- 3. 计算行号（在替换前计算，确保准确） ----
        line_no = original[: original.index(oldText)].count("\n") + 1

        # ---- 4. 执行替换 ----
        modified = original.replace(oldText, newText, 1)

        # ---- 5. 写回文件 ----
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(modified)
        except PermissionError:
            return f"错误：没有权限写入 {path}"
        except OSError as e:
            return f"写入文件时出错：{e}"

        return (
            f"✅ 已在 {path} 第 {line_no} 行完成替换。"
            f"（old: {len(oldText)} 字符 → new: {len(newText)} 字符）"
        )
