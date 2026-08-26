"""上下文管理 —— spec.md 的定位与读写。

spec.md 是编码执行的唯一权威输入（项目级上下文），v2.3 起固定在
**目标项目根**（见 agent.paths.target_root / agent.runtime.spec_path）
——spec 是项目工件，随项目走，不再随运行目录搬家。

上下文管理策略（与 CONTEXT.md 一致）：
    - spec.md 提供项目级上下文，对话被压缩后 agent 重读它恢复状态。
    - 文件系统即代码索引 —— 不预索引，靠 read 工具按需读取。

本模块只负责项目根 spec.md 的定位、读写与存在性校验。
（feature 级 spec 的定位见 agent.issues.spec_path，两者是不同概念。）
"""

from pathlib import Path

from agent import runtime

# 缺少 spec.md 时的统一提示（ensure_spec 异常与用法提示共用）
MISSING_SPEC_MESSAGE: str = (
    "spec.md 不存在。请在会话里描述你的需求，agent 澄清后会写入 spec.md；\n"
    "也可以直接手动创建 spec.md 后输入 /code 开始编码。"
)


def root_spec_path() -> Path:
    """返回目标项目根 spec.md 的完整路径。

    与 agent.issues.spec_path(slug) 不同：本函数定位项目根 spec.md
    （澄清/编码流程使用），后者定位 feature 级 spec.md（v2.0 拆解流程）。
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
    """编码前调用：spec.md 不存在则抛出清晰错误。

    返回:
        spec.md 的完整内容。

    抛出:
        FileNotFoundError: spec.md 不存在 —— 提示先做需求澄清。
    """
    content = load_spec()
    if content is None:
        raise FileNotFoundError(MISSING_SPEC_MESSAGE)
    return content
