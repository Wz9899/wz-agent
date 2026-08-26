"""运行上下文 —— 转录目录管理 + 目标项目的产物定位。

v2.3 锚定模型下的职责划分：
    - 目标项目的产物（spec.md、.scratch/、生成的代码）落在目标项目里
      （见 agent.paths.target_root），本模块只做路径定位；
    - wz-agent 自己的观测记录（session.log 流式回放）留在 wz-agent 的
      runs/ 下，不污染目标项目；目录名带目标项目 slug，多项目可分辨。

运行结束后打开 runs/<时间戳>_<项目名>/session.log，就能回看 agent 全程
做了什么、出了什么问题，方便定位和修改。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TextIO

from agent import paths
from agent.paths import PROJECT_ROOT

# runs/ 根目录（固定在 wz-agent 项目根下）
RUNS_DIR: Path = PROJECT_ROOT / "runs"

# 当前运行目录（start_run 设置，未设置时惰性创建）
_current: Path | None = None

# 当前运行的转录文件句柄（session.log）
_transcript: TextIO | None = None


def _slugify(name: str) -> str:
    """把目标项目目录名压成可放进目录名的 slug（Windows 安全字符）。"""
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", name).strip("-")
    return slug[:30]


def start_run(existing: Path | None = None) -> Path:
    """创建本次运行的转录目录，或复用指定目录（调试场景）。

    目录名：runs/<时间戳>_<目标项目名>/ —— 转录按项目可分辨。
    v2.3 起 runs/ 下只有 session.log（代码与 spec 都直接落目标项目），
    不再创建 output/ 沙箱。
    """
    global _current, _transcript
    if existing is not None:
        _current = existing
        _current.mkdir(parents=True, exist_ok=True)
        _transcript = open(_current / "session.log", "a", encoding="utf-8", errors="replace")
        return _current
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _slugify(paths.target_root().name)
    _current = RUNS_DIR / (f"{ts}_{slug}" if slug else ts)
    _current.mkdir(parents=True, exist_ok=True)
    _transcript = open(_current / "session.log", "w", encoding="utf-8", errors="replace")
    return _current


def current() -> Path:
    """当前运行目录；未显式 start 时惰性创建（保证转录总能写入）。"""
    global _current
    if _current is None:
        _current = start_run()
    return _current


def spec_path() -> Path:
    """spec.md 路径 —— 目标项目根下（spec 是项目工件，随项目走）。"""
    return paths.target_root() / paths.SPEC_FILENAME


def write_transcript(text: str) -> None:
    """把一段终端可见文本追加到 session.log（agent 流式输出的回放）。"""
    if _transcript:
        _transcript.write(text)
        _transcript.flush()


def close_run() -> None:
    """结束本次运行，关闭 session.log。"""
    global _transcript
    if _transcript:
        _transcript.close()
        _transcript = None
