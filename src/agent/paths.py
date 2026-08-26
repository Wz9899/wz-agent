"""路径常量与目标锚定 —— 单一事实来源。

两个"根"：
    PROJECT_ROOT  wz-agent 自身（runs/ 转录目录、.env 的定位基准）
    TARGET_ROOT   目标项目 —— agent 实际工作的目录（-C 指定，默认启动
                  时所在目录）。spec.md、.scratch/、生成的代码都落在这里。

此前 PROJECT_ROOT 在 context.py / issues.py / main.py 各自用不同深度
的 parent.parent(.parent) 计算，容易写错层级。现在收敛到一处。
"""

from __future__ import annotations

import os
from pathlib import Path

# wz-agent 项目根目录 = src/agent/paths.py 的上一级的上一级的上一级
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# .scratch/ 根目录名（固定在目标项目根目录下）
SCRATCH_DIRNAME: str = ".scratch"

# spec.md 文件名
SPEC_FILENAME: str = "spec.md"

# 目标项目根 —— None 表示未锚定（回退 PROJECT_ROOT，兼容测试与旧调用）
TARGET_ROOT: Path | None = None


def set_target(path: Path) -> Path:
    """锚定目标项目目录并切换工作目录。

    之后 read/write/edit/bash 的相对路径、spec.md、.scratch/ 都以目标
    项目为基准——wz-agent 直接在用户的项目上工作（v2.3 锚定模型），
    不再有 runs/<ts>/output/ 沙箱。

    抛出:
        FileNotFoundError: 路径不存在或不是目录。
    """
    global TARGET_ROOT
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"目标项目目录不存在或不是目录：{resolved}")
    TARGET_ROOT = resolved
    os.chdir(resolved)  # 工具（read/write/edit/bash）的相对路径全部随锚定走
    return resolved


def target_root() -> Path:
    """返回目标项目根；未锚定时回退 wz-agent 自身根（兼容未走 set_target 的调用）。"""
    return TARGET_ROOT if TARGET_ROOT is not None else PROJECT_ROOT
