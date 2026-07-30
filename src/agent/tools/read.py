"""read 工具 —— 读取文件内容。"""

from agent.tools.base import BaseTool


class ReadTool(BaseTool):
    """读取指定路径的文件内容，返回纯文本。

    属性:
        MAX_CHARS: 单次读取的最大字符数，超出自动截断。
    """

    # 类级别常量，便于外部调整
    MAX_CHARS: int = 3000

    @property
    def name(self) -> str:
        return "read"

    @property
    def description(self) -> str:
        return (
            "读取指定路径的文件内容。"
            "适合在编写代码前先了解已有的文件内容，或在多步操作中确认修改结果。"
        )

    def run(self, path: str) -> str:
        """读取文件，返回内容字符串或错误信息。

        超过 MAX_CHARS 的内容会被截断，并在末尾附加提示信息。
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

        # ---- 2. 截断保护：大文件只返回前 MAX_CHARS 个字符 ----
        total_chars = len(content)      # 先保存原始长度，因为后面 content 会被重新赋值
        if total_chars > self.MAX_CHARS:
            content = (
                content[: self.MAX_CHARS]
                + f"\n\n... (文件共 {total_chars} 字符，以上为前 {self.MAX_CHARS} 字符)"
            )

        return content
