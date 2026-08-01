"""运行上下文 —— 每次运行的独立工作区与输出转录。

所有产物（spec.md、生成的代码）集中在 runs/<时间戳>/ 下；
agent 在终端实时显示的流式输出（思考、工具调用、结果、错误）同步写入
该目录的 session.log —— 运行结束后打开它，就能回看 agent 全程做了什么、
出了什么问题，方便定位和修改。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TextIO

from agent.paths import PROJECT_ROOT

# runs/ 根目录（固定在项目根下）
RUNS_DIR: Path = PROJECT_ROOT / "runs"

# 当前运行目录（start_run 设置，未设置时惰性创建）
_current: Path | None = None

# 当前运行的转录文件句柄（session.log）
_transcript: TextIO | None = None


def start_run() -> Path:
    """创建本次运行的独立目录 runs/<时间戳>/，并打开 session.log。"""
    global _current, _transcript
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _current = RUNS_DIR / ts
    _current.mkdir(parents=True, exist_ok=True)
    (_current / "output").mkdir(exist_ok=True)
    _transcript = open(_current / "session.log", "w", encoding="utf-8", errors="replace")
    return _current


def current() -> Path:
    """当前运行目录；未显式 start 时惰性创建（保证转录总能写入）。"""
    global _current
    if _current is None:
        _current = start_run()
    return _current


def spec_path() -> Path:
    """本次运行的 spec.md 路径。"""
    return current() / "spec.md"


def output_dir() -> Path:
    """本次运行生成的代码目录。"""
    return current() / "output"


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
