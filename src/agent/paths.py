"""路径常量 —— 项目根、.scratch/、spec 文件名的单一事实来源。

此前 PROJECT_ROOT 在 context.py / issues.py / main.py 各自用不同深度
的 parent.parent(.parent) 计算，容易写错层级。现在收敛到一处。
"""

from pathlib import Path

# 项目根目录 = src/agent/paths.py 的上一级的上一级的上一级
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

# .scratch/ 根目录名（固定在项目根目录下）
SCRATCH_DIRNAME: str = ".scratch"

# spec.md 文件名
SPEC_FILENAME: str = "spec.md"
