"""read 工具 —— 读取文件内容，支持按行范围读取。"""

import re

from agent.tools.base import BaseTool


def _parse_lines(spec: str) -> tuple[int, int] | None:
    """解析行范围 "1-50" / "40" → (start, end)；空或非法返回 None。"""
    if not spec:
        return None
    m = re.match(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$", spec)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    if start < 1:
        return None
    return start, end


class ReadTool(BaseTool):
    """读取指定路径的文件内容。

    属性:
        MAX_CHARS: 无 lines 参数时单次读取的最大字符数，超出自动截断。
    """

    # 类级别常量，便于外部调整
    MAX_CHARS: int = 3000

    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return (
            "读取指定路径的文件内容。可用 lines 参数按行范围读取"
            "（如 \"1-50\" 读 1-50 行、\"40\" 读第 40 行），适合大文件分段查看；"
            "不传 lines 时返回文件开头（超长自动截断）。"
        )

    def run(self, path: str, lines: str = "") -> str:
        """读取文件，返回内容字符串或错误信息。

        参数:
            path: 文件路径。
            lines: 可选，行范围。如 "1-50" 读 1-50 行、"40" 读第 40 行；
                   为空时读取文件开头（超长自动截断）。
        """
        # ---- 1. 尝试以 UTF-8 文本模式读取 ----
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            return f"错误：文件不存在 —— {path}"
        except IsADirectoryError:
            return f"错误：{path} 是一个目录，请指定具体文件"
        except PermissionError:
            return f"错误：没有权限读取 {path}"
        except UnicodeDecodeError:
            return f"错误：{path} 不是 UTF-8 文本文件，无法读取"
        except OSError as e:
            return f"读取文件时出错（OS 错误）：{e}"
        except Exception as e:
            return f"读取文件时出错：{e}"

        # ---- 2. 指定行范围：返回该段（带行号，便于 edit 定位）----
        rng = _parse_lines(lines)
        if rng is not None:
            start, end = rng
            all_lines = content.split("\n")
            total = len(all_lines)
            if start > total:
                return f"错误：第 {start} 行超出文件总行数（共 {total} 行）"
            end = min(end, total)
            selected = all_lines[start - 1:end]
            numbered = [f"{i}: {line}" for i, line in enumerate(selected, start=start)]
            return "\n".join(numbered) + f"\n...（显示第 {start}-{end} 行，共 {total} 行）"

        # ---- 3. 截断保护：大文件只返回前 MAX_CHARS 个字符 ----
        total_chars = len(content)
        if total_chars > self.MAX_CHARS:
            content = (
                content[: self.MAX_CHARS]
                + f"\n\n... (文件共 {total_chars} 字符，以上为前 {self.MAX_CHARS} 字符)"
            )

        return content
