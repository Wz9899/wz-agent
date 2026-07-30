"""write 工具 —— 创建或覆盖文件。"""

import os

from agent.tools.base import BaseTool


class WriteTool(BaseTool):
    """创建新文件或覆盖已有文件，自动创建父目录。

    注意:
        - 写入模式为覆盖（w），已有内容会被替换。
        - 如果 path 指向一个已存在的目录，会返回错误。
    """

    @property
    def name(self) -> str:
        return "write"

    @property
    def description(self) -> str:
        return (
            "创建新文件或覆盖已有文件的内容。"
            "会自动创建不存在的父目录。适合生成代码、配置文件等。"
        )

    def run(self, path: str, content: str) -> str:
        """将 content 写入 path，自动创建中间目录。

        参数:
            path: 目标文件路径（相对或绝对）。
            content: 要写入的文本内容。
        """
        # ---- 1. 路径安全：拒绝写入到已存在的目录 ----
        if os.path.isdir(path):
            return f"错误：{path} 是一个已存在的目录，请指定文件路径"

        # ---- 2. 自动创建父目录 ----
        try:
            directory = os.path.dirname(path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        except PermissionError:
            return f"错误：没有权限创建目录 {directory}"
        except OSError as e:
            return f"创建父目录时出错：{e}"

        # ---- 3. 写入文件 ----
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except PermissionError:
            return f"错误：没有权限写入 {path}"
        except IsADirectoryError:
            return f"错误：{path} 是一个目录，无法作为文件写入"
        except OSError as e:
            return f"写入文件时出错（OS 错误）：{e}"
        except Exception as e:
            return f"写入文件时出错：{e}"

        return f"✅ 文件已写入：{path}（{len(content)} 字符）"
