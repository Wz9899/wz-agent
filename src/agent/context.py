"""上下文管理 —— spec.md 的读写与定位。

spec.md 是编码执行阶段的唯一输入（项目级上下文），存放在**本次运行的
独立目录**（runs/<时间戳>/spec.md，见 agent.runtime）。

上下文管理策略（与 CONTEXT.md 一致）：
    - spec.md 提供项目级上下文，编码阶段启动时自动注入。
    - 文件系统即代码索引 —— 不预索引，靠 read 工具按需读取已生成文件。

本模块只负责运行目录 spec.md 的定位、读写与存在性校验。
（feature 级 spec 的定位见 agent.issues.spec_path，两者是不同概念。）
"""

from pathlib import Path

from agent import runtime

# 缺少 spec.md 时的统一提示（ensure_spec 异常与 main.py 用法提示共用）
MISSING_SPEC_MESSAGE: str = (
    "spec.md 不存在。请先运行需求澄清阶段：\n"
    '    python src/main.py "你的需求"\n'
    "确认 spec.md 内容无误后，再运行：\n"
    '    python src/main.py --phase code "请根据 spec.md 实现项目"'
)


def root_spec_path() -> Path:
    """返回本次运行目录 spec.md 的完整路径。

    与 agent.issues.spec_path(slug) 不同：本函数定位运行根级 spec.md
    （澄清/编码流程使用），后者定位 feature 级 spec.md（v2.0 拆解流程）。
    路径随每次运行变化：runs/<时间戳>/spec.md。
    """
    return runtime.spec_path()


def spec_exists() -> bool:
    """根目录 spec.md 是否已存在。"""
    return root_spec_path().is_file()


def load_spec() -> str | None:
    """读取根目录 spec.md 内容；文件不存在时返回 None。"""
    path = root_spec_path()
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def ensure_spec() -> str:
    """编码阶段前调用：spec.md 不存在则抛出清晰错误。

    返回:
        spec.md 的完整内容。

    抛出:
        FileNotFoundError: spec.md 不存在 —— 提示用户先运行需求澄清阶段。
    """
    content = load_spec()
    if content is None:
        raise FileNotFoundError(MISSING_SPEC_MESSAGE)
    return content
